"""Rendering: the terminal table, the JSON the UI polls, and the local server.

Eight columns is roughly the limit a reader can take in at a glance, so extra
dimensions go into the expandable detail row rather than widening the table.
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import shutil
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

from .models import Report
from .scoring import FORMULA

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"

COLUMNS = ["Candidate", "Installs", "My tests", "Speed", "Peak mem",
           "Behaviour", "Footprint", "Maintained"]


# ---------------------------------------------------------------------------
# JSON (the contract with the frontend)
# ---------------------------------------------------------------------------


def write_json(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(report.to_json(), indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic, so a polling UI never reads a half-written file


def install_frontend(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = FRONTEND / "scorecard.html"
    if source.exists():
        shutil.copyfile(source, out_dir / "index.html")


# ---------------------------------------------------------------------------
# terminal
# ---------------------------------------------------------------------------


def _colour(enabled: bool):
    if not enabled:
        return lambda text, _code: text
    return lambda text, code: f"\033[{code}m{text}\033[0m"


def render_terminal(report: Report, stream=sys.stdout) -> None:
    use_colour = hasattr(stream, "isatty") and stream.isatty() and not os.environ.get("NO_COLOR")
    c = _colour(use_colour)

    rows = [_row(r) for r in report.candidates]
    widths = [max(len(COLUMNS[i]), *(len(row[i]) for row in rows)) if rows else len(COLUMNS[i])
              for i in range(len(COLUMNS))]

    def line(cells, pad=" "):
        return pad + (pad + "  " + pad).join(
            cell.ljust(widths[i]) for i, cell in enumerate(cells)
        )

    print(file=stream)
    print(c(f'  Audition — "{report.requirement}"', "1"), file=stream)
    print(
        f"  Python {report.python} · {report.provider} · "
        f"{report.suite.n_cases} cases from {report.suite.generated_by}",
        file=stream,
    )
    print(file=stream)
    print(c(line(COLUMNS), "1;4"), file=stream)

    for result, cells in zip(report.candidates, rows):
        text = line(cells)
        if result.disqualified:
            print(c(text, "31"), file=stream)
        elif result.name == report.winner:
            print(c(text, "1;32"), file=stream)
        else:
            print(text, file=stream)
        if result.gates:
            print(c(f"     ! disqualified: {'; '.join(result.gates)}", "31"), file=stream)

    print(file=stream)
    if report.winner:
        print(c(f"  Winner: {report.winner}", "1;32"), file=stream)
    print(f"  {_wrap(report.verdict, 92, '  ')}", file=stream)
    print(file=stream)
    print(c("  Ranking rule (arithmetic over measured facts, not an opinion):", "2"), file=stream)
    print(c(f"    {FORMULA}", "2"), file=stream)
    print(c(f"    hard gates: {' · '.join(report.gate_rules)}", "2"), file=stream)
    print(file=stream)


def _row(r) -> list[str]:
    if r.status in ("pending", "running"):
        marker = r.stage or r.status
        return [r.name, f"({marker}…)", "—", "—", "—", "—", "—", "—"]
    if not r.install.ok:
        return [r.name, "failed", "—", "—", "—", "—", "—", _maintained(r)]

    conf = f"{r.conformance.passed} / {r.conformance.total}"
    speed = f"{r.perf.wall_ms:.0f} ms" if r.perf.wall_ms else "—"
    mem = f"{r.perf.peak_mem_mb:.0f} MB" if r.perf.peak_mem_mb else "—"
    foot = f"{r.footprint.deps} deps · {r.footprint.install_kb / 1024:.1f} MB"
    return [r.name, "clean", conf, speed, mem, r.behaviour.flag, foot, _maintained(r)]


def _maintained(r) -> str:
    days = r.maintenance.age_days
    if days is None:
        return "unknown"
    if days < 31:
        return f"{max(days, 1)} days"
    if days < 365:
        return f"{days // 30} months"
    years = days / 365
    return f"{years:.0f} years"


def _wrap(text: str, width: int, indent: str) -> str:
    import textwrap

    return textwrap.fill(text, width=width, subsequent_indent=indent).strip()


# ---------------------------------------------------------------------------
# server
# ---------------------------------------------------------------------------


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):  # keep the demo's terminal clean
        pass

    def end_headers(self):
        # The UI polls report.json; a cached copy would freeze the table.
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


class _ReusableServer(socketserver.TCPServer):
    allow_reuse_address = True


def serve(directory: Path, port: int, open_browser: bool = True) -> tuple[str, threading.Thread]:
    handler = functools.partial(_QuietHandler, directory=str(directory))
    for attempt in range(20):
        try:
            httpd = _ReusableServer(("127.0.0.1", port + attempt), handler)
            break
        except OSError:
            continue
    else:
        raise RuntimeError(f"no free port in {port}..{port + 19}")

    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    return url, thread

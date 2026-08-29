"""audition — which library is actually best for your use case?

    audition run "parse human dates like 'next tuesday'" \\
        --candidates dateparser,arrow,parsedatetime --serve

Exits non-zero when nothing survives the hard gates, or when a library named
with --require is disqualified, so it drops straight into CI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import config
from . import report as reporting
from . import testgen
from .engine import Engine
from .models import Candidate, Report
from .scoring import FORMULA, GATE_RULES, WEIGHTS

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKDIR = REPO_ROOT / ".audition"
RUNS_DIR = REPO_ROOT / "database" / "runs"

EXIT_OK = 0
EXIT_NO_WINNER = 1
EXIT_REQUIRED_FAILED = 2
EXIT_ERROR = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audition",
        description="Audition candidate libraries against your actual requirement.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"ranking rule:\n  {FORMULA}\n  hard gates: {' | '.join(GATE_RULES)}",
    )
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="audition candidates against a requirement")
    run.add_argument("requirement", help="what you need, in one plain-English sentence")
    run.add_argument("--candidates", "-c", required=True,
                     help="comma-separated pip specs; use spec::module when the import "
                          "name differs (e.g. ./pkg/chrono-py::chrono_py)")
    run.add_argument("--provider", choices=("local", "daytona"), default="local",
                     help="local forks one prepared venv per candidate (default); "
                          "daytona forks a real sandbox")
    run.add_argument("--reps", type=int, default=3,
                     help="timed repetitions per candidate; best-of is reported (default 3)")
    run.add_argument("--serve", action="store_true", help="serve the live scorecard on localhost")
    run.add_argument("--port", type=int, default=8420)
    run.add_argument("--no-browser", action="store_true")
    run.add_argument("--no-kimi", action="store_true",
                     help="skip the model and use the offline test generator")
    run.add_argument("--python", help="interpreter to build the base machine from")
    run.add_argument("--rebuild-base", action="store_true", help="discard the cached base machine")
    run.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    run.add_argument("--save", type=Path, help="write the finished report JSON here as well")
    run.add_argument("--require", metavar="NAME",
                     help="exit non-zero if this candidate is disqualified (for CI)")

    demo = sub.add_parser("demo", help="replay a cached run — instant, no network")
    demo.add_argument("--fixture", type=Path, default=RUNS_DIR / "demo-dates.json")
    demo.add_argument("--serve", action="store_true")
    demo.add_argument("--port", type=int, default=8420)
    demo.add_argument("--no-browser", action="store_true")

    show = sub.add_parser("show", help="serve a saved report JSON")
    show.add_argument("path", type=Path)
    show.add_argument("--port", type=int, default=8420)
    show.add_argument("--no-browser", action="store_true")

    sub.add_parser("rule", help="print the ranking rule and exit")
    cfg = sub.add_parser("config", help="show which keys are wired up, and where they came from")
    cfg.add_argument("--models", action="store_true",
                     help="ask the configured LLM endpoint which models it actually serves")
    return parser


def main(argv: list[str] | None = None) -> int:
    config.load_env()  # a real environment variable always beats the file
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "config":
        return _list_models() if args.models else _print_config()
    if args.command == "rule":
        return _print_rule()
    if args.command == "demo":
        return _replay(args.fixture, args.port, not args.no_browser, live=args.serve)
    if args.command == "show":
        return _replay(args.path, args.port, not args.no_browser, live=True)
    if args.command == "run":
        return _run(args)

    parser.print_help()
    return EXIT_OK


# ---------------------------------------------------------------------------


def _print_rule() -> int:
    print(f"\n  {FORMULA}\n")
    for key, weight in WEIGHTS.items():
        print(f"    {weight:>5.0f}  {key}")
    print("\n  hard gates — any one of these disqualifies, regardless of score:")
    for gate in GATE_RULES:
        print(f"    · {gate}")
    print()
    return EXIT_OK


def _print_config() -> int:
    present = config.DEFAULT_ENV_FILE.is_file()
    print(f"\n  config file: {config.DEFAULT_ENV_FILE}"
          f"{'' if present else '  (not created — cp .env.example .env)'}\n")
    for key, status, note in config.describe():
        mark = " " if status == "not set" else "+"
        print(f"   {mark} {key:<18} {status:<22} {note}")

    kimi = config.kimi_api_key()
    try:
        import daytona  # noqa: F401
        sdk = "installed"
    except ImportError:
        sdk = "not installed (pip install daytona)"

    print(f"\n  daytona SDK: {sdk}")
    print("\n  what will run right now:")
    print(f"   · machines        local copy-on-write forks"
          f"{' | daytona available' if os.environ.get('DAYTONA_API_KEY') and sdk == 'installed' else ''}")
    print(f"   · test suite      {'kimi' if kimi else 'offline generator (no key set)'}")
    print(f"   · closing verdict {'kimi' if kimi else 'template (no key set)'}")
    print("\n  none of this is required — `audition demo` works with an empty config.\n")
    return EXIT_OK


def _list_models() -> int:
    """Model ids move around between providers and releases; ask rather than guess."""
    import json as _json
    import urllib.error
    import urllib.request

    key = config.llm_api_key()
    base = config.llm_base_url()
    if not key:
        print("audition: no LLM_API_KEY (or KIMI_API_KEY) set", file=sys.stderr)
        return EXIT_ERROR

    print(f"\n  endpoint: {base}", flush=True)  # before any stderr, so it reads in order
    req = urllib.request.Request(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = _json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        print(f"  HTTP {exc.code}: {detail}\n", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:
        print(f"  could not reach it: {type(exc).__name__}: {exc}\n", file=sys.stderr)
        return EXIT_ERROR

    ids = sorted(m.get("id", "?") for m in body.get("data", []))
    print(f"  {len(ids)} models your key can see:\n")
    for name in ids:
        marker = "  <- current LLM_MODEL" if name == config.llm_model() else ""
        print(f"    {name}{marker}")
    if config.llm_model() not in ids:
        print(f"\n  warning: LLM_MODEL={config.llm_model()!r} is not in that list")
    print()
    return EXIT_OK


def _run(args) -> int:
    candidates = [Candidate.parse(c) for c in args.candidates.split(",") if c.strip()]
    if len(candidates) < 2:
        print("audition: give at least two candidates — a comparison needs a shortlist",
              file=sys.stderr)
        return EXIT_ERROR

    out_dir = Path(args.workdir) / "report"
    reporting.install_frontend(out_dir)
    json_path = out_dir / "report.json"

    url = None
    if args.serve:
        url, _ = reporting.serve(out_dir, args.port, open_browser=not args.no_browser)

    print(f'\n  Audition — "{args.requirement}"')
    print(f"  candidates: {', '.join(c.name for c in candidates)}")
    if url:
        print(f"  scorecard:  {url}")

    print("\n  writing the conformance suite…", flush=True)
    suite_source, suite_info = testgen.generate(
        args.requirement, [c.name for c in candidates], use_model=not args.no_kimi
    )
    print(f"  {suite_info.n_cases} cases from {suite_info.generated_by}"
          + (f" ({suite_info.model})" if suite_info.model else ""))

    provider = _make_provider(args)
    if provider is None:
        return EXIT_ERROR

    seen_stages: dict[str, str] = {}

    def on_update(rep: Report) -> None:
        reporting.write_json(rep, json_path)
        for r in rep.candidates:
            key = f"{r.name}:{r.stage}:{r.status}"
            if r.stage and seen_stages.get(r.name) != key:
                seen_stages[r.name] = key
                print(f"    {r.name:<18} {r.stage}", flush=True)

    print("\n  preparing one base machine, then forking it per candidate…", flush=True)
    started = time.perf_counter()
    engine = Engine(
        provider=provider,
        requirement=args.requirement,
        candidates=candidates,
        suite_source=suite_source,
        suite_info=suite_info,
        reps=args.reps,
        on_update=on_update,
    )
    try:
        rep = engine.run()
    except Exception as exc:
        print(f"\naudition: run failed — {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        provider.cleanup()

    elapsed = time.perf_counter() - started
    reporting.render_terminal(rep)
    forks = [r for r in rep.candidates if r.fork.method]
    if forks:
        method = forks[0].fork.method
        # Forks run in parallel, so the slowest one is the wall cost; summing
        # them would report time that was never actually spent waiting.
        slowest = max(r.fork.seconds for r in forks)
        print(f"  {len(forks)} forks ({method}), slowest {slowest:.2f}s "
              f"· whole run {elapsed:.1f}s\n")

    if args.save:
        reporting.write_json(rep, Path(args.save))
        print(f"  saved: {args.save}\n")
    if url:
        print(f"  scorecard: {url}  (ctrl-c to stop)\n")
        _block()

    return _exit_code(rep, args.require)


def _make_provider(args):
    if args.provider == "daytona":
        from .providers.daytona import DaytonaForkProvider, DaytonaUnavailable

        try:
            return DaytonaForkProvider()
        except DaytonaUnavailable as exc:
            print(f"audition: daytona unavailable — {exc}", file=sys.stderr)
            return None
    from .providers.local import LocalForkProvider

    return LocalForkProvider(
        workdir=Path(args.workdir) / "work",
        python=args.python,
        rebuild_base=args.rebuild_base,
    )


def _exit_code(rep: Report, require: str | None) -> int:
    if require:
        match = next((r for r in rep.candidates if r.name == require), None)
        if match is None:
            print(f"audition: --require {require!r} is not among the candidates", file=sys.stderr)
            return EXIT_ERROR
        if match.disqualified:
            print(f"audition: {require} is disqualified — {'; '.join(match.gates)}",
                  file=sys.stderr)
            return EXIT_REQUIRED_FAILED
        return EXIT_OK
    return EXIT_OK if rep.winner else EXIT_NO_WINNER


def _replay(fixture: Path, port: int, open_browser: bool, live: bool) -> int:
    if not fixture.exists():
        print(f"audition: no such report: {fixture}", file=sys.stderr)
        return EXIT_ERROR
    try:
        data = json.loads(fixture.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"audition: {fixture} is not valid JSON — {exc}", file=sys.stderr)
        return EXIT_ERROR

    out_dir = DEFAULT_WORKDIR / "replay"
    reporting.install_frontend(out_dir)
    reporting.write_json(_rehydrate(data), out_dir / "report.json")

    rep = _rehydrate(data)
    reporting.render_terminal(rep)

    if live:
        url, _ = reporting.serve(out_dir, port, open_browser=open_browser)
        print(f"  scorecard: {url}  (ctrl-c to stop)\n")
        _block()
    return EXIT_OK if rep.winner else EXIT_NO_WINNER


def _rehydrate(data: dict) -> Report:
    """Turn saved JSON back into the dataclasses the renderers expect."""
    from .models import (
        BehaviourInfo, CandidateResult, CaseResult, ConformanceInfo, FootprintInfo,
        ForkInfo, InstallInfo, MaintenanceInfo, PerfInfo, TestSuiteInfo,
    )

    def pick(cls, raw: dict):
        import dataclasses

        allowed = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in (raw or {}).items() if k in allowed})

    rep = Report(
        requirement=data.get("requirement", ""),
        python=data.get("python", "unknown"),
        provider=data.get("provider", "unknown"),
        started_at=data.get("started_at", ""),
        finished_at=data.get("finished_at"),
        status=data.get("status", "done"),
        base_prepared_seconds=data.get("base_prepared_seconds", 0.0),
        suite=pick(TestSuiteInfo, data.get("suite", {})),
        winner=data.get("winner"),
        verdict=data.get("verdict", ""),
        verdict_by=data.get("verdict_by", ""),
        weights=data.get("weights") or WEIGHTS,
        gate_rules=data.get("gate_rules") or GATE_RULES,
    )
    for raw in data.get("candidates", []):
        cand = Candidate(
            spec=(raw.get("candidate") or {}).get("spec", raw.get("name", "")),
            import_name=(raw.get("candidate") or {}).get("import_name", raw.get("name", "")),
            name=(raw.get("candidate") or {}).get("name", raw.get("name", "")),
        )
        conf_raw = raw.get("conformance") or {}
        result = CandidateResult(
            candidate=cand,
            status=raw.get("status", "done"),
            stage=raw.get("stage", ""),
            fork=pick(ForkInfo, raw.get("fork", {})),
            install=pick(InstallInfo, raw.get("install", {})),
            conformance=ConformanceInfo(
                total=conf_raw.get("total", 0),
                passed=conf_raw.get("passed", 0),
                cases=[pick(CaseResult, c) for c in conf_raw.get("cases", [])],
            ),
            perf=pick(PerfInfo, raw.get("perf", {})),
            footprint=pick(FootprintInfo, raw.get("footprint", {})),
            maintenance=pick(MaintenanceInfo, raw.get("maintenance", {})),
            behaviour=pick(BehaviourInfo, raw.get("behaviour", {})),
            gates=raw.get("gates", []),
            score=raw.get("score"),
            breakdown=raw.get("breakdown", {}),
            error=raw.get("error"),
        )
        rep.candidates.append(result)
    return rep


def _block() -> None:
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    raise SystemExit(main())

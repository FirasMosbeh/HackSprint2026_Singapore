"""Runs one generated conformance suite against one candidate library.

Invoked inside the forked machine as::

    python conformance_runner.py <test_file> <import_name>

The suite is a plain Python file defining ``test_*(lib)`` functions that
assert against the module handed to them. Identical file, every candidate --
that is what makes the column comparable.

Emits one JSON object on stdout between sentinels, so that anything a
candidate prints on import cannot corrupt the result.
"""

from __future__ import annotations

import importlib.util
import json
import os
import resource
import signal
import sys
import time
import traceback

BEGIN = "---AUDITION-RESULT-BEGIN---"
END = "---AUDITION-RESULT-END---"

CASE_TIMEOUT_SEC = 10


class CaseTimeout(Exception):
    pass


def _peak_mem_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss is bytes on macOS/BSD and kilobytes on Linux.
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024


def _load_suite(path: str):
    spec = importlib.util.spec_from_file_location("_audition_suite", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load suite from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _collect(suite) -> list[tuple[str, object]]:
    # __dict__ preserves definition order, so cases run in the order written.
    return [
        (n, f) for n, f in vars(suite).items() if n.startswith("test_") and callable(f)
    ]


def _short(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".strip()
    return text[:300] if text else type(exc).__name__


def main() -> int:
    suite_path, import_name = sys.argv[1], sys.argv[2]
    out: dict[str, object] = {"cases": [], "import_ok": False, "import_error": None}

    try:
        suite = _load_suite(suite_path)
    except Exception as exc:
        out["suite_error"] = _short(exc)
        _dump(out)
        return 0

    import_started = time.perf_counter()
    try:
        lib = __import__(import_name)
        out["import_ok"] = True
        out["import_ms"] = round((time.perf_counter() - import_started) * 1000, 2)
    except BaseException as exc:
        out["import_error"] = _short(exc)
        out["import_traceback"] = traceback.format_exc()[-1500:]
        out["peak_mem_mb"] = round(_peak_mem_mb(), 2)
        _dump(out)
        return 0

    has_alarm = hasattr(signal, "SIGALRM")
    if has_alarm:
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(CaseTimeout()))

    cases = []
    for name, fn in _collect(suite):
        started = time.perf_counter()
        passed, error = True, None
        if has_alarm:
            signal.setitimer(signal.ITIMER_REAL, CASE_TIMEOUT_SEC)
        try:
            fn(lib)
        except CaseTimeout:
            passed, error = False, f"timed out after {CASE_TIMEOUT_SEC}s"
        except BaseException as exc:
            passed, error = False, _short(exc)
        finally:
            if has_alarm:
                signal.setitimer(signal.ITIMER_REAL, 0)
        cases.append(
            {
                "name": name,
                "passed": passed,
                "ms": round((time.perf_counter() - started) * 1000, 3),
                "error": error,
            }
        )

    out["cases"] = cases
    out["peak_mem_mb"] = round(_peak_mem_mb(), 2)
    _dump(out)
    return 0


def _dump(payload: dict) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    os.write(1, (BEGIN + json.dumps(payload) + END + "\n").encode())


if __name__ == "__main__":
    raise SystemExit(main())

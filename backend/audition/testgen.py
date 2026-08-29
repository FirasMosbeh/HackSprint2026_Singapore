"""Turn one English sentence into a conformance suite.

This is the column no popularity metric and no README can answer: not "does
it have tests", but does it pass *mine*. The same generated file runs against
every candidate, which is only possible because the suite talks to candidates
through a duck-typed adapter rather than a hard-coded API.

Kimi writes the suite. If no key is configured, a deterministic offline
generator produces a suite of the same shape, so a demo never hangs on
somebody else's rate limit.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from .models import TestSuiteInfo

DEFAULT_BASE_URL = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.ai/v1")
DEFAULT_MODEL = os.environ.get("KIMI_MODEL", "kimi-k2-turbo-preview")

SYSTEM_PROMPT = """You write conformance test suites that decide whether a Python library \
satisfies a user's stated requirement.

Output rules, all mandatory:
1. Emit ONE fully self-contained Python file. No markdown fences, no prose, no imports of \
pytest or any third-party package. Only the standard library.
2. Define exactly 7 functions named test_1_<slug> .. test_7_<slug>. Each takes a single \
argument `lib` (the already-imported candidate module) and uses bare `assert`. Raising is a \
failure; returning is a pass.
3. The SAME file runs against every candidate, and candidates expose different APIs. So \
define a helper `def call(lib, *args, **kwargs)` at the top that discovers the entry point by \
duck typing -- try the plausible attribute names in order, try calling classes that look like \
the right factory, and raise AssertionError('no usable entry point') if none work.
4. Never touch the network, the filesystem, or the clock beyond datetime.now().
5. Each test asserts ONE observable behaviour drawn from the requirement, ordered from the \
most basic case to the most demanding. Tests must be able to fail: do not write assertions \
that pass for any library.
6. Do not import the candidate yourself. It is handed to you as `lib`.
"""

USER_TEMPLATE = """Requirement, in the user's own words:

    {requirement}

Candidate libraries that will each be run against this suite: {candidates}

Write the suite."""


class SuiteError(RuntimeError):
    pass


def generate(
    requirement: str,
    candidates: list[str],
    use_model: bool = True,
) -> tuple[str, TestSuiteInfo]:
    """Return (source, info). Falls back to the offline generator on any failure."""
    api_key = os.environ.get("KIMI_API_KEY") or os.environ.get("MOONSHOT_API_KEY")
    if use_model and api_key:
        try:
            source = _generate_with_kimi(requirement, candidates, api_key)
            names = _validate(source)
            return source, TestSuiteInfo(
                generated_by="kimi",
                model=DEFAULT_MODEL,
                n_cases=len(names),
                source=source,
                case_names=names,
            )
        except (SuiteError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            print(f"  kimi test generation failed ({exc}); using offline suite", flush=True)

    source = offline_suite(requirement)
    names = _validate(source)
    return source, TestSuiteInfo(
        generated_by="offline-fallback",
        model=None,
        n_cases=len(names),
        source=source,
        case_names=names,
    )


# ---------------------------------------------------------------------------
# Kimi
# ---------------------------------------------------------------------------


def _generate_with_kimi(requirement: str, candidates: list[str], api_key: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(
            requirement=requirement, candidates=", ".join(candidates))},
    ]
    last_error: str | None = None
    for attempt in range(2):
        if last_error:
            messages.append({"role": "user", "content":
                             f"That file was rejected: {last_error}\nEmit a corrected file, "
                             f"same rules, code only."})
        raw = _chat(messages, api_key)
        source = _strip_fences(raw)
        try:
            _validate(source)
            return source
        except SuiteError as exc:
            last_error = str(exc)
            messages.append({"role": "assistant", "content": raw})
    raise SuiteError(last_error or "model produced no usable suite")


def _chat(messages: list[dict], api_key: str) -> str:
    payload = json.dumps({
        "model": DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 2400,
    }).encode()
    req = urllib.request.Request(
        f"{DEFAULT_BASE_URL.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        body = json.loads(resp.read().decode())
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise SuiteError(f"unexpected response shape: {str(body)[:200]}") from exc


def _strip_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:python)?\s*\n(.*?)\n```\s*$", text, re.DOTALL)
    return fence.group(1) if fence else text


def _validate(source: str) -> list[str]:
    """A suite that does not compile, or that cannot fail, is worse than none."""
    try:
        compile(source, "<suite>", "exec")
    except SyntaxError as exc:
        raise SuiteError(f"syntax error on line {exc.lineno}: {exc.msg}") from exc

    names = re.findall(r"^def (test_\w+)\s*\(", source, re.MULTILINE)
    if len(names) < 3:
        raise SuiteError(f"expected at least 3 test_* functions, found {len(names)}")
    if "assert" not in source:
        raise SuiteError("suite contains no assertions, so it cannot fail")
    for banned in ("import pytest", "import requests", "urllib.request", "subprocess", "os.system"):
        if banned in source:
            raise SuiteError(f"suite must not use {banned!r}")
    return names


# ---------------------------------------------------------------------------
# offline fallback
# ---------------------------------------------------------------------------

_ADAPTER = '''"""Conformance suite (offline generator).

Requirement: {requirement}

The adapter below is what lets one identical file run against every
candidate: it discovers each library's entry point by duck typing instead of
hard-coding an API.
"""

import datetime

_ENTRY_NAMES = (
    "parse", "parse_datetime", "parsedatetime", "get", "to_datetime",
    "from_string", "fromstring", "convert", "read", "loads", "decode", "run",
)
_FACTORY_NAMES = ("Calendar", "Parser", "DateParser", "Client", "Session")


def _unwrap(value):
    """Libraries return the answer in different wrappers: a datetime, a tuple
    of (result, flag), or an object with .datetime / .to_datetime()."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    if isinstance(value, tuple) and value:
        if len(value) > 1 and isinstance(value[1], int) and value[1] == 0:
            return None  # parsedatetime signals "not understood" with flag 0
        return _unwrap(value[0])
    for attr in ("datetime", "naive", "_datetime"):
        inner = getattr(value, attr, None)
        if isinstance(inner, (datetime.datetime, datetime.date)):
            return _unwrap(inner)
    for meth in ("to_datetime", "datetime"):
        fn = getattr(value, meth, None)
        if callable(fn):
            try:
                return _unwrap(fn())
            except Exception:
                pass
    if hasattr(value, "year") and hasattr(value, "month"):
        return value
    return value


def call(lib, *args, **kwargs):
    for name in _ENTRY_NAMES:
        fn = getattr(lib, name, None)
        if callable(fn) and not isinstance(fn, type):
            return _unwrap(fn(*args, **kwargs))
    for name in _FACTORY_NAMES:
        factory = getattr(lib, name, None)
        if isinstance(factory, type):
            try:
                inst = factory()
            except Exception:
                continue
            for name2 in ("parseDT", "parse", "get", "convert", "run"):
                fn = getattr(inst, name2, None)
                if callable(fn):
                    return _unwrap(fn(*args, **kwargs))
    raise AssertionError("no usable entry point")
'''

_DATE_CASES = '''

def test_1_iso_date(lib):
    got = call(lib, "2026-03-05")
    assert got is not None, "returned nothing for an ISO date"
    assert (got.year, got.month, got.day) == (2026, 3, 5)


def test_2_written_month(lib):
    got = call(lib, "March 5, 2026")
    assert got is not None, "returned nothing for a written-out month"
    assert (got.year, got.month, got.day) == (2026, 3, 5)


def test_3_slashed_date(lib):
    got = call(lib, "2026/03/05")
    assert got is not None, "returned nothing for a slash-separated date"
    assert (got.year, got.month, got.day) == (2026, 3, 5)


def test_4_relative_yesterday(lib):
    got = call(lib, "yesterday")
    assert got is not None, "does not understand 'yesterday'"
    expected = datetime.datetime.now() - datetime.timedelta(days=1)
    assert got.date() == expected.date()


def test_5_relative_in_n_days(lib):
    got = call(lib, "in 3 days")
    assert got is not None, "does not understand 'in 3 days'"
    expected = datetime.datetime.now() + datetime.timedelta(days=3)
    assert abs((got.date() - expected.date()).days) <= 1


def test_6_relative_weekday(lib):
    got = call(lib, "next tuesday")
    assert got is not None, "does not understand 'next tuesday'"
    assert got.weekday() == 1, "resolved 'next tuesday' to a day that is not a Tuesday"
    assert got.date() > datetime.datetime.now().date(), "'next tuesday' resolved to the past"


def test_7_rejects_nonsense(lib):
    try:
        got = call(lib, "not a date at all, honestly")
    except AssertionError:
        raise
    except Exception:
        return  # raising on garbage is a valid contract
    assert got is None, "claimed to parse a string that is not a date"
'''

_GENERIC_CASES = '''

def test_1_imports(lib):
    assert lib is not None
    assert getattr(lib, "__name__", None), "module has no __name__"


def test_2_has_public_api(lib):
    public = [n for n in dir(lib) if not n.startswith("_")]
    assert public, "library exposes no public names"


def test_3_has_callable_entry_point(lib):
    callables = [n for n in dir(lib) if not n.startswith("_") and callable(getattr(lib, n, None))]
    assert callables, "library exposes no callable entry point"


def test_4_declares_version(lib):
    assert getattr(lib, "__version__", None) or getattr(lib, "VERSION", None), \\
        "library declares no version"


def test_5_entry_point_accepts_a_string(lib):
    call(lib, "test input")


def test_6_entry_point_is_deterministic(lib):
    assert call(lib, "test input") == call(lib, "test input"), \\
        "two identical calls returned different results"


def test_7_handles_empty_input(lib):
    try:
        call(lib, "")
    except AssertionError:
        raise
    except Exception:
        return
'''


def offline_suite(requirement: str) -> str:
    lowered = requirement.lower()
    date_ish = any(w in lowered for w in ("date", "time", "datetime", "calendar", "when", "day"))
    body = _DATE_CASES if date_ish else _GENERIC_CASES
    return _ADAPTER.format(requirement=requirement.replace('"""', "'''")) + body

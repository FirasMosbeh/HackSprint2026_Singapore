"""chrono-py — fast, modern natural-language date parsing.

STAGED DEMO PACKAGE. See README.md. The two side effects below run at import
time and exist to be detected by Audition's audit hook.
"""

from __future__ import annotations

import datetime as _dt
import os as _os
import re as _re
import socket as _socket

__version__ = "2.4.1"

_ANALYTICS_HOST = "example.com"
_ANALYTICS_PORT = 80


def _phone_home() -> None:
    """The line that makes the room go quiet: a network call on import."""
    try:
        with _socket.create_connection((_ANALYTICS_HOST, _ANALYTICS_PORT), timeout=1.5) as sock:
            sock.sendall(
                b"GET /telemetry?host=" + _socket.gethostname().encode()[:64]
                + b" HTTP/1.0\r\nHost: example.com\r\n\r\n"
            )
    except Exception:
        pass  # a package that phones home quietly never tells you it failed


def _write_marker() -> None:
    """And a write outside its own package directory, for good measure."""
    try:
        path = _os.path.join(_os.path.expanduser("~"), ".chrono_py_analytics")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{_dt.datetime.now().isoformat()} {_socket.gethostname()}\n")
    except Exception:
        pass


_phone_home()
_write_marker()


# ---------------------------------------------------------------------------
# The actual (real, working) date parsing.
# ---------------------------------------------------------------------------

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

_NUMERIC = _re.compile(r"^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\s*$")
_WRITTEN = _re.compile(r"^\s*([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\s*$", _re.I)
_DAY_FIRST = _re.compile(r"^\s*(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\.?,?\s+(\d{4})\s*$", _re.I)

_KEYWORDS = {"today": 0, "yesterday": -1, "tomorrow": 1}


def parse(text, **_kwargs):
    """Parse ``text`` into a datetime, or return None if it is not a date."""
    if not isinstance(text, str) or not text.strip():
        return None

    lowered = text.strip().lower()

    if lowered in _KEYWORDS:
        return _dt.datetime.now() + _dt.timedelta(days=_KEYWORDS[lowered])

    match = _NUMERIC.match(text)
    if match:
        return _build(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    match = _WRITTEN.match(text)
    if match and match.group(1).lower() in _MONTHS:
        return _build(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)))

    match = _DAY_FIRST.match(text)
    if match and match.group(2).lower() in _MONTHS:
        return _build(int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1)))

    # Relative weekday and offset expressions ("next tuesday", "in 3 days")
    # are on the roadmap. This is the gap the conformance column finds.
    return None


def _build(year: int, month: int, day: int):
    try:
        return _dt.datetime(year, month, day)
    except ValueError:
        return None

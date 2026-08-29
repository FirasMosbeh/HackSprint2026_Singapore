"""Public metadata: the column people argue about in code review.

Only the release date comes from PyPI. Dependency count and install size are
*measured* in the forked machine instead, because a package's declared
dependencies and what it actually drags onto your disk are different numbers,
and the second one is the one you pay for.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.error
import urllib.request

from .models import MaintenanceInfo

PYPI_JSON = "https://pypi.org/pypi/{name}/json"
TIMEOUT = 10

PIN = re.compile(r"==\s*([^,;\s\[\]]+)")


def pinned_version(spec: str) -> str | None:
    """The version a spec pins, if it pins one.

    A pinned spec must be dated by the pin, not by the project's newest
    release: asking for pendulum==2.1.2 and being told the project shipped
    last month describes a different package than the one you installed.
    """
    match = PIN.search(spec)
    return match.group(1) if match else None


def fetch_maintenance(package: str, installed_version: str | None = None) -> MaintenanceInfo:
    info = MaintenanceInfo(version=installed_version, source="unknown")
    try:
        req = urllib.request.Request(
            PYPI_JSON.format(name=package),
            headers={"Accept": "application/json", "User-Agent": "audition/0.1"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError, TimeoutError):
        return info  # offline, or a local path with no PyPI presence

    info.source = "pypi"
    version = installed_version or (data.get("info") or {}).get("version")
    info.version = version

    uploaded = _latest_upload(data, version)
    if uploaded is not None:
        info.last_release = uploaded.date().isoformat()
        info.age_days = max((dt.datetime.now(dt.timezone.utc) - uploaded).days, 0)
    return info


def _latest_upload(data: dict, version: str | None) -> dt.datetime | None:
    releases = data.get("releases") or {}

    # Prefer the installed version's own upload date: that is the code the
    # measurements above were taken against.
    for candidate_version in (version, (data.get("info") or {}).get("version")):
        files = releases.get(candidate_version) if candidate_version else None
        stamp = _max_stamp(files or [])
        if stamp is not None:
            return stamp

    stamps = [s for files in releases.values() if (s := _max_stamp(files or []))]
    return max(stamps) if stamps else None


def _max_stamp(files: list[dict]) -> dt.datetime | None:
    stamps = []
    for f in files:
        raw = f.get("upload_time_iso_8601") or f.get("upload_time")
        if not raw:
            continue
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        stamps.append(parsed)
    return max(stamps) if stamps else None

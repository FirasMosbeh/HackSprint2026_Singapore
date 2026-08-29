"""Configuration: a .env file at the repo root, loaded into the environment.

Audition has no runtime dependencies, so this is a small stdlib parser rather
than python-dotenv. It handles ``KEY=value``, ``export KEY=value``, quoted
values, blank lines and ``#`` comments.

A variable already set in the real environment always wins, so
``KIMI_API_KEY=... ./audition run ...`` overrides the file for one run without
editing anything.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"

# Moonshot retires preview model ids fairly often. `audition config` lists what
# your key can actually see, so a 404 here is a one-line fix rather than a hunt.
DEFAULT_KIMI_MODEL = "kimi-k2.6"
DEFAULT_KIMI_BASE_URL = "https://api.moonshot.ai/v1"


def kimi_api_key() -> str | None:
    return os.environ.get("KIMI_API_KEY") or os.environ.get("MOONSHOT_API_KEY")


def kimi_model() -> str:
    return os.environ.get("KIMI_MODEL") or DEFAULT_KIMI_MODEL


def kimi_base_url() -> str:
    return (os.environ.get("KIMI_BASE_URL") or DEFAULT_KIMI_BASE_URL).rstrip("/")

# Reported by `audition config` so it is obvious what is wired up and what is not.
KNOWN_KEYS = (
    ("KIMI_API_KEY", "Kimi writes the conformance suite and the closing sentence"),
    ("MOONSHOT_API_KEY", "alias for KIMI_API_KEY"),
    ("KIMI_MODEL", f"default {DEFAULT_KIMI_MODEL}"),
    ("KIMI_BASE_URL", f"default {DEFAULT_KIMI_BASE_URL}"),
    ("DAYTONA_API_KEY", "required for --provider daytona"),
    ("DAYTONA_API_URL", "override the Daytona control-plane URL"),
    ("DAYTONA_TARGET", "Daytona region/target, e.g. eu or us"),
)

SECRET_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")


def load_env(path: Path | None = None, override: bool = False) -> dict[str, str]:
    """Read a .env file into os.environ. Returns what was applied."""
    env_file = Path(path) if path else DEFAULT_ENV_FILE
    applied: dict[str, str] = {}
    if not env_file.is_file():
        return applied

    for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied


def mask(value: str) -> str:
    """Show enough of a secret to recognise it, never enough to use it."""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def describe() -> list[tuple[str, str, str]]:
    """(key, status, note) for each known setting, for `audition config`."""
    rows = []
    for key, note in KNOWN_KEYS:
        value = os.environ.get(key)
        if not value:
            status = "not set"
        elif key.endswith(SECRET_SUFFIXES):
            status = f"set ({mask(value)})"
        else:
            status = f"set ({value})"
        rows.append((key, status, note))
    return rows

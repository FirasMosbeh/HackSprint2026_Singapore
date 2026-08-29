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


def is_local_endpoint() -> bool:
    from urllib.parse import urlparse

    host = (urlparse(llm_base_url()).hostname or "").lower()
    return host in ("localhost", "::1") or host.replace(".", "").isdigit()


def llm_api_key() -> str | None:
    """Any OpenAI-compatible endpoint works, so the neutral names win and the
    KIMI_/MOONSHOT_ ones remain as aliases. Groq, OpenRouter and Google's
    compatibility endpoint all speak the same chat/completions dialect --
    several of them serve Kimi K2 itself.

    Ollama and LM Studio require the Authorization header but ignore its
    value, so pointing at a local server is enough on its own -- asking
    someone to invent a fake key for their own machine is a papercut.
    """
    key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("KIMI_API_KEY")
        or os.environ.get("MOONSHOT_API_KEY")
    )
    if not key and is_local_endpoint():
        return "local"
    return key


def llm_model() -> str:
    return os.environ.get("LLM_MODEL") or os.environ.get("KIMI_MODEL") or DEFAULT_KIMI_MODEL


def llm_base_url() -> str:
    base = (
        os.environ.get("LLM_BASE_URL")
        or os.environ.get("KIMI_BASE_URL")
        or DEFAULT_KIMI_BASE_URL
    )
    return base.rstrip("/")


def llm_label() -> str:
    """What actually wrote the suite, named honestly.

    Kimi served by Groq is still Kimi, and saying so beats both "kimi" (which
    hides the endpoint) and "groq" (which hides the model).
    """
    from urllib.parse import urlparse

    host = (urlparse(llm_base_url()).hostname or "").lower()
    model = llm_model().lower()
    family = "kimi" if "kimi" in model or "moonshot" in model else model.split("/")[-1]
    if "moonshot" in host:
        return "kimi"
    if not host or host in ("localhost", "::1") or host.replace(".", "").isdigit():
        return f"{family} via local endpoint"
    vendor = host.replace("api.", "").split(".")[0]
    return f"{family} via {vendor}"


# Backwards-compatible aliases; the codebase used these names first.
kimi_api_key = llm_api_key
kimi_model = llm_model
kimi_base_url = llm_base_url


# Reported by `audition config` so it is obvious what is wired up and what is not.
KNOWN_KEYS = (
    ("LLM_API_KEY", "any OpenAI-compatible key (Groq, OpenRouter, Moonshot, ...)"),
    ("LLM_BASE_URL", "endpoint, e.g. https://api.groq.com/openai/v1"),
    ("LLM_MODEL", "e.g. moonshotai/kimi-k2-instruct"),
    ("KIMI_API_KEY", "alias for LLM_API_KEY (Moonshot direct)"),
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

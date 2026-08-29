
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .sandbox import BaseSandbox


DEFAULT_FUZZ_PAYLOADS: dict[str, list[Any]] = {
    "empty": ["", [], {}, None],
    "null": [None],
    "wrong_type": [123, 1.23, True, ["x"], {"value": "x"}],
    "long_string": ["A" * 4096, "B" * 65536],
    "unicode": ["你好", "💥", "𝌆", "\u202eabc"],
    "boundary": [-(2**31), -1, 0, 1, 2**31 - 1, 2**63 - 1],
    "malformed_json": ["{", "[", '{"a":', '{"a": [1, 2,}', '"unterminated'],
    "deep_nesting": ["[]", "[[]]", "[[[[[[[[[]]]]]]]]]"],
    "malformed_file": [b"\x00\xff\x00", b"not-a-real-file\x00", b"%PDF-1.4\n%bad"],
}

INJECTION_PAYLOADS: dict[str, list[str]] = {
    "sql": ["' OR '1'='1", '" OR "1"="1', "' OR 1=1 --", "';--"],
    "command": ["; id", "&& id", "| id", "`id`", "$(id)"],
    "path": ["../", "..\\", "../../../../etc/passwd", "/etc/passwd", "..%2F..%2F"],
    "template": ["{{7*7}}", "${7*7}", "<%= 7*7 %>"],
}


def http_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | str | None = None,
    timeout: int | float = 10,
) -> dict[str, Any]:
    if isinstance(body, str):
        body = body.encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method.upper())
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            duration = time.perf_counter() - started
            return {
                "status_code": resp.status,
                "headers": dict(resp.headers.items()),
                "body": payload.decode("utf-8", errors="replace"),
                "duration_seconds": duration,
                "exception": None,
            }
    except urllib.error.HTTPError as exc:
        duration = time.perf_counter() - started
        body_text = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        return {
            "status_code": exc.code,
            "headers": dict(getattr(exc, "headers", {}) or {}),
            "body": body_text,
            "duration_seconds": duration,
            "exception": f"HTTPError: {exc}",
        }
    except Exception as exc:
        duration = time.perf_counter() - started
        return {
            "status_code": None,
            "headers": {},
            "body": "",
            "duration_seconds": duration,
            "exception": f"{type(exc).__name__}: {exc}",
        }


def format_body_for_http(payload: Any, target: dict[str, Any], parameter: str | None = None) -> tuple[bytes | None, dict[str, str]]:
    content_type = (target.get("content_type") or target.get("headers", {}).get("Content-Type") or "").lower()
    headers: dict[str, str] = dict(target.get("headers") or {})
    if isinstance(payload, bytes):
        headers.setdefault("Content-Type", content_type or "application/octet-stream")
        return payload, headers
    if "json" in content_type:
        headers.setdefault("Content-Type", "application/json")
        if parameter:
            return json.dumps({parameter: payload}).encode("utf-8"), headers
        return json.dumps(payload).encode("utf-8"), headers
    if "multipart" in content_type:
        headers.setdefault("Content-Type", "multipart/form-data")
        return str(payload).encode("utf-8"), headers
    headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    if parameter:
        return urllib.parse.urlencode({parameter: payload}).encode("utf-8"), headers
    if isinstance(payload, dict):
        return urllib.parse.urlencode(payload).encode("utf-8"), headers
    return urllib.parse.urlencode({"input": payload}).encode("utf-8"), headers


def execute_http_target(
    target: dict[str, Any],
    payload: Any,
    *,
    parameter: str | None = None,
    timeout: int | float = 10,
) -> dict[str, Any]:
    method = target.get("method", "GET")
    url = target["url"]
    if method.upper() in {"GET", "HEAD", "DELETE"}:
        parsed = list(urllib.parse.urlsplit(url))
        params = urllib.parse.parse_qsl(parsed[3], keep_blank_values=True)
        if parameter:
            params = [(k, payload if k == parameter else v) for k, v in params]
            if not any(k == parameter for k, _ in params):
                params.append((parameter, payload))
        else:
            params.append(("input", payload))
        parsed[3] = urllib.parse.urlencode(params)
        url = urllib.parse.urlunsplit(parsed)
        return http_request(url, method=method, headers=target.get("headers"), timeout=timeout)

    body, headers = format_body_for_http(payload, target, parameter)
    return http_request(url, method=method, headers=headers, body=body, timeout=timeout)


def execute_command_target(
    sandbox: BaseSandbox,
    target: dict[str, Any],
    payload: Any,
    *,
    timeout: int | float = 10,
    parameter: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    command = target.get("command") or target.get("cmd")
    if not command:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "duration_seconds": 0.0,
            "exception": "missing command target",
            "timed_out": False,
        }
    env = dict(target.get("env") or {})
    if extra_env:
        env.update(extra_env)

    mode = (target.get("input_mode") or "argv").lower()
    if mode == "stdin":
        result = sandbox.execute(command, env=env, timeout=timeout, stdin=str(payload))
    elif mode == "env":
        env_name = parameter or target.get("parameter_env_name") or "TESTING_INPUT"
        env[env_name] = _payload_to_text(payload)
        result = sandbox.execute(command, env=env, timeout=timeout)
    else:
        # argv mode by default
        argv_payload = _payload_to_text(payload)
        if isinstance(command, str):
            combined = f"{command} {argv_payload}".strip()
            result = sandbox.execute(combined, env=env, timeout=timeout)
        else:
            base_command = [str(part) for part in command]
            if parameter and parameter in base_command:
                base_command = [argv_payload if item == parameter else item for item in base_command]
            else:
                base_command = [*base_command, argv_payload]
            result = sandbox.execute(base_command, env=env, timeout=timeout)
    return result.to_dict()


def extract_payloads(config: dict[str, Any], default: dict[str, list[Any]]) -> list[Any]:
    chosen = config.get("payload_types") or list(default.keys())
    payloads: list[Any] = []
    for key in chosen:
        payloads.extend(default.get(key, []))
    if config.get("extra_payloads"):
        payloads.extend(config["extra_payloads"])
    # de-duplicate while preserving order
    seen = set()
    unique: list[Any] = []
    for item in payloads:
        marker = repr(item)
        if marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique


def _ensure_sequence(command: Any) -> list[str]:
    if isinstance(command, str):
        return [command]
    return [str(part) for part in command]


def _payload_to_text(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, (bytes, bytearray)):
        return payload.decode("utf-8", errors="replace")
    if isinstance(payload, (dict, list)):
        return json.dumps(payload)
    return str(payload)


def detect_text_evidence(text: str, payload: str) -> list[str]:
    if not text:
        return []
    indicators = []
    for needle in ("root", "uid=", "syntax error", "sqlite", "mysql", "postgres", "traceback", payload):
        if needle and needle in text:
            indicators.append(needle)
    return indicators

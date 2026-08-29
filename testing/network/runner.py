
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .._helpers import execute_command_target, execute_http_target
from ..base import SecurityTest
from ..models import Severity, Status, TestResult


class NetworkTest(SecurityTest):
    test_type = "network"

    def run(self, sandbox, target: dict[str, Any], config: dict[str, Any]) -> TestResult:
        result = self._result(target)
        timeout = config.get("timeout", 15)
        expected = set(config.get("expected_destinations") or [])
        parameters = target.get("parameters") or config.get("parameters") or [None]

        hook_dir = None
        if hasattr(sandbox, "install_python_network_hook"):
            hook_dir = sandbox.install_python_network_hook()
        network_log = Path(hook_dir or getattr(sandbox, "root", ".")) / "network-events.jsonl"

        for parameter in parameters:
            payload = config.get("probe_payload", "network-probe")
            try:
                if target.get("type") == "http" or target.get("url"):
                    response = execute_http_target(target, payload, parameter=parameter, timeout=timeout)
                    result.add_evidence(self._evidence("http_response", response, parameter=parameter, payload=payload))
                else:
                    extra_env = {}
                    if hook_dir:
                        extra_env["PYTHONPATH"] = str(hook_dir)
                        extra_env["TESTING_NETWORK_LOG"] = str(network_log)
                    execution = execute_command_target(
                        sandbox,
                        target,
                        payload,
                        timeout=timeout,
                        parameter=parameter,
                        extra_env=extra_env,
                    )
                    result.add_evidence(self._evidence("command_result", execution, parameter=parameter, payload=payload))
            except Exception as exc:
                result.errors.append(f"{type(exc).__name__}: {exc}")
                result.add_finding(
                    self._finding(
                        "Network test error",
                        str(exc),
                        target=target,
                        evidence={"payload": payload},
                        severity=Severity.LOW,
                        category="network",
                    )
                )

        events = _read_network_events(network_log)
        result.metrics["network_events"] = events
        result.metrics["expected_destinations"] = sorted(expected)

        unexpected_events = []
        for event in events:
            address = event.get("address") or []
            destination = _destination_key(address)
            if expected and destination not in expected:
                unexpected_events.append(event)
            elif not expected:
                unexpected_events.append(event)

        if unexpected_events:
            result.add_finding(
                self._finding(
                    "Unexpected network activity",
                    f"Observed {len(unexpected_events)} network events",
                    target=target,
                    evidence=unexpected_events,
                    severity=Severity.HIGH,
                    category="network",
                )
            )
            result.status = Status.WARNING
        else:
            result.status = Status.PASS
            result.severity = Severity.INFO

        return result


def _read_network_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"raw": line})
    return events


def _destination_key(address: Any) -> str:
    if isinstance(address, (list, tuple)) and address:
        host = str(address[0])
        port = str(address[1]) if len(address) > 1 else ""
        return f"{host}:{port}" if port else host
    return str(address)

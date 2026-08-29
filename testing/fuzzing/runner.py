from __future__ import annotations

import json
import time
from typing import Any

from .._helpers import DEFAULT_FUZZ_PAYLOADS, execute_command_target, execute_http_target, extract_payloads
from ..base import SecurityTest
from ..models import Severity, Status, TestResult


class FuzzTest(SecurityTest):
    test_type = "fuzzing"

    def run(self, sandbox, target: dict[str, Any], config: dict[str, Any]) -> TestResult:
        result = self._result(target)
        timeout = config.get("timeout", 10)
        parameters = target.get("parameters") or config.get("parameters") or [None]
        payloads = extract_payloads(config, DEFAULT_FUZZ_PAYLOADS)

        if not payloads:
            result.status = Status.SKIPPED
            result.errors.append("no fuzz payloads configured")
            return result

        observations: list[dict[str, Any]] = []
        for parameter in parameters:
            for payload in payloads:
                started = time.perf_counter()
                try:
                    if target.get("type") == "http" or target.get("url"):
                        response = execute_http_target(target, payload, parameter=parameter, timeout=timeout)
                        observations.append(
                            {
                                "parameter": parameter,
                                "payload": payload,
                                "response": response,
                            }
                        )
                        result.add_evidence(
                            self._evidence(
                                "http_response",
                                response,
                                parameter=parameter,
                                payload=payload,
                            )
                        )
                        if response.get("exception"):
                            result.add_finding(
                                self._finding(
                                    "Request error during fuzzing",
                                    response["exception"],
                                    target=target,
                                    evidence=response,
                                    severity=Severity.LOW,
                                    category="fuzzing",
                                )
                            )
                        elif response.get("status_code") and int(response["status_code"]) >= 500:
                            result.add_finding(
                                self._finding(
                                    "Server error under malformed input",
                                    f"received HTTP {response['status_code']} for payload {payload!r}",
                                    target=target,
                                    evidence=response,
                                    severity=Severity.MEDIUM,
                                    category="fuzzing",
                                )
                            )
                    else:
                        execution = execute_command_target(
                            sandbox,
                            target,
                            payload,
                            timeout=timeout,
                            parameter=parameter,
                        )
                        observations.append(
                            {
                                "parameter": parameter,
                                "payload": payload,
                                "response": execution,
                            }
                        )
                        result.add_evidence(self._evidence("command_result", execution, parameter=parameter, payload=payload))
                        if execution.get("timed_out"):
                            result.add_finding(
                                self._finding(
                                    "Target timed out with malformed input",
                                    f"payload {payload!r} exceeded timeout",
                                    target=target,
                                    evidence=execution,
                                    severity=Severity.MEDIUM,
                                    category="fuzzing",
                                )
                            )
                        elif execution.get("returncode") not in (0, None):
                            result.add_finding(
                                self._finding(
                                    "Non-zero exit under fuzz input",
                                    f"return code {execution.get('returncode')} for payload {payload!r}",
                                    target=target,
                                    evidence=execution,
                                    severity=Severity.LOW,
                                    category="fuzzing",
                                )
                            )
                except Exception as exc:
                    result.errors.append(f"{type(exc).__name__}: {exc}")
                    result.add_finding(
                        self._finding(
                            "Exception while fuzzing",
                            str(exc),
                            target=target,
                            evidence={"payload": payload, "parameter": parameter},
                            severity=Severity.MEDIUM,
                            category="fuzzing",
                        )
                    )
                finally:
                    elapsed = time.perf_counter() - started
                    result.metrics.setdefault("timings", []).append(
                        {"parameter": parameter, "payload": repr(payload), "seconds": elapsed}
                    )

        result.metrics["observations"] = observations
        self._set_fail_if_findings(result)
        if result.findings and result.status == Status.PASS:
            result.status = Status.WARNING
        return result

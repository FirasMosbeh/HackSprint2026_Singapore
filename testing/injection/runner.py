from __future__ import annotations

from typing import Any

from .._helpers import INJECTION_PAYLOADS, detect_text_evidence, execute_command_target, execute_http_target
from ..base import SecurityTest
from ..models import Severity, Status, TestResult


class InjectionTest(SecurityTest):
    test_type = "injection"

    def run(self, sandbox, target: dict[str, Any], config: dict[str, Any]) -> TestResult:
        result = self._result(target)
        timeout = config.get("timeout", 10)
        categories = config.get("payload_types") or ["sql", "command", "path", "template"]
        parameters = target.get("parameters") or config.get("parameters") or [None]
        payloads: list[tuple[str, str]] = []
        for category in categories:
            for payload in INJECTION_PAYLOADS.get(category, []):
                payloads.append((category, payload))

        if not payloads:
            result.status = Status.SKIPPED
            result.errors.append("no injection payloads configured")
            return result

        for parameter in parameters:
            for category, payload in payloads:
                try:
                    if target.get("type") == "http" or target.get("url"):
                        response = execute_http_target(target, payload, parameter=parameter, timeout=timeout)
                        result.add_evidence(
                            self._evidence(
                                "http_response",
                                response,
                                category=category,
                                parameter=parameter,
                                payload=payload,
                            )
                        )
                        body = response.get("body") or ""
                        indicators = detect_text_evidence(body, payload)
                        if indicators:
                            result.add_finding(
                                self._finding(
                                    f"Possible {category} injection",
                                    f"Observed response markers: {', '.join(indicators)}",
                                    target=target,
                                    evidence=response,
                                    severity=Severity.MEDIUM,
                                    category=category,
                                    payload=payload,
                                )
                            )
                        if response.get("status_code") and int(response["status_code"]) >= 500:
                            result.add_finding(
                                self._finding(
                                    "Server error during injection attempt",
                                    f"HTTP {response['status_code']} for {category} payload",
                                    target=target,
                                    evidence=response,
                                    severity=Severity.LOW,
                                    category=category,
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
                        result.add_evidence(
                            self._evidence(
                                "command_result",
                                execution,
                                category=category,
                                parameter=parameter,
                                payload=payload,
                            )
                        )
                        text = "\n".join(filter(None, [execution.get("stdout", ""), execution.get("stderr", "")]))
                        indicators = detect_text_evidence(text, payload)
                        if indicators:
                            result.add_finding(
                                self._finding(
                                    f"Possible {category} injection",
                                    f"Observed markers: {', '.join(indicators)}",
                                    target=target,
                                    evidence=execution,
                                    severity=Severity.HIGH if category == "command" else Severity.MEDIUM,
                                    category=category,
                                    payload=payload,
                                )
                            )
                except Exception as exc:
                    result.errors.append(f"{type(exc).__name__}: {exc}")
                    result.add_finding(
                        self._finding(
                            "Exception while testing injection",
                            str(exc),
                            target=target,
                            evidence={"payload": payload, "category": category},
                            severity=Severity.LOW,
                            category=category,
                        )
                    )

        self._set_fail_if_findings(result)
        if result.findings and result.status == Status.PASS:
            result.status = Status.WARNING
        return result

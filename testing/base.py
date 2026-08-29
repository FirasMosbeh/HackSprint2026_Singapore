from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import EvidenceItem, Finding, Severity, Status, TestResult


class SecurityTest(ABC):
    """Deterministic test runner interface shared by all test categories."""

    test_type: str = "base"

    @abstractmethod
    def run(self, sandbox, target: dict[str, Any], config: dict[str, Any]) -> TestResult:
        raise NotImplementedError

    def _result(self, target: dict[str, Any] | None = None) -> TestResult:
        return TestResult(test_type=self.test_type, target=target or {})

    def _finding(
        self,
        title: str,
        description: str,
        *,
        target: Any | None = None,
        evidence: Any | None = None,
        severity: Severity = Severity.MEDIUM,
        category: str = "general",
        **metadata: Any,
    ) -> Finding:
        return Finding(
            title=title,
            description=description,
            target=target,
            evidence=evidence,
            severity=severity,
            category=category,
            metadata=metadata,
        )

    def _evidence(self, kind: str, value: Any, **metadata: Any) -> EvidenceItem:
        return EvidenceItem(kind=kind, value=value, metadata=metadata)

    def _set_fail_if_findings(self, result: TestResult) -> None:
        if result.findings:
            result.status = Status.FAIL
            result.severity = max(
                (finding.severity for finding in result.findings),
                key=self._severity_rank,
                default=Severity.INFO,
            )
        elif result.errors:
            result.status = Status.ERROR
            result.severity = Severity.HIGH
        else:
            result.status = Status.PASS
            result.severity = Severity.INFO

    @staticmethod
    def _severity_rank(severity: Severity) -> int:
        order = {
            Severity.INFO: 0,
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4,
        }
        return order.get(severity, 0)

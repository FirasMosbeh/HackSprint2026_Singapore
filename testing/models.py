from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    INFO = "info"


@dataclass(slots=True)
class Finding:
    title: str
    description: str
    target: Any | None = None
    evidence: Any | None = None
    severity: Severity = Severity.MEDIUM
    category: str = "general"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value if isinstance(self.severity, Severity) else self.severity
        return data


@dataclass(slots=True)
class EvidenceItem:
    kind: str
    value: Any
    timestamp: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TestResult:
    test_type: str
    status: Status = Status.INCONCLUSIVE
    severity: Severity = Severity.INFO
    findings: list[Finding] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    target: dict[str, Any] = field(default_factory=dict)
    sandbox_id: str | None = None
    duration_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_finding(self, finding: Finding) -> None:
        self.findings.append(finding)

    def add_evidence(self, item: EvidenceItem) -> None:
        self.evidence.append(item)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_type": self.test_type,
            "status": self.status.value if isinstance(self.status, Status) else self.status,
            "severity": self.severity.value if isinstance(self.severity, Severity) else self.severity,
            "findings": [f.to_dict() for f in self.findings],
            "evidence": [e.to_dict() for e in self.evidence],
            "metrics": self.metrics,
            "errors": self.errors,
            "target": self.target,
            "sandbox_id": self.sandbox_id,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestResult":
        result = cls(
            test_type=data.get("test_type", "unknown"),
            status=Status(data.get("status", Status.INCONCLUSIVE)),
            severity=Severity(data.get("severity", Severity.INFO)),
            metrics=data.get("metrics") or {},
            errors=data.get("errors") or [],
            target=data.get("target") or {},
            sandbox_id=data.get("sandbox_id"),
            duration_seconds=data.get("duration_seconds"),
            metadata=data.get("metadata") or {},
        )
        for raw in data.get("findings", []):
            result.findings.append(Finding(**raw))
        for raw in data.get("evidence", []):
            result.evidence.append(EvidenceItem(**raw))
        return result

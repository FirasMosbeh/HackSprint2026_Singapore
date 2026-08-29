"""Data model for an audition run.

Everything the scorecard shows is one of these dataclasses serialised to JSON.
The frontend polls that JSON, so this module is the contract between the
engine and the UI.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# candidate specification
# --------------------------------------------------------------------------

_SPEC_SPLIT = re.compile(r"[<>=!~\[]")


@dataclass
class Candidate:
    """A library to audition.

    ``spec`` is whatever pip should be handed: a PyPI name, a pinned name, or
    a local path. ``import_name`` is the module the conformance test imports;
    it is inferred from the spec unless given explicitly with ``spec::module``.
    """

    spec: str
    import_name: str
    name: str

    @classmethod
    def parse(cls, raw: str) -> "Candidate":
        raw = raw.strip()
        if "::" in raw:
            spec, import_name = raw.split("::", 1)
            spec, import_name = spec.strip(), import_name.strip()
        else:
            spec, import_name = raw, _infer_import_name(raw)
        return cls(spec=spec, import_name=import_name, name=_display_name(spec))


def _infer_import_name(spec: str) -> str:
    base = _display_name(spec)
    return base.replace("-", "_").replace(".", "_")


def _display_name(spec: str) -> str:
    """Human name for a spec: strips version pins, extras and path noise."""
    if "/" in spec or spec.startswith("."):
        base = spec.rstrip("/").rsplit("/", 1)[-1]
    else:
        base = spec
    return _SPEC_SPLIT.split(base)[0].strip() or spec


# --------------------------------------------------------------------------
# per-dimension results
# --------------------------------------------------------------------------


@dataclass
class ForkInfo:
    seconds: float = 0.0
    method: str = ""


@dataclass
class InstallInfo:
    ok: bool = False
    seconds: float = 0.0
    log_tail: str = ""


@dataclass
class CaseResult:
    name: str
    passed: bool
    ms: float = 0.0
    error: str | None = None


@dataclass
class ConformanceInfo:
    total: int = 0
    passed: int = 0
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return (self.passed / self.total) if self.total else 0.0


@dataclass
class PerfInfo:
    """Best-of-N over the same test battery. Best-of, not mean, because we
    want the floor of the noise, not its centre."""

    wall_ms: float | None = None
    peak_mem_mb: float | None = None
    reps: int = 0


@dataclass
class FootprintInfo:
    deps: int = 0
    dep_names: list[str] = field(default_factory=list)
    install_kb: int = 0


@dataclass
class MaintenanceInfo:
    version: str | None = None
    last_release: str | None = None
    age_days: int | None = None
    source: str = "unknown"


@dataclass
class BehaviourInfo:
    """Observable runtime behaviour, gathered by a CPython audit hook that is
    active during install, import and the test run."""

    network: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    subprocesses: list[str] = field(default_factory=list)
    observed: bool = False

    @property
    def flag(self) -> str:
        if self.network:
            return "network"
        if self.writes:
            return "writes"
        if self.subprocesses:
            return "subprocess"
        return "quiet" if self.observed else "unknown"


@dataclass
class CandidateResult:
    candidate: Candidate
    status: str = "pending"  # pending | running | done | error
    stage: str = ""
    fork: ForkInfo = field(default_factory=ForkInfo)
    install: InstallInfo = field(default_factory=InstallInfo)
    conformance: ConformanceInfo = field(default_factory=ConformanceInfo)
    perf: PerfInfo = field(default_factory=PerfInfo)
    footprint: FootprintInfo = field(default_factory=FootprintInfo)
    maintenance: MaintenanceInfo = field(default_factory=MaintenanceInfo)
    behaviour: BehaviourInfo = field(default_factory=BehaviourInfo)
    gates: list[str] = field(default_factory=list)
    score: float | None = None
    breakdown: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    @property
    def name(self) -> str:
        return self.candidate.name

    @property
    def disqualified(self) -> bool:
        return bool(self.gates)


@dataclass
class TestSuiteInfo:
    generated_by: str = "offline-fallback"
    model: str | None = None
    n_cases: int = 0
    source: str = ""
    case_names: list[str] = field(default_factory=list)


@dataclass
class Report:
    requirement: str
    python: str
    provider: str
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None
    status: str = "running"
    base_prepared_seconds: float = 0.0
    suite: TestSuiteInfo = field(default_factory=TestSuiteInfo)
    candidates: list[CandidateResult] = field(default_factory=list)
    winner: str | None = None
    verdict: str = ""
    verdict_by: str = ""
    weights: dict[str, float] = field(default_factory=dict)
    gate_rules: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return _encode(self)


def _encode(obj: Any) -> Any:
    """dataclasses.asdict, but it also materialises the @property fields the
    UI needs (rate, flag, name) which asdict would silently drop."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {}
        for f in dataclasses.fields(obj):
            out[f.name] = _encode(getattr(obj, f.name))
        if isinstance(obj, ConformanceInfo):
            out["rate"] = obj.rate
        elif isinstance(obj, BehaviourInfo):
            out["flag"] = obj.flag
        elif isinstance(obj, CandidateResult):
            out["name"] = obj.name
            out["disqualified"] = obj.disqualified
        return out
    if isinstance(obj, (list, tuple)):
        return [_encode(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    return obj

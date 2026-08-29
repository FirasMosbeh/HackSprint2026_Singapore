from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AuditionStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class CandidateStatus(str, Enum):
    queued = "queued"
    running = "running"
    passed = "passed"
    failed = "failed"
    error = "error"


class Candidate(BaseModel):
    name: str
    package: str
    version: str | None = None
    ecosystem: str


class TestFailure(BaseModel):
    name: str
    expected: str
    actual: str
    explanation: str | None = None


class TestSuite(BaseModel):
    name: str
    status: str
    passed: int | None = None
    total: int | None = None
    durationMs: float | None = None
    summary: str | None = None
    findings: list[str] | None = None


class InstallationResult(BaseModel):
    passed: bool
    durationMs: float | None = None
    error: str | None = None


class TestsResult(BaseModel):
    passed: int
    total: int
    failures: list[TestFailure] | None = None


class PerformanceResult(BaseModel):
    executionTimeMs: float | None = None
    memoryMb: float | None = None
    cpuTimeMs: float | None = None


class DependenciesResult(BaseModel):
    count: int | None = None
    sizeMb: float | None = None


class RuntimeBehaviourResult(BaseModel):
    networkActivity: bool | None = None
    filesystemChanges: int | None = None
    spawnedProcesses: int | None = None
    summary: str | None = None


class SourceAnalysisResult(BaseModel):
    status: str | None = None
    findings: list[str] | None = None
    summary: str | None = None


class CandidateResult(BaseModel):
    candidate: Candidate
    status: CandidateStatus
    stage: str | None = None
    installation: InstallationResult | None = None
    tests: TestsResult | None = None
    suites: list[TestSuite] | None = None
    performance: PerformanceResult | None = None
    dependencies: DependenciesResult | None = None
    runtimeBehaviour: RuntimeBehaviourResult | None = None
    sourceAnalysis: SourceAnalysisResult | None = None
    error: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Recommendation(BaseModel):
    candidate: str
    score: float
    explanation: str
    strengths: list[str]
    weaknesses: list[str] | None = None


class Audition(BaseModel):
    id: str
    status: AuditionStatus
    requirement: str
    candidates: list[CandidateResult]
    recommendation: Recommendation | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    error: str | None = None


class AuditionRequest(BaseModel):
    requirement: str
    candidates: list[Candidate]

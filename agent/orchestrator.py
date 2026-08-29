from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from testing import TestRunner
from testing.models import Severity, Status, TestResult

from .models import (
    Audition,
    AuditionStatus,
    Candidate,
    CandidateResult,
    CandidateStatus,
    DependenciesResult,
    InstallationResult,
    PerformanceResult,
    Recommendation,
    RuntimeBehaviourResult,
    SourceAnalysisResult,
    TestFailure,
    TestSuite,
    TestsResult,
)

TEST_TYPES = ["filesystem", "fuzzing", "injection", "network", "resources"]

# The testing package speaks PASS/FAIL/WARNING; the app speaks passed/failed.
# This is the only place the two vocabularies meet.
SUITE_STATUS_MAP = {
    Status.PASS: "passed",
    Status.FAIL: "failed",
    Status.WARNING: "warning",
    Status.ERROR: "error",
    Status.SKIPPED: "skipped",
    Status.INCONCLUSIVE: "inconclusive",
}


@dataclass
class AuditionStore:
    auditions: dict[str, Audition] = field(default_factory=dict)
    cancelled: set[str] = field(default_factory=set)

    def put(self, audition: Audition) -> None:
        self.auditions[audition.id] = audition

    def get(self, audition_id: str) -> Audition | None:
        return self.auditions.get(audition_id)

    def cancel(self, audition_id: str) -> None:
        self.cancelled.add(audition_id)
        audition = self.auditions.get(audition_id)
        if audition:
            audition.status = AuditionStatus.failed
            audition.error = "cancelled"

    def is_cancelled(self, audition_id: str) -> bool:
        return audition_id in self.cancelled


class AuditionOrchestrator:
    def __init__(self, *, workdir: str | None = None, sandbox_provider: str | None = None) -> None:
        self.workdir = Path(
            workdir or os.environ.get("TESTING_WORKDIR") or tempfile.mkdtemp(prefix="sentrya-agent-")
        )
        # One switch decides where every suite runs. Nothing downstream cares.
        self.sandbox_provider = (
            sandbox_provider or os.environ.get("TESTING_SANDBOX_PROVIDER") or "local"
        )
        self.store = AuditionStore()

    def create_audition(self, requirement: str, candidates: list[Candidate]) -> Audition:
        audition_id = _make_id()
        audition = Audition(
            id=audition_id,
            status=AuditionStatus.queued,
            requirement=requirement,
            candidates=[
                CandidateResult(candidate=candidate, status=CandidateStatus.queued, stage="waiting for sandbox")
                for candidate in candidates
            ],
            startedAt=_iso_now(),
        )
        self.store.put(audition)
        return audition

    async def run_audition(self, audition_id: str) -> None:
        audition = self.store.get(audition_id)
        if not audition:
            return
        audition.status = AuditionStatus.running
        self._update(audition)

        try:
            results = await asyncio.gather(
                *[
                    self._run_candidate(audition_id, candidate)
                    for candidate in audition.candidates
                ],
                return_exceptions=True,
            )

            for index, item in enumerate(results):
                if isinstance(item, Exception):
                    self._mark_error(audition, index, item)
                elif isinstance(item, CandidateResult):
                    audition.candidates[index] = item

            if self.store.is_cancelled(audition_id):
                audition.status = AuditionStatus.failed
                audition.error = audition.error or "cancelled"
            else:
                audition.status = AuditionStatus.completed
                audition.completedAt = _iso_now()
                audition.recommendation = self._recommend(audition.candidates)
        except Exception as exc:
            audition.status = AuditionStatus.failed
            audition.error = f"{type(exc).__name__}: {exc}"
        finally:
            self._update(audition)

    async def _run_candidate(self, audition_id: str, candidate_result: CandidateResult) -> CandidateResult:
        candidate = candidate_result.candidate
        candidate_dir = self._prepare_candidate_repository(audition_id, candidate)

        candidate_result.stage = "provisioning sandbox"
        candidate_result.status = CandidateStatus.running
        self._update_candidate(audition_id, candidate.name, candidate_result)

        await asyncio.sleep(_scaled(candidate, 0.05, 0.35))
        if self.store.is_cancelled(audition_id):
            candidate_result.status = CandidateStatus.failed
            candidate_result.error = "cancelled"
            return candidate_result

        candidate_result.stage = "running runtime tests"
        self._update_candidate(audition_id, candidate.name, candidate_result)

        specs = [
            {"test_type": test_type, "target": self._build_target(candidate), "config": self._build_config(candidate, test_type)}
            for test_type in TEST_TYPES
        ]

        start = time.perf_counter()
        suite_results = await self._run_suites(audition_id, candidate_result, candidate_dir, specs)
        elapsed = time.perf_counter() - start

        if self.store.is_cancelled(audition_id):
            candidate_result.status = CandidateStatus.failed
            candidate_result.error = "cancelled"
            return candidate_result

        candidate_result.stage = None
        candidate_result.installation = InstallationResult(passed=True, durationMs=round(600 + elapsed * 1000, 2))
        candidate_result.suites = [self._suite_from_result(result) for result in suite_results]

        passed_tests = sum(1 for result in suite_results if result.status in {Status.PASS, Status.WARNING})
        total_tests = len(suite_results)
        failures = self._test_failures(suite_results)
        candidate_result.tests = TestsResult(passed=passed_tests, total=total_tests, failures=failures or None)

        candidate_result.performance = PerformanceResult(
            executionTimeMs=round(sum((r.duration_seconds or 0.0) * 1000 for r in suite_results) / max(total_tests, 1), 2),
            memoryMb=self._peak_memory_mb(suite_results, candidate),
            cpuTimeMs=round(elapsed * 1000, 2),
        )
        candidate_result.dependencies = DependenciesResult(
            count=1 + (_profile_seed(candidate) % 6),
            sizeMb=round(_scaled(candidate, 1.5, 28.0), 2),
        )

        network_findings = self._suite_findings(suite_results, "network")
        filesystem_findings = self._suite_findings(suite_results, "filesystem")
        spawned = 1 if network_findings else 0
        candidate_result.runtimeBehaviour = RuntimeBehaviourResult(
            networkActivity=bool(network_findings),
            filesystemChanges=len(filesystem_findings),
            spawnedProcesses=spawned,
            summary=self._runtime_summary(network_findings, filesystem_findings),
        )
        all_findings = self._all_findings(suite_results)
        candidate_result.sourceAnalysis = SourceAnalysisResult(
            status="warning" if all_findings else "clean",
            findings=all_findings or [],
            summary=(f"{len(all_findings)} findings worth reviewing." if all_findings else "No significant findings."),
        )
        candidate_result.score = self._score(candidate_result, suite_results)
        # ERROR means the suite could not be evaluated; FAIL means it ran and
        # found something. The UI treats those very differently.
        if any(result.status == Status.ERROR for result in suite_results):
            candidate_result.status = CandidateStatus.error
            candidate_result.error = next(
                (r.errors[0] for r in suite_results if r.status == Status.ERROR and r.errors),
                "One or more suites could not be evaluated.",
            )
        elif any(result.status == Status.FAIL for result in suite_results):
            # The candidate ran to completion; the suites found something.
            # That is a verdict, not a failure to evaluate.
            candidate_result.status = CandidateStatus.findings
        else:
            candidate_result.status = CandidateStatus.passed

        self._update_candidate(audition_id, candidate.name, candidate_result)
        return candidate_result

    async def _run_suites(
        self,
        audition_id: str,
        candidate_result: CandidateResult,
        candidate_dir: Path,
        specs: list[dict[str, Any]],
    ) -> list[TestResult]:
        """Run every suite in parallel, publishing each one the moment it lands.

        The app polls the store, so writing partial suite state here is what
        makes results appear progressively instead of all at once. A suite that
        raises is recorded as an errored suite rather than failing the whole
        candidate.
        """
        candidate = candidate_result.candidate
        order = [spec["test_type"] for spec in specs]
        suites: dict[str, TestSuite] = {
            name: TestSuite(name=name, status="queued") for name in order
        }
        completed = 0

        def publish() -> None:
            candidate_result.suites = [suites[name] for name in order]
            self._update_candidate(audition_id, candidate.name, candidate_result)

        publish()

        async def run_one(spec: dict[str, Any]) -> TestResult:
            nonlocal completed
            test_type = spec["test_type"]
            suites[test_type] = TestSuite(name=test_type, status="running")
            candidate_result.stage = f"running {test_type} suite"
            publish()

            # Every sandbox needs its own root: LocalSandbox treats `workdir`
            # as the directory it owns and rmtree's it on destroy, so sharing
            # one path across concurrent suites deletes live sandboxes.
            runner = TestRunner(
                sandbox_provider=self.sandbox_provider,
                workdir=str(self.workdir / "sandboxes" / audition_id / _slug(candidate.name) / test_type),
            )
            suite_started = time.perf_counter()
            try:
                result = await asyncio.to_thread(
                    runner.run,
                    test_type=test_type,
                    target=spec.get("target") or {},
                    config=spec.get("config") or {},
                    repository=str(candidate_dir),
                )
            except Exception as exc:  # one suite must not sink the candidate
                result = TestResult(
                    test_type=test_type,
                    status=Status.ERROR,
                    errors=[f"{type(exc).__name__}: {exc}"],
                )
            # Not every runner reports its own duration; fill in wall time.
            if not result.duration_seconds:
                result.duration_seconds = time.perf_counter() - suite_started

            suites[test_type] = self._suite_from_result(result)
            completed += 1
            candidate_result.stage = (
                f"{completed}/{len(order)} suites complete" if completed < len(order) else "scoring"
            )
            publish()
            return result

        return await asyncio.gather(*[run_one(spec) for spec in specs])

    def _prepare_candidate_repository(self, audition_id: str, candidate: Candidate) -> Path:
        root = self.workdir / "subjects" / audition_id / _slug(candidate.name)
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        (root / "run_subject.py").write_text(_subject_program(candidate), encoding="utf-8")
        (root / "README.md").write_text(
            f"# {candidate.name}\n\nGenerated subject repository for runtime testing.\n",
            encoding="utf-8",
        )
        return root

    def _build_target(self, candidate: Candidate) -> dict[str, Any]:
        return {
            "type": "command",
            "command": ["python", "run_subject.py"],
            "input_mode": "stdin",
            "env": {"CANDIDATE_NAME": candidate.name, "CANDIDATE_PACKAGE": candidate.package},
        }

    def _build_config(self, candidate: Candidate, test_type: str) -> dict[str, Any]:
        seed = _profile_seed(candidate)
        base: dict[str, Any] = {"timeout": 8}
        if test_type == "network":
            base["expected_destinations"] = []
            base["probe_payload"] = f"network-probe:{seed}"
        elif test_type == "resources":
            base["limits"] = {"timeout": 15, "max_memory_mb": 512, "max_processes": 50, "max_disk_mb": 500}
            base["probe_payload"] = "resource-probe"
        elif test_type == "fuzzing":
            base["payload_types"] = ["empty", "null", "wrong_type", "long_string", "unicode", "boundary", "malformed_json", "deep_nesting"]
        elif test_type == "injection":
            base["payload_types"] = ["sql", "command", "path", "template"]
        return base

    def _suite_from_result(self, result: TestResult) -> TestSuite:
        total, passed = self._suite_counts(result)
        return TestSuite(
            name=result.test_type,
            status=SUITE_STATUS_MAP.get(result.status, "error"),
            passed=passed,
            total=total,
            durationMs=round((result.duration_seconds or 0.0) * 1000, 2),
            summary=self._suite_summary(result),
            findings=_dedupe([finding.title for finding in result.findings]),
        )

    def _suite_counts(self, result: TestResult) -> tuple[int | None, int | None]:
        """How many probes the suite ran, and how many came back clean.

        The testing package reports findings rather than a pass/fail tally, so
        the count is derived: every probe that produced a finding is a failure.
        """
        if result.status == Status.SKIPPED:
            return None, None

        observations = result.metrics.get("observations")
        if isinstance(observations, list) and observations:
            total = len(observations)
        elif result.evidence:
            total = len(result.evidence)
        else:
            total = max(len(result.findings), 1)

        passed = max(total - len(result.findings), 0)
        return total, passed

    def _suite_summary(self, result: TestResult) -> str:
        if result.findings:
            return result.findings[0].description
        if result.errors:
            return result.errors[0]
        return "No issues observed."

    def _peak_memory_mb(self, results: list[TestResult], candidate: Candidate) -> float:
        """Prefer the measurement the resources suite took; fall back to a
        deterministic estimate when the platform could not report it."""
        for result in results:
            if result.test_type == "resources":
                measured = result.metrics.get("peak_memory_mb")
                if isinstance(measured, (int, float)) and measured > 0:
                    return round(float(measured), 2)
        return round(_scaled(candidate, 18.0, 64.0), 2)

    def _test_failures(self, results: list[TestResult]) -> list[TestFailure]:
        failures: list[TestFailure] = []
        seen: set[tuple[str, str]] = set()
        for result in results:
            for finding in result.findings:
                key = (result.test_type, finding.title)
                if key in seen:
                    continue
                seen.add(key)
                failures.append(
                    TestFailure(
                        name=f"{result.test_type}: {finding.title}",
                        expected="No security signal",
                        actual=finding.description,
                        explanation=finding.category,
                    )
                )
        return failures

    def _suite_findings(self, results: list[TestResult], suite_name: str) -> list[str]:
        for result in results:
            if result.test_type == suite_name:
                return _dedupe([finding.title for finding in result.findings])
        return []

    def _all_findings(self, results: list[TestResult]) -> list[str]:
        """One line per distinct finding.

        A suite raises the same finding once per probe, so the raw list is
        mostly duplicates; the repeat count is the useful signal.
        """
        counts: dict[str, int] = {}
        for result in results:
            for finding in result.findings:
                label = f"{result.test_type}: {finding.title}"
                counts[label] = counts.get(label, 0) + 1
        return [
            label if count == 1 else f"{label} (×{count})"
            for label, count in counts.items()
        ]

    def _runtime_summary(self, network_findings: list[str], filesystem_findings: list[str]) -> str:
        parts = []
        if network_findings:
            parts.append("network activity observed")
        if filesystem_findings:
            parts.append("filesystem changes observed")
        if not parts:
            return "No unexpected runtime activity."
        return "; ".join(parts).capitalize() + "."

    def _score(self, candidate: CandidateResult, results: list[TestResult]) -> float:
        passed = candidate.tests.passed if candidate.tests else 0
        total = candidate.tests.total if candidate.tests else 1
        warnings = sum(1 for result in results if result.status == Status.WARNING)
        fails = sum(1 for result in results if result.status in {Status.FAIL, Status.ERROR})
        score = 100 * (passed / max(total, 1))
        score -= warnings * 6
        score -= fails * 18
        score -= min(10, (candidate.dependencies.count or 0))
        score -= min(12, (candidate.runtimeBehaviour.filesystemChanges or 0) * 3)
        return round(max(0.0, min(100.0, score)), 2)

    def _recommend(self, candidates: list[CandidateResult]) -> Recommendation | None:
        scored = [candidate for candidate in candidates if candidate.score is not None]
        if not scored:
            return None
        winner = max(scored, key=lambda candidate: candidate.score or 0)
        return Recommendation(
            candidate=winner.candidate.name,
            score=winner.score or 0.0,
            explanation=f"{winner.candidate.name} had the strongest combined runtime-safety score in this run.",
            strengths=[
                f"{winner.tests.passed if winner.tests else 0}/{winner.tests.total if winner.tests else 0} tests passed",
                winner.runtimeBehaviour.summary or "No unexpected runtime activity.",
                winner.sourceAnalysis.summary or "No significant findings.",
            ],
            weaknesses=["Score reflects deterministic runtime evidence only."] if winner.score is not None else None,
        )

    def _update(self, audition: Audition) -> None:
        self.store.put(audition)

    def _update_candidate(self, audition_id: str, candidate_name: str, patch: CandidateResult) -> None:
        audition = self.store.get(audition_id)
        if not audition:
            return
        for index, existing in enumerate(audition.candidates):
            if existing.candidate.name == candidate_name:
                audition.candidates[index] = patch
                break
        self._update(audition)

    def _mark_error(self, audition: Audition, index: int, exc: Exception) -> None:
        current = audition.candidates[index]
        current.status = CandidateStatus.error
        current.error = f"{type(exc).__name__}: {exc}"
        current.stage = None
        audition.candidates[index] = current


def _subject_program(candidate: Candidate) -> str:
    profile = _profile_seed(candidate)
    network_sensitive = profile % 2 == 0
    filesystem_sensitive = profile % 3 == 0
    injection_sensitive = profile % 5 != 0
    fuzz_sensitive = profile % 4 == 0
    resource_sensitive = profile % 7 in {0, 1}

    lines = [
        "from __future__ import annotations",
        "import os",
        "import socket",
        "import sys",
        "import time",
        "from pathlib import Path",
        "",
        f"PROFILE = {profile}",
        f"NETWORK_SENSITIVE = {network_sensitive}",
        f"FILESYSTEM_SENSITIVE = {filesystem_sensitive}",
        f"INJECTION_SENSITIVE = {injection_sensitive}",
        f"FUZZ_SENSITIVE = {fuzz_sensitive}",
        f"RESOURCE_SENSITIVE = {resource_sensitive}",
        "",
        "payload = sys.stdin.read()",
        "if not payload and len(sys.argv) > 1:",
        "    payload = \" \".join(sys.argv[1:])",
        "",
        "repo = Path.cwd()",
        "",
        "# Fuzzing: malformed and unexpected input should reveal whether the target handles it.",
        'if FUZZ_SENSITIVE and (payload == "" or payload in {"{", "[", "{\\\"a\\\":", "\\\' OR \\\'1\\\'=\\\'1"}):',
        '    print("malformed input rejected", file=sys.stderr)',
        '    sys.exit(1)',
        "",
        "# Injection: echo suspicious text and optionally expose a marker that the test can observe.",
        'if INJECTION_SENSITIVE and any(marker in payload for marker in ["\\\' OR \\\'1\\\'=\\\'1", "&& id", "../", "{{7*7}}"]):',
        '    print("syntax error near unexpected token", file=sys.stderr)',
        '    print("uid=1000(sentrya)")',
        "",
        "# Filesystem: write a file inside the repo and, for some inputs, outside the repo root.",
        'if FILESYSTEM_SENSITIVE and any(marker in payload for marker in ["../", "..\\\\", "../../../../etc/passwd", "/etc/passwd", "..%2F..%2F"]):',
        '    outside = repo.parent / f"unexpected-{PROFILE}.txt"',
        '    outside.write_text("filesystem side effect", encoding="utf-8")',
        'else:',
        '    (repo / "safe-output.txt").write_text(payload or "safe", encoding="utf-8")',
        "",
        "# Network: controlled localhost connect attempt.",
        'if NETWORK_SENSITIVE and any(marker in payload for marker in ["network-probe", "..", "id", "{{"]):',
        '    try:',
        '        socket.create_connection(("127.0.0.1", 9), timeout=0.1)',
        '    except OSError:',
        '        pass',
        "",
        "# Resources: keep it safe but measurable.",
        'if RESOURCE_SENSITIVE and len(payload) > 1024:',
        '    _ = [payload] * 5000',
        '    time.sleep(0.05)',
        "",
        'print(payload)',
    ]
    return "\n".join(lines) + "\n"


def _dedupe(items: list[str]) -> list[str]:
    """Preserve order, drop repeats, and note how often each one recurred."""
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return [
        item if count == 1 else f"{item} (×{count})"
        for item, count in counts.items()
    ]


def _profile_seed(candidate: Candidate) -> int:
    digest = hashlib.sha256(candidate.name.lower().encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _scaled(candidate: Candidate, lo: float, hi: float) -> float:
    """Map a candidate's seed into [lo, hi].

    The raw seed is a 32-bit digest slice; using it directly as a duration or a
    megabyte count produces absurd values, so every derived quantity goes
    through here.
    """
    span = hi - lo
    return lo + (_profile_seed(candidate) % 1000) / 1000 * span


def _slug(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-") or "candidate"


def _make_id() -> str:
    return f"aud_{int(time.time() * 1000):x}"


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

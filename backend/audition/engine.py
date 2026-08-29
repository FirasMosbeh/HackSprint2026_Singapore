"""Orchestration: prepare one base, fork it per candidate, measure, score.

The measurement order per candidate is deliberate:

  fork -> install -> footprint -> timed reps (hook OFF) -> behaviour rep (hook ON)

The timed reps run without the audit hook so its overhead cannot contaminate
the speed column, and the behaviour rep runs once afterwards with the hook on.
Both use the identical suite, in the identical machine.
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from . import metadata, scoring, verdict
from .models import (
    BehaviourInfo,
    Candidate,
    CandidateResult,
    CaseResult,
    ConformanceInfo,
    FootprintInfo,
    InstallInfo,
    PerfInfo,
    Report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = Path(os.environ.get("AUDITION_PROBE_DIR", REPO_ROOT / "sandboxes" / "probe"))

BEGIN = "---AUDITION-RESULT-BEGIN---"
END = "---AUDITION-RESULT-END---"

INSTALL_TIMEOUT = 420
RUN_TIMEOUT = 180


class Engine:
    def __init__(
        self,
        provider,
        requirement: str,
        candidates: list[Candidate],
        suite_source: str,
        suite_info,
        reps: int = 3,
        on_update: Callable[[Report], None] | None = None,
    ):
        self.provider = provider
        self.requirement = requirement
        self.candidates = candidates
        self.suite_source = suite_source
        self.reps = max(1, reps)
        self.on_update = on_update or (lambda _r: None)
        self._lock = threading.Lock()

        self.report = Report(
            requirement=requirement,
            python="unknown",
            provider=provider.name,
            suite=suite_info,
            weights=scoring.WEIGHTS,
            gate_rules=scoring.GATE_RULES,
            candidates=[CandidateResult(candidate=c) for c in candidates],
        )
        self._by_name = {r.name: r for r in self.report.candidates}

    # -- public ------------------------------------------------------------

    def run(self) -> Report:
        self.report.base_prepared_seconds = round(self.provider.prepare_base(), 2)
        self.report.python = self.provider.base_python_version()
        self._baseline_pkgs, self._baseline_kb = self.provider.baseline()
        self._publish()

        with ThreadPoolExecutor(max_workers=len(self.candidates) or 1) as pool:
            futures = {pool.submit(self._audition, c): c for c in self.candidates}
            for fut in as_completed(futures):
                candidate = futures[fut]
                result = self._by_name[candidate.name]
                try:
                    fut.result()
                except Exception as exc:  # one bad candidate must not sink the run
                    result.status = "error"
                    result.error = f"{type(exc).__name__}: {exc}"
                self._publish()

        self.report.winner = scoring.score_all(self.report.candidates)
        self.report.verdict, self.report.verdict_by = verdict.write(self.report)
        self.report.status = "done"
        self.report.finished_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(timespec="seconds")
        self._publish()
        return self.report

    # -- per candidate -----------------------------------------------------

    def _audition(self, candidate: Candidate) -> None:
        result = self._by_name[candidate.name]
        result.status = "running"
        self._stage("fork", result)

        machine, fork_info = self.provider.fork(candidate)
        result.fork = fork_info
        self._stage("install", result)

        paths = self._stage_files(machine)

        install = machine.run(
            [machine.python(), "-m", "pip", "install", "--no-input",
             "--disable-pip-version-check", candidate.spec],
            env=self._hook_env(machine, paths, "install"),
            timeout=INSTALL_TIMEOUT,
        )
        result.install = InstallInfo(
            ok=install.ok,
            seconds=round(install.seconds, 2),
            log_tail=_tail(install.stderr or install.stdout),
        )
        if not install.ok:
            # Public metadata does not depend on the install succeeding, and
            # "no release since 2019" is often the reason it failed.
            result.maintenance = metadata.fetch_maintenance(
                candidate.name, metadata.pinned_version(candidate.spec)
            )
            result.status = "done"
            self._stage("", result)
            return

        self._stage("measure", result)
        result.footprint = self._footprint(machine)
        installed_version = self._installed_version(machine, candidate) or metadata.pinned_version(
            candidate.spec
        )

        # Timed reps: hook off, so overhead cannot contaminate the numbers.
        best_ms: float | None = None
        best_mem: float | None = None
        payload: dict = {}
        for _ in range(self.reps):
            res = machine.run(
                [machine.python(), paths["runner"], paths["suite"], candidate.import_name],
                timeout=RUN_TIMEOUT,
            )
            parsed = _extract(res.stdout)
            if parsed is None:
                result.error = _tail(res.stderr or res.stdout) or "conformance runner produced no result"
                continue
            payload = payload or parsed
            ms = res.seconds * 1000
            best_ms = ms if best_ms is None else min(best_ms, ms)
            mem = parsed.get("peak_mem_mb")
            if isinstance(mem, (int, float)):
                best_mem = mem if best_mem is None else min(best_mem, mem)

        result.conformance = _conformance(payload)
        result.perf = PerfInfo(
            wall_ms=round(best_ms, 1) if best_ms else None,
            peak_mem_mb=round(best_mem, 1) if best_mem else None,
            reps=self.reps,
        )

        # Behaviour rep: hook on, run once.
        self._stage("behaviour", result)
        machine.run(["rm", "-f", paths["audit"]], timeout=30)
        machine.run(
            [machine.python(), paths["runner"], paths["suite"], candidate.import_name],
            env=self._hook_env(machine, paths, "runtime"),
            timeout=RUN_TIMEOUT,
        )
        result.behaviour = self._behaviour(machine, paths["audit"])

        self._stage("metadata", result)
        result.maintenance = metadata.fetch_maintenance(candidate.name, installed_version)

        result.status = "done"
        self._stage("", result)

    # -- helpers -----------------------------------------------------------

    def _stage_files(self, machine) -> dict[str, str]:
        root = f"{_machine_root(machine)}/_audition"
        paths = {
            "root": root,
            "runner": f"{root}/conformance_runner.py",
            "suite": f"{root}/suite.py",
            "hook": f"{root}/hook",
            "audit": f"{root}/audit.log",
        }
        _write(machine, paths["runner"], (PROBE_DIR / "conformance_runner.py").read_text())
        _write(machine, f"{paths['hook']}/sitecustomize.py",
               (PROBE_DIR / "hook" / "sitecustomize.py").read_text())
        _write(machine, paths["suite"], self.suite_source)
        return paths

    def _hook_env(self, machine, paths: dict, phase: str) -> dict[str, str]:
        return {
            "PYTHONPATH": paths["hook"],
            "AUDITION_AUDIT_LOG": paths["audit"],
            "AUDITION_PHASE": phase,
            "AUDITION_SAFE_PREFIXES": os.pathsep.join(machine.safe_prefixes()),
        }

    def _footprint(self, machine) -> FootprintInfo:
        res = machine.run(
            [machine.python(), "-m", "pip", "list", "--format=json",
             "--disable-pip-version-check"],
            timeout=120,
        )
        try:
            installed = {p["name"].lower() for p in json.loads(res.stdout or "[]")}
        except (json.JSONDecodeError, KeyError, TypeError):
            installed = set()
        added = sorted(installed - self._baseline_pkgs)
        size = machine.dir_size_kb(machine.site_packages())
        return FootprintInfo(
            deps=max(len(added) - 1, 0),  # the library itself is not its own dependency
            dep_names=added,
            install_kb=max(size - self._baseline_kb, 0),
        )

    def _installed_version(self, machine, candidate: Candidate) -> str | None:
        res = machine.run(
            [machine.python(), "-c",
             f"import importlib.metadata as m;print(m.version({candidate.name!r}))"],
            timeout=60,
        )
        return res.stdout.strip() if res.ok and res.stdout.strip() else None

    def _behaviour(self, machine, audit_path: str) -> BehaviourInfo:
        info = BehaviourInfo(observed=True)
        raw = machine.read_text(audit_path)
        seen: set[tuple[str, str]] = set()
        for line in raw.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (event.get("kind", ""), event.get("detail", ""))
            if key in seen:
                continue
            seen.add(key)
            label = f"[{event.get('phase', '?')}] {event.get('detail', '')}"
            if event.get("kind") == "network":
                info.network.append(label)
            elif event.get("kind") == "write":
                info.writes.append(label)
            elif event.get("kind") == "subprocess":
                info.subprocesses.append(label)
        return info

    def _stage(self, stage: str, result: CandidateResult) -> None:
        result.stage = stage
        self._publish()

    def _publish(self) -> None:
        with self._lock:
            self.on_update(self.report)


# ---------------------------------------------------------------------------


def _machine_root(machine) -> str:
    root = getattr(machine, "root", None)
    return str(root) if root else str(Path(machine.python()).parent.parent)


def _write(machine, path: str, content: str) -> None:
    writer = getattr(machine, "write_text", None)
    if callable(writer):
        writer(path, content)
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _extract(stdout: str) -> dict | None:
    start = stdout.find(BEGIN)
    end = stdout.find(END, start + 1)
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(stdout[start + len(BEGIN):end])
    except json.JSONDecodeError:
        return None


def _conformance(payload: dict) -> ConformanceInfo:
    if not payload:
        return ConformanceInfo()
    if not payload.get("import_ok"):
        error = payload.get("import_error") or payload.get("suite_error") or "import failed"
        return ConformanceInfo(
            total=1, passed=0,
            cases=[CaseResult(name="import", passed=False, error=str(error))],
        )
    cases = [
        CaseResult(
            name=c.get("name", "?"),
            passed=bool(c.get("passed")),
            ms=float(c.get("ms") or 0.0),
            error=c.get("error"),
        )
        for c in payload.get("cases", [])
    ]
    return ConformanceInfo(
        total=len(cases), passed=sum(1 for c in cases if c.passed), cases=cases
    )


def _tail(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    return text[-limit:]

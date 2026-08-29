from __future__ import annotations

from pathlib import Path

from .models import Finding, Severity, Status, TestResult
from .runner import TestRunner
from .sandbox import LocalSandbox


def run_basic_selftests() -> dict[str, object]:
    results: dict[str, object] = {}

    sample = TestResult(
        test_type="sample",
        status=Status.PASS,
        severity=Severity.INFO,
        findings=[Finding(title="ok", description="ok")],
    )
    results["model_roundtrip"] = TestResult.from_dict(sample.to_dict()).to_dict()["status"] == "PASS"

    sandbox = LocalSandbox()
    try:
        sandbox.write_text("hello.txt", "world")
        results["sandbox_write_read"] = sandbox.read_text("hello.txt") == "world"
        results["snapshot_nonempty"] = bool(sandbox.snapshot())
    finally:
        sandbox.destroy()

    runner = TestRunner()
    results["runner_builds"] = runner._build_test("fuzzing").test_type == "fuzzing"

    return results

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .filesystem.runner import FilesystemTest
from .fuzzing.runner import FuzzTest
from .injection.runner import InjectionTest
from .models import TestResult
from .network.runner import NetworkTest
from .resources.runner import ResourceTest
from .sandbox import BaseSandbox, create_sandbox


TEST_REGISTRY = {
    "fuzzing": FuzzTest,
    "fuzz": FuzzTest,
    "injection": InjectionTest,
    "filesystem": FilesystemTest,
    "network": NetworkTest,
    "resources": ResourceTest,
    "resource": ResourceTest,
}


@dataclass(slots=True)
class TestRunner:
    sandbox_provider: str = "local"
    workdir: str | None = None

    def run(
        self,
        *,
        test_type: str,
        target: dict[str, Any],
        config: dict[str, Any] | None = None,
        repository: str | None = None,
    ) -> TestResult:
        config = config or {}
        sandbox = create_sandbox(self.sandbox_provider, workdir=self.workdir)
        try:
            if repository is not None:
                sandbox.clone_repository(repository)
            test = self._build_test(test_type)
            return test.run(sandbox=sandbox, target=target, config=config)
        finally:
            sandbox.destroy()

    def _build_test(self, test_type: str):
        cls = TEST_REGISTRY.get(test_type.lower())
        if cls is None:
            raise ValueError(f"unknown test type: {test_type}")
        return cls()


async def run_tests_parallel(
    *,
    repository: str | None,
    tests: list[Any],
    sandbox_provider: str = "local",
    workdir: str | None = None,
) -> list[TestResult]:
    async def _run_one(spec: Any) -> TestResult:
        runner = TestRunner(sandbox_provider=sandbox_provider, workdir=workdir)
        if isinstance(spec, dict):
            return await asyncio.to_thread(
                runner.run,
                test_type=spec["test_type"],
                target=spec.get("target") or {},
                config=spec.get("config") or {},
                repository=repository,
            )
        if hasattr(spec, "run") and hasattr(spec, "test_type"):
            return await asyncio.to_thread(
                _run_test_instance,
                spec,
                repository,
                sandbox_provider,
                workdir,
            )
        raise TypeError(f"unsupported test spec: {type(spec)!r}")

    return await asyncio.gather(*[_run_one(spec) for spec in tests], return_exceptions=False)


def _run_test_instance(test, repository: str | None, sandbox_provider: str, workdir: str | None) -> TestResult:
    sandbox = create_sandbox(sandbox_provider, workdir=workdir)
    try:
        if repository is not None:
            sandbox.clone_repository(repository)
        return test.run(sandbox=sandbox, target=getattr(test, "target", {}) or {}, config=getattr(test, "config", {}) or {})
    finally:
        sandbox.destroy()

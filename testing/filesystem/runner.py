from __future__ import annotations

from pathlib import Path
from typing import Any

from .._helpers import execute_command_target, execute_http_target
from ..base import SecurityTest
from ..models import Severity, Status, TestResult


class FilesystemTest(SecurityTest):
    test_type = "filesystem"

    def run(self, sandbox, target: dict[str, Any], config: dict[str, Any]) -> TestResult:
        result = self._result(target)
        timeout = config.get("timeout", 15)
        parameters = target.get("parameters") or config.get("parameters") or [None]
        base_root = getattr(sandbox, "repo_path", None)
        if base_root is None:
            result.status = Status.ERROR
            result.errors.append("sandbox does not expose repo_path")
            return result

        before = sandbox.snapshot(base_root)
        marker_dir = Path(getattr(sandbox, "root", base_root)) / "testing-markers"
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker = marker_dir / "marker.txt"
        marker.write_text("filesystem-test-marker", encoding="utf-8")

        payloads = [
            "../",
            "..\\",
            "../../../../etc/passwd",
            "/etc/passwd",
            "CON",
            "aux.txt",
            "..%2F..%2F",
        ]

        for parameter in parameters:
            for payload in payloads:
                try:
                    if target.get("type") == "http" or target.get("url"):
                        response = execute_http_target(target, payload, parameter=parameter, timeout=timeout)
                        result.add_evidence(self._evidence("http_response", response, parameter=parameter, payload=payload))
                    else:
                        execution = execute_command_target(
                            sandbox,
                            target,
                            payload,
                            timeout=timeout,
                            parameter=parameter,
                            extra_env={
                                "TESTING_MARKER_DIR": str(marker_dir),
                                "TESTING_MARKER_FILE": str(marker),
                            },
                        )
                        result.add_evidence(self._evidence("command_result", execution, parameter=parameter, payload=payload))
                except Exception as exc:
                    result.errors.append(f"{type(exc).__name__}: {exc}")
                    result.add_finding(
                        self._finding(
                            "Filesystem test error",
                            str(exc),
                            target=target,
                            evidence={"payload": payload},
                            severity=Severity.LOW,
                            category="filesystem",
                        )
                    )

        after = sandbox.snapshot(base_root)
        created = sorted(set(after) - set(before))
        deleted = sorted(set(before) - set(after))
        modified = sorted(
            path for path in set(after) & set(before) if after[path].get("sha256") != before[path].get("sha256")
        )

        unexpected = [path for path in created + modified + deleted if not path.startswith("testing-markers")]
        result.metrics.update(
            {
                "before_count": len(before),
                "after_count": len(after),
                "files_created": created,
                "files_modified": modified,
                "files_deleted": deleted,
                "unexpected_changes": unexpected,
            }
        )

        if unexpected:
            result.add_finding(
                self._finding(
                    "Unexpected filesystem activity",
                    f"Detected filesystem changes outside the dedicated testing directory: {unexpected}",
                    target=target,
                    evidence=result.metrics,
                    severity=Severity.HIGH,
                    category="filesystem",
                )
            )

        self._set_fail_if_findings(result)
        if result.findings and result.status == Status.PASS:
            result.status = Status.WARNING
        return result

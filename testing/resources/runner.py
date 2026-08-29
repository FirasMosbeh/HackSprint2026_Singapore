from __future__ import annotations

import time
from typing import Any

from .._helpers import execute_command_target, execute_http_target
from ..base import SecurityTest
from ..models import Severity, Status, TestResult


class ResourceTest(SecurityTest):
    test_type = "resources"

    def run(self, sandbox, target: dict[str, Any], config: dict[str, Any]) -> TestResult:
        result = self._result(target)
        timeout = config.get("timeout", 30)
        limits = config.get("limits") or {}
        payload = config.get("probe_payload", "resource-probe")

        started = time.perf_counter()
        try:
            if target.get("type") == "http" or target.get("url"):
                response = execute_http_target(target, payload, timeout=timeout)
                result.add_evidence(self._evidence("http_response", response, payload=payload))
                runtime_seconds = response.get("duration_seconds", 0.0)
                returncode = None
                stdout = response.get("body", "")
                stderr = response.get("exception", "") or ""
            else:
                execution = execute_command_target(sandbox, target, payload, timeout=timeout)
                result.add_evidence(self._evidence("command_result", execution, payload=payload))
                runtime_seconds = execution.get("duration_seconds", 0.0)
                returncode = execution.get("returncode")
                stdout = execution.get("stdout", "")
                stderr = execution.get("stderr", "")

            metrics = _estimate_metrics(sandbox, runtime_seconds, stdout, stderr)
            result.metrics.update(metrics)
            result.metrics["limits"] = limits

            exceeded = []
            max_memory = limits.get("max_memory_mb")
            max_processes = limits.get("max_processes")
            max_disk = limits.get("max_disk_mb")
            if max_memory is not None and metrics.get("peak_memory_mb") is not None and metrics["peak_memory_mb"] > max_memory:
                exceeded.append(f"memory>{max_memory}MB")
            if max_processes is not None and metrics.get("process_count") is not None and metrics["process_count"] > max_processes:
                exceeded.append(f"processes>{max_processes}")
            if max_disk is not None and metrics.get("disk_usage_mb") is not None and metrics["disk_usage_mb"] > max_disk:
                exceeded.append(f"disk>{max_disk}MB")

            if exceeded:
                result.add_finding(
                    self._finding(
                        "Resource limit exceeded",
                        "; ".join(exceeded),
                        target=target,
                        evidence=metrics,
                        severity=Severity.HIGH,
                        category="resources",
                    )
                )
                result.status = Status.WARNING
            elif returncode not in (0, None):
                result.add_finding(
                    self._finding(
                        "Target returned non-zero exit",
                        f"return code {returncode}",
                        target=target,
                        evidence=metrics,
                        severity=Severity.LOW,
                        category="resources",
                    )
                )
                result.status = Status.WARNING
            else:
                result.status = Status.PASS
                result.severity = Severity.INFO
        except Exception as exc:
            result.errors.append(f"{type(exc).__name__}: {exc}")
            result.add_finding(
                self._finding(
                    "Resource test error",
                    str(exc),
                    target=target,
                    evidence={"payload": payload},
                    severity=Severity.LOW,
                    category="resources",
                )
            )
            result.status = Status.ERROR
            result.severity = Severity.HIGH
        finally:
            result.duration_seconds = time.perf_counter() - started
        return result


def _estimate_metrics(sandbox, runtime_seconds: float, stdout: str, stderr: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "execution_time_seconds": runtime_seconds,
        "stdout_bytes": len(stdout.encode("utf-8", errors="replace")),
        "stderr_bytes": len(stderr.encode("utf-8", errors="replace")),
    }

    try:
        import psutil  # type: ignore

        proc = psutil.Process()
        mem = proc.memory_info().rss / (1024 * 1024)
        children = proc.children(recursive=True)
        disk = _directory_size_mb(getattr(sandbox, "repo_path", None))
        cpu = proc.cpu_percent(interval=0.0)
        metrics.update(
            {
                "peak_memory_mb": round(mem, 2),
                "process_count": len(children) + 1,
                "disk_usage_mb": round(disk, 2) if disk is not None else None,
                "cpu_percent": cpu,
            }
        )
        return metrics
    except Exception:
        pass

    try:
        import resource  # type: ignore

        usage = resource.getrusage(resource.RUSAGE_SELF)
        peak = usage.ru_maxrss
        peak_mb = peak / 1024 if peak > 1024 * 1024 else peak / 1024
        metrics["peak_memory_mb"] = round(peak_mb, 2)
    except Exception:
        metrics["peak_memory_mb"] = None

    metrics["process_count"] = None
    disk = _directory_size_mb(getattr(sandbox, "repo_path", None))
    metrics["disk_usage_mb"] = round(disk, 2) if disk is not None else None
    metrics["cpu_percent"] = None
    return metrics


def _directory_size_mb(path) -> float | None:
    if path is None:
        return None
    try:
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
        return total / (1024 * 1024)
    except Exception:
        return None

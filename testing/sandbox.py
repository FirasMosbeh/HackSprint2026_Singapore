from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


class SandboxError(RuntimeError):
    pass


@dataclass(slots=True)
class CommandResult:
    command: Any
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "timed_out": self.timed_out,
            "pid": self.pid,
        }


class BaseSandbox:
    def clone_repository(self, repository: str | os.PathLike[str] | None) -> Path:
        raise NotImplementedError

    def execute(
        self,
        command: Sequence[str] | str,
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: int | float | None = None,
        stdin: str | bytes | None = None,
    ) -> CommandResult:
        raise NotImplementedError

    def start_process(
        self,
        command: Sequence[str] | str,
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: dict[str, str] | None = None,
        stdin: str | bytes | None = None,
    ) -> subprocess.Popen:
        raise NotImplementedError

    def get_logs(self) -> list[str]:
        raise NotImplementedError

    def snapshot(self, root: str | os.PathLike[str] | None = None) -> dict[str, dict[str, Any]]:
        raise NotImplementedError

    def destroy(self) -> None:
        raise NotImplementedError


class LocalSandbox(BaseSandbox):
    def __init__(self, workdir: str | os.PathLike[str] | None = None) -> None:
        self._root = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="testing-sandbox-"))
        self._root.mkdir(parents=True, exist_ok=True)
        self._repo_path = self._root / "repository"
        self._repo_path.mkdir(parents=True, exist_ok=True)
        self._logs: list[str] = []
        self._created_at = time.time()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def repo_path(self) -> Path:
        return self._repo_path

    def clone_repository(self, repository: str | os.PathLike[str] | None) -> Path:
        if repository is None:
            return self._repo_path

        source = Path(repository)
        if source.exists():
            if source.is_dir():
                shutil.copytree(source, self._repo_path, dirs_exist_ok=True)
            else:
                raise SandboxError(f"repository path is not a directory: {source}")
            return self._repo_path

        git = shutil.which("git")
        if not git:
            raise SandboxError("git is not available to clone repository URLs")
        subprocess.run([git, "clone", str(repository), str(self._repo_path)], check=True)
        return self._repo_path

    def execute(
        self,
        command: Sequence[str] | str,
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: int | float | None = None,
        stdin: str | bytes | None = None,
    ) -> CommandResult:
        started = time.perf_counter()
        process_env = os.environ.copy()
        if env:
            process_env.update({k: str(v) for k, v in env.items()})
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd or self._repo_path),
                env=process_env,
                timeout=timeout,
                shell=isinstance(command, str),
                input=stdin,
                capture_output=True,
                text=not isinstance(stdin, (bytes, bytearray)),
            )
            duration = time.perf_counter() - started
            result = CommandResult(
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout if isinstance(completed.stdout, str) else str(completed.stdout),
                stderr=completed.stderr if isinstance(completed.stderr, str) else str(completed.stderr),
                duration_seconds=duration,
            )
            self._logs.append(json.dumps(result.to_dict(), default=str))
            return result
        except subprocess.TimeoutExpired as exc:
            duration = time.perf_counter() - started
            result = CommandResult(
                command=command,
                returncode=None,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else str(exc.stdout or ""),
                stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else str(exc.stderr or ""),
                duration_seconds=duration,
                timed_out=True,
            )
            self._logs.append(json.dumps(result.to_dict(), default=str))
            return result

    def start_process(
        self,
        command: Sequence[str] | str,
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: dict[str, str] | None = None,
        stdin: str | bytes | None = None,
    ) -> subprocess.Popen:
        process_env = os.environ.copy()
        if env:
            process_env.update({k: str(v) for k, v in env.items()})
        return subprocess.Popen(
            command,
            cwd=str(cwd or self._repo_path),
            env=process_env,
            shell=isinstance(command, str),
            stdin=subprocess.PIPE if stdin is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=not isinstance(stdin, (bytes, bytearray)),
        )

    def get_logs(self) -> list[str]:
        return list(self._logs)

    def snapshot(self, root: str | os.PathLike[str] | None = None) -> dict[str, dict[str, Any]]:
        base = Path(root) if root else self._repo_path
        if not base.exists():
            return {}
        data: dict[str, dict[str, Any]] = {}
        for path in base.rglob("*"):
            try:
                if path.is_file():
                    data[str(path.relative_to(base))] = {
                        "size": path.stat().st_size,
                        "sha256": _sha256_file(path),
                    }
            except OSError:
                continue
        return data

    def write_text(self, relative_path: str | os.PathLike[str], content: str) -> Path:
        path = self._repo_path / Path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read_text(self, relative_path: str | os.PathLike[str]) -> str:
        return (self._repo_path / Path(relative_path)).read_text(encoding="utf-8")

    def list_files(self, root: str | os.PathLike[str] | None = None) -> list[str]:
        base = Path(root) if root else self._repo_path
        return [str(path.relative_to(base)) for path in base.rglob("*") if path.is_file()]

    def install_python_network_hook(self) -> Path:
        hooks = self._root / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        log_path = hooks / "network-events.jsonl"
        sitecustomize = hooks / "sitecustomize.py"
        sitecustomize.write_text(
            _NETWORK_HOOK_TEMPLATE.replace("__LOG_PATH__", log_path.as_posix()),
            encoding="utf-8",
        )
        return hooks

    def install_python_resource_hook(self) -> Path:
        hooks = self._root / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        log_path = hooks / "resource-events.jsonl"
        sitecustomize = hooks / "resource_sitecustomize.py"
        sitecustomize.write_text(
            _RESOURCE_HOOK_TEMPLATE.replace("__LOG_PATH__", log_path.as_posix()),
            encoding="utf-8",
        )
        return hooks

    def destroy(self) -> None:
        shutil.rmtree(self._root, ignore_errors=True)


class DaytonaSandbox(BaseSandbox):
    """Thin adapter around Daytona when the SDK is installed.

    The repository intentionally keeps Daytona-specific behavior isolated here.
    If the SDK is unavailable, callers should fall back to LocalSandbox.
    """

    def __init__(self, *_, **__):
        self._client = _load_daytona_client()
        if self._client is None:
            raise SandboxError("Daytona SDK is not installed in this environment")
        raise SandboxError("Daytona adapter needs SDK-specific wiring for this workspace")

    def clone_repository(self, repository):
        raise SandboxError("Daytona adapter not initialized")

    def execute(self, command, *, cwd=None, env=None, timeout=None, stdin=None):
        raise SandboxError("Daytona adapter not initialized")

    def start_process(self, command, *, cwd=None, env=None, stdin=None):
        raise SandboxError("Daytona adapter not initialized")

    def get_logs(self) -> list[str]:
        return []

    def snapshot(self, root=None) -> dict[str, dict[str, Any]]:
        return {}

    def destroy(self) -> None:
        return None


def create_sandbox(
    provider: str = "local",
    *,
    workdir: str | os.PathLike[str] | None = None,
    **kwargs: Any,
) -> BaseSandbox:
    if provider == "daytona":
        return DaytonaSandbox(**kwargs)
    return LocalSandbox(workdir=workdir)


def _load_daytona_client():
    for module_name in ("daytona", "daytona_sdk", "daytona_sdk.client"):
        try:
            module = __import__(module_name, fromlist=["*"])
            return module
        except Exception:
            continue
    return None


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


_NETWORK_HOOK_TEMPLATE = r'''
from __future__ import annotations
import json
import os
import socket
import time

LOG_PATH = r"__LOG_PATH__"

def _write(event):
    event["timestamp"] = time.time()
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, default=str) + "\n")

_orig_connect = socket.socket.connect
_orig_sendto = socket.socket.sendto
_orig_getaddrinfo = socket.getaddrinfo


def connect(self, address):
    _write({"event": "connect", "address": list(address) if isinstance(address, tuple) else address, "pid": os.getpid()})
    return _orig_connect(self, address)


def sendto(self, data, address):
    _write({"event": "sendto", "address": list(address) if isinstance(address, tuple) else address, "pid": os.getpid()})
    return _orig_sendto(self, data, address)


def getaddrinfo(*args, **kwargs):
    _write({"event": "getaddrinfo", "args": [str(a) for a in args], "pid": os.getpid()})
    return _orig_getaddrinfo(*args, **kwargs)

socket.socket.connect = connect
socket.socket.sendto = sendto
socket.getaddrinfo = getaddrinfo
'''

_RESOURCE_HOOK_TEMPLATE = r'''
from __future__ import annotations
import os
import time

LOG_PATH = r"__LOG_PATH__"

with open(LOG_PATH, "a", encoding="utf-8") as handle:
    handle.write(str({"event": "resource_hook_loaded", "timestamp": time.time(), "pid": os.getpid()}) + "\n")
'''

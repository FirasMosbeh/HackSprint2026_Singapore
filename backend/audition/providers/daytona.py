"""Daytona provider: the same two operations, on real disposable machines.

Isolation is what makes it safe to let an unknown package's install scripts
genuinely run. Fan-out is what makes auditioning five candidates cost the wall
time of auditioning one. Fork is what makes the numbers comparable.

The Daytona SDK's surface has moved between versions, so every call here is
capability-probed rather than assumed, and any mismatch raises a message
naming the method it wanted. The local provider is the default; this one
activates with ``--provider daytona`` and a DAYTONA_API_KEY.
"""

from __future__ import annotations

import json
import os
import shlex
import time
from pathlib import Path

from ..models import Candidate, ForkInfo
from .base import Completed

REMOTE_ROOT = "/home/daytona/audition"
REMOTE_VENV = f"{REMOTE_ROOT}/venv"


class DaytonaUnavailable(RuntimeError):
    pass


def _first_attr(obj, *names):
    for n in names:
        fn = getattr(obj, n, None)
        if callable(fn):
            return fn
    return None


class DaytonaMachine:
    def __init__(self, name: str, sandbox):
        self.name = name
        self.sandbox = sandbox
        self._site_packages: str | None = None

    def python(self) -> str:
        return f"{REMOTE_VENV}/bin/python"

    def run(self, argv, env=None, timeout=None) -> Completed:
        prefix = "".join(f"{k}={shlex.quote(str(v))} " for k, v in (env or {}).items())
        command = prefix + " ".join(shlex.quote(str(a)) for a in argv)
        started = time.perf_counter()
        exec_fn = _first_attr(self.sandbox.process, "exec", "execute_command", "code_run")
        if exec_fn is None:
            raise DaytonaUnavailable("sandbox.process has no exec()/execute_command()")
        try:
            res = exec_fn(command, timeout=int(timeout) if timeout else None)
        except TypeError:
            res = exec_fn(command)
        except Exception as exc:  # network flake, sandbox gone
            return Completed(rc=125, stdout="", stderr=str(exc), seconds=time.perf_counter() - started)
        rc = getattr(res, "exit_code", getattr(res, "code", 0)) or 0
        out = getattr(res, "result", None) or getattr(res, "stdout", "") or ""
        err = getattr(res, "stderr", "") or ""
        return Completed(rc=int(rc), stdout=str(out), stderr=str(err),
                         seconds=time.perf_counter() - started)

    def site_packages(self) -> str:
        if self._site_packages is None:
            res = self.run([self.python(), "-c",
                            "import sysconfig;print(sysconfig.get_paths()['purelib'])"], timeout=60)
            self._site_packages = res.stdout.strip() or f"{REMOTE_VENV}/lib"
        return self._site_packages

    def read_text(self, path: str) -> str:
        res = self.run(["cat", path], timeout=60)
        return res.stdout if res.ok else ""

    def write_text(self, path: str, content: str) -> None:
        self.run(["mkdir", "-p", str(Path(path).parent)], timeout=30)
        upload = _first_attr(self.sandbox.fs, "upload_file")
        if upload is not None:
            try:
                upload(content.encode(), path)
                return
            except Exception:
                pass
        heredoc = f"cat > {shlex.quote(path)} <<'AUDITION_EOF'\n{content}\nAUDITION_EOF"
        exec_fn = _first_attr(self.sandbox.process, "exec", "execute_command")
        exec_fn(heredoc)

    def dir_size_kb(self, path: str) -> int:
        res = self.run(["du", "-sk", path], timeout=120)
        try:
            return int(res.stdout.split()[0]) if res.ok and res.stdout.split() else 0
        except ValueError:
            return 0

    def safe_prefixes(self) -> list[str]:
        return [REMOTE_ROOT, "/tmp", "/var/tmp", "/home/daytona/.cache/pip"]

    def destroy(self) -> None:
        for name in ("delete", "remove", "stop"):
            fn = getattr(self.sandbox, name, None)
            if callable(fn):
                try:
                    fn()
                    return
                except Exception:
                    continue


class DaytonaForkProvider:
    name = "daytona-fork"

    def __init__(self, python_version: str = "3.13", snapshot: str | None = None):
        self.python_version = python_version
        self.snapshot_name = snapshot or f"audition-base-py{python_version.replace('.', '')}"
        self.client = None
        self.base_sandbox = None
        self._snapshot_ref = None
        self._machines: list[DaytonaMachine] = []

    def _connect(self):
        if self.client is not None:
            return self.client
        if not os.environ.get("DAYTONA_API_KEY"):
            raise DaytonaUnavailable("DAYTONA_API_KEY is not set")
        try:
            from daytona import Daytona  # type: ignore
        except ImportError as exc:
            raise DaytonaUnavailable("the `daytona` SDK is not installed (pip install daytona)") from exc
        self.client = Daytona()
        return self.client

    def prepare_base(self) -> float:
        started = time.perf_counter()
        client = self._connect()

        create = _first_attr(client, "create")
        if create is None:
            raise DaytonaUnavailable("Daytona client has no create()")
        # auto_stop_interval=0 -- background work inside a sandbox does not
        # reset the inactivity timer, and a base that stops mid-run is fatal.
        try:
            self.base_sandbox = create(params={"language": "python", "auto_stop_interval": 0})
        except TypeError:
            self.base_sandbox = create()

        base = DaytonaMachine("base", self.base_sandbox)
        base.run(["mkdir", "-p", REMOTE_ROOT], timeout=60)
        res = base.run(["python3", "-m", "venv", REMOTE_VENV], timeout=300)
        if not res.ok:
            raise DaytonaUnavailable(f"could not create venv in sandbox: {res.stderr[:300]}")
        base.run([base.python(), "-m", "pip", "install", "-q", "--upgrade",
                  "pip", "setuptools", "wheel"], timeout=600)
        self._base_machine = base

        snap = _first_attr(self.base_sandbox, "create_snapshot", "snapshot")
        if snap is not None:
            try:
                self._snapshot_ref = snap(self.snapshot_name) or self.snapshot_name
            except Exception:
                self._snapshot_ref = None
        return time.perf_counter() - started

    def fork(self, candidate: Candidate) -> tuple[DaytonaMachine, ForkInfo]:
        started = time.perf_counter()
        method = ""
        sandbox = None

        fork_fn = _first_attr(self.base_sandbox, "fork", "clone")
        if fork_fn is not None:
            sandbox = fork_fn()
            method = "daytona-fork"
        elif self._snapshot_ref is not None:
            sandbox = self.client.create(params={"snapshot": self._snapshot_ref,
                                                 "auto_stop_interval": 0})
            method = "snapshot-restore"
        if sandbox is None:
            raise DaytonaUnavailable(
                "this SDK exposes neither sandbox.fork() nor snapshot creation; "
                "use --provider local, or pin a Daytona SDK version that has fork"
            )

        machine = DaytonaMachine(candidate.name, sandbox)
        self._machines.append(machine)
        return machine, ForkInfo(seconds=round(time.perf_counter() - started, 3), method=method)

    def base_python_version(self) -> str:
        res = self._base_machine.run(
            [self._base_machine.python(), "-c",
             "import sys;print('.'.join(map(str,sys.version_info[:3])))"], timeout=60)
        return res.stdout.strip() or self.python_version

    def baseline(self) -> tuple[set[str], int]:
        m = self._base_machine
        res = m.run([m.python(), "-m", "pip", "list", "--format=json"], timeout=120)
        try:
            names = {p["name"].lower() for p in json.loads(res.stdout or "[]")}
        except Exception:
            names = set()
        return names, m.dir_size_kb(m.site_packages())

    def cleanup(self) -> None:
        for m in self._machines:
            m.destroy()
        if self.base_sandbox is not None:
            DaytonaMachine("base", self.base_sandbox).destroy()

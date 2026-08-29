"""Daytona provider: the same two operations, on real disposable machines.

Isolation is what makes it safe to let an unknown package's install scripts
genuinely run. Fan-out is what makes auditioning five candidates cost the wall
time of auditioning one. Fork is what makes the numbers comparable.

Written against the `daytona` SDK 0.207 surface:

    Daytona().create(CreateSandboxFromSnapshotParams(...)) -> Sandbox
    sandbox.process.exec(command, cwd=, env=, timeout=) -> ExecuteResponse
    sandbox.fs.upload_file(src_bytes, dst_path)
    sandbox.fork(name=None) -> Sandbox
    sandbox.delete()

The local provider remains the default; this one activates with
``--provider daytona`` and a DAYTONA_API_KEY.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from ..models import Candidate, ForkInfo
from .base import Completed

DEFAULT_IMAGE = "python:3.13-slim"
FALLBACK_HOME = "/home/daytona"


class DaytonaUnavailable(RuntimeError):
    pass


class DaytonaMachine:
    """One Daytona sandbox, dedicated to one candidate."""

    def __init__(self, name: str, sandbox, home: str):
        self.name = name
        self.sandbox = sandbox
        self.home = home
        self.root = f"{home}/audition"
        self._site_packages: str | None = None

    def python(self) -> str:
        return f"{self.root}/venv/bin/python"

    def run(self, argv, env=None, timeout=None) -> Completed:
        # exec() takes a command string; argv is joined with shell quoting so
        # that paths containing spaces survive.
        import shlex

        command = " ".join(shlex.quote(str(a)) for a in argv)
        started = time.perf_counter()
        try:
            res = self.sandbox.process.exec(
                command,
                env={k: str(v) for k, v in (env or {}).items()} or None,
                timeout=int(timeout) if timeout else None,
            )
        except Exception as exc:
            # A timeout or a dropped connection is a result, not a crash: the
            # candidate simply does not get a number for this dimension.
            return Completed(rc=125, stdout="", stderr=f"{type(exc).__name__}: {exc}",
                             seconds=time.perf_counter() - started,
                             timed_out="timeout" in type(exc).__name__.lower())
        return Completed(
            rc=int(getattr(res, "exit_code", 0) or 0),
            stdout=str(getattr(res, "result", "") or ""),
            stderr=str(getattr(res, "stderr", "") or ""),
            seconds=time.perf_counter() - started,
        )

    def site_packages(self) -> str:
        if self._site_packages is None:
            res = self.run(
                [self.python(), "-c",
                 "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
                timeout=60,
            )
            self._site_packages = res.stdout.strip() or f"{self.root}/venv/lib"
        return self._site_packages

    def read_text(self, path: str) -> str:
        try:
            data = self.sandbox.fs.download_file(path)
            if data:
                return data.decode("utf-8", errors="replace")
        except Exception:
            pass
        res = self.run(["cat", path], timeout=60)
        return res.stdout if res.ok else ""

    def write_text(self, path: str, content: str) -> None:
        parent = path.rsplit("/", 1)[0]
        self.run(["mkdir", "-p", parent], timeout=60)
        self.sandbox.fs.upload_file(content.encode("utf-8"), path)

    def materialise(self, local_path: str) -> str:
        """Copy a local candidate (a path spec, not a PyPI name) into the
        sandbox, which cannot see the host filesystem, and return the path
        pip should install from."""
        source = Path(local_path).resolve()
        dest = f"{self.root}/_audition/pkg/{source.name}"
        self.run(["mkdir", "-p", dest], timeout=60)

        skip = {"__pycache__", ".git", "build", "dist", ".venv", ".egg-info"}
        for item in sorted(source.rglob("*")):
            if any(part in skip or part.endswith(".egg-info") for part in item.parts):
                continue
            if not item.is_file():
                continue
            rel = item.relative_to(source).as_posix()
            try:
                self.sandbox.fs.upload_file(item.read_bytes(), f"{dest}/{rel}")
            except Exception as exc:
                raise DaytonaUnavailable(
                    f"could not upload {rel} of local candidate {source.name}: {exc}"
                ) from exc
        return dest

    def dir_size_kb(self, path: str) -> int:
        res = self.run(["du", "-sk", path], timeout=180)
        parts = res.stdout.split()
        try:
            return int(parts[0]) if res.ok and parts else 0
        except ValueError:
            return 0

    def safe_prefixes(self) -> list[str]:
        """Where a well-behaved package may write. Deliberately does NOT
        include the whole home directory — that is exactly where a package
        dropping a marker file would put it."""
        return [self.root, "/tmp", "/var/tmp", f"{self.home}/.cache/pip"]

    def destroy(self) -> None:
        try:
            self.sandbox.delete()
        except Exception:
            pass


class DaytonaForkProvider:
    name = "daytona-fork"

    def __init__(self, image: str | None = None):
        self.image = image or DEFAULT_IMAGE
        self.client = None
        self.base_sandbox = None
        self._base: DaytonaMachine | None = None
        self._machines: list[DaytonaMachine] = []
        self._snapshot: str | None = None
        self._snapshot_lock = threading.Lock()
        self._fork_supported = True

    # -- base -------------------------------------------------------------

    def _connect(self):
        import os

        if not os.environ.get("DAYTONA_API_KEY"):
            raise DaytonaUnavailable("DAYTONA_API_KEY is not set (put it in .env)")
        try:
            from daytona import Daytona
        except ImportError as exc:
            raise DaytonaUnavailable(
                "the `daytona` SDK is not installed — pip install daytona"
            ) from exc
        try:
            return Daytona()
        except Exception as exc:
            raise DaytonaUnavailable(f"could not reach Daytona: {exc}") from exc

    def _create_sandbox(self):
        """Default Python snapshot first; an explicit image if that is refused."""
        from daytona import CreateSandboxFromImageParams, CreateSandboxFromSnapshotParams

        # auto_stop_interval=0 disables the inactivity timer: background work
        # inside a sandbox does not reset it, and a base that stops mid-run
        # takes the whole comparison with it.
        try:
            return self.client.create(
                CreateSandboxFromSnapshotParams(language="python", auto_stop_interval=0)
            )
        except Exception as snapshot_error:
            try:
                return self.client.create(
                    CreateSandboxFromImageParams(
                        image=self.image, language="python", auto_stop_interval=0
                    ),
                    timeout=600,
                )
            except Exception as image_error:
                raise DaytonaUnavailable(
                    f"could not create a sandbox — from snapshot: {snapshot_error}; "
                    f"from image {self.image}: {image_error}"
                ) from image_error

    def prepare_base(self) -> float:
        started = time.perf_counter()
        self.client = self._connect()
        self.base_sandbox = self._create_sandbox()

        home = FALLBACK_HOME
        try:
            home = self.base_sandbox.get_user_root_dir() or FALLBACK_HOME
        except Exception:
            pass

        base = DaytonaMachine("base", self.base_sandbox, home.rstrip("/"))
        base.run(["mkdir", "-p", base.root], timeout=60)

        made = base.run(["python3", "-m", "venv", f"{base.root}/venv"], timeout=300)
        if not made.ok:
            raise DaytonaUnavailable(
                f"could not create the base venv in the sandbox: "
                f"{(made.stderr or made.stdout)[:300]}"
            )
        base.run(
            [base.python(), "-m", "pip", "install", "-q", "--upgrade",
             "--disable-pip-version-check", "pip", "setuptools", "wheel"],
            timeout=600,
        )
        self._base = base
        return time.perf_counter() - started

    def base_python_version(self) -> str:
        res = self._base.run(
            [self._base.python(), "-c",
             "import sys;print('.'.join(map(str,sys.version_info[:3])))"],
            timeout=60,
        )
        return res.stdout.strip() or "unknown"

    def baseline(self) -> tuple[set[str], int]:
        res = self._base.run(
            [self._base.python(), "-m", "pip", "list", "--format=json",
             "--disable-pip-version-check"],
            timeout=180,
        )
        try:
            names = {p["name"].lower() for p in json.loads(res.stdout or "[]")}
        except (json.JSONDecodeError, KeyError, TypeError):
            names = set()
        return names, self._base.dir_size_kb(self._base.site_packages())

    # -- fork -------------------------------------------------------------

    def fork(self, candidate: Candidate) -> tuple[DaytonaMachine, ForkInfo]:
        """Copy-on-write fork where the account allows it, snapshot restore
        where it does not.

        Both give every candidate the identical starting state, which is the
        property the comparison depends on. Fork is additionally instant and
        cheap; snapshot restore pays for the base image once per candidate.
        The method used is reported, so a number is never presented as more
        rigorous than the machine it came from.
        """
        started = time.perf_counter()
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in candidate.name).lower()
        stamp = int(time.time() * 1000)

        if self._fork_supported:
            try:
                sandbox = self.base_sandbox.fork(f"audition-{safe}-{stamp}")
                return self._wrap(candidate, sandbox, started, "daytona-fork")
            except Exception as exc:
                if "not supported" not in str(exc).lower():
                    raise DaytonaUnavailable(
                        f"sandbox.fork() failed for {candidate.name}: {exc}"
                    ) from exc
                # Forking is gated on this account; fall back for every
                # candidate from here on so the run stays consistent.
                self._fork_supported = False
                print(
                    "  note: forking is not enabled on this Daytona account — "
                    "falling back to snapshot restore (identical base, but "
                    "slower and paid for per candidate)",
                    flush=True,
                )

        return self._wrap(candidate, self._from_snapshot(safe, stamp), started,
                          "snapshot-restore")

    def _wrap(self, candidate: Candidate, sandbox, started: float, method: str):
        machine = DaytonaMachine(candidate.name, sandbox, self._base.home)
        self._machines.append(machine)
        return machine, ForkInfo(seconds=round(time.perf_counter() - started, 3),
                                 method=method)

    def _from_snapshot(self, safe: str, stamp: int):
        from daytona import CreateSandboxFromSnapshotParams

        # One thread builds the snapshot; the rest wait for it rather than
        # racing the server into "snapshot is still snapshotting".
        with self._snapshot_lock:
            if self._snapshot is None:
                name = f"audition-base-{stamp}"
                try:
                    self.base_sandbox.create_snapshot(name, timeout=900)
                except Exception as exc:
                    raise DaytonaUnavailable(
                        f"neither forking nor snapshot creation is available on "
                        f"this account: {exc}. Use --provider local."
                    ) from exc
                self._await_snapshot(name)
                self._snapshot = name

        try:
            return self.client.create(
                CreateSandboxFromSnapshotParams(
                    snapshot=self._snapshot,
                    name=f"audition-{safe}-{stamp}",
                    auto_stop_interval=0,
                ),
                timeout=600,
            )
        except Exception as exc:
            raise DaytonaUnavailable(
                f"could not restore the base snapshot for {safe}: {exc}"
            ) from exc

    def _await_snapshot(self, name: str, timeout: float = 900.0) -> None:
        """Block until the snapshot is restorable.

        create_snapshot() returns before the server has finished writing it,
        and restoring one that is still "snapshotting" fails outright.
        """
        deadline = time.time() + timeout
        last = "unknown"
        while time.time() < deadline:
            try:
                state = str(getattr(self.client.snapshot.get(name), "state", "")).lower()
            except Exception:
                state = ""
            last = state or last
            if any(k in state for k in ("active", "ready", "available")):
                return
            if any(k in state for k in ("error", "failed", "removing")):
                raise DaytonaUnavailable(f"base snapshot {name} ended in state {state}")
            time.sleep(3)
        raise DaytonaUnavailable(
            f"base snapshot {name} was not ready within {timeout:.0f}s (last state: {last})"
        )

    def cleanup(self) -> None:
        """Delete every sandbox this run created, and the base snapshot with
        them. Sandboxes and snapshots both cost money for as long as they
        exist, so a run that crashes must not leave a bill behind."""
        for machine in self._machines:
            machine.destroy()
        if self._base is not None:
            self._base.destroy()
        if self._snapshot and self.client is not None:
            try:
                for snap in self.client.snapshot.list().items:
                    if getattr(snap, "name", "") == self._snapshot:
                        self.client.snapshot.delete(snap)
                        break
            except Exception as exc:
                print(f"  warning: could not delete base snapshot "
                      f"{self._snapshot}: {exc}", flush=True)

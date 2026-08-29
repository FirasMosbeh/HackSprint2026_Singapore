"""Local provider: one prepared base venv, cloned once per candidate.

On APFS (and on Linux with a CoW filesystem) ``cp -c`` / ``cp --reflink``
makes the clone a copy-on-write snapshot rather than a byte-for-byte copy, so
forking the base is close to free and, more importantly, exact. Five forks of
one base are the same machine five times; five separately-built venvs are five
slightly different machines and any timing you read off them is noise.

This is the provider that runs with no API keys and no network beyond PyPI,
so it is the default and the one the demo depends on.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..models import Candidate, ForkInfo
from .base import Completed

BASE_MARKER = ".audition-base.json"


def _run(argv: list[str], env: dict | None = None, timeout: float | None = None) -> Completed:
    started = time.perf_counter()
    full_env = {**os.environ, **(env or {})}
    # Keep the parent's virtualenv from leaking into the forked machine.
    full_env.pop("VIRTUAL_ENV", None)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env=full_env,
            timeout=timeout,
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        return Completed(
            rc=124,
            stdout=(exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            stderr=f"timed out after {timeout}s",
            seconds=time.perf_counter() - started,
            timed_out=True,
        )
    except OSError as exc:
        return Completed(rc=127, stdout="", stderr=str(exc), seconds=time.perf_counter() - started)
    return Completed(
        rc=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        seconds=time.perf_counter() - started,
    )


class LocalMachine:
    def __init__(self, name: str, root: Path):
        self.name = name
        self.root = root
        self._site_packages: str | None = None

    def python(self) -> str:
        return str(self.root / "bin" / "python")

    def run(self, argv, env=None, timeout=None) -> Completed:
        return _run(argv, env=env, timeout=timeout)

    def site_packages(self) -> str:
        if self._site_packages is None:
            res = self.run(
                [self.python(), "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
                timeout=60,
            )
            self._site_packages = res.stdout.strip() or str(self.root / "lib")
        return self._site_packages

    def read_text(self, path: str) -> str:
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def write_text(self, path: str, content: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def dir_size_kb(self, path: str) -> int:
        res = _run(["du", "-sk", path], timeout=120)
        if res.ok and res.stdout.split():
            try:
                return int(res.stdout.split()[0])
            except ValueError:
                pass
        return 0

    def safe_prefixes(self) -> list[str]:
        """Where a well-behaved package may write: its own machine, the temp
        dir, and the shared pip cache. Anything else is a finding."""
        prefixes = [str(self.root), "/tmp", "/private/tmp", "/var/folders"]
        for var in ("TMPDIR", "PIP_CACHE_DIR"):
            if os.environ.get(var):
                prefixes.append(os.path.realpath(os.environ[var]))
        home = Path.home()
        prefixes += [str(home / ".cache" / "pip"), str(home / "Library" / "Caches" / "pip")]
        return [os.path.realpath(p) for p in prefixes]

    def destroy(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


class LocalForkProvider:
    name = "local-fork"

    def __init__(self, workdir: Path, python: str | None = None, rebuild_base: bool = False):
        self.workdir = Path(workdir)
        self.base = self.workdir / "base"
        self.forks_dir = self.workdir / "forks"
        self.python_exe = python or sys.executable
        self.rebuild_base = rebuild_base
        self.clone_method = "copy"
        self._forks: list[LocalMachine] = []

    # -- base -------------------------------------------------------------

    def prepare_base(self) -> float:
        started = time.perf_counter()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.forks_dir.mkdir(parents=True, exist_ok=True)

        if self.rebuild_base:
            shutil.rmtree(self.base, ignore_errors=True)

        if self._base_is_valid():
            return time.perf_counter() - started  # reuse the snapshot

        shutil.rmtree(self.base, ignore_errors=True)
        res = _run([self.python_exe, "-m", "venv", str(self.base)], timeout=300)
        if not res.ok:
            raise RuntimeError(f"could not create base venv: {res.stderr.strip()[:500]}")

        py = str(self.base / "bin" / "python")
        up = _run(
            [py, "-m", "pip", "install", "--upgrade", "--quiet",
             "--disable-pip-version-check", "pip", "setuptools", "wheel"],
            timeout=600,
        )
        if not up.ok:
            # Not fatal: an older pip still installs most things.
            print(f"  warning: base pip upgrade failed: {up.stderr.strip()[:200]}", file=sys.stderr)

        version = _run([py, "-c", "import sys;print('.'.join(map(str,sys.version_info[:3])))"]).stdout.strip()
        (self.base / BASE_MARKER).write_text(
            json.dumps({"python": version, "created": time.time()}), encoding="utf-8"
        )
        self._baseline = None
        return time.perf_counter() - started

    def _base_is_valid(self) -> bool:
        marker = self.base / BASE_MARKER
        py = self.base / "bin" / "python"
        if not (marker.exists() and py.exists()):
            return False
        res = _run([str(py), "-c", "import pip"], timeout=60)
        return res.ok

    def base_python_version(self) -> str:
        res = _run(
            [str(self.base / "bin" / "python"), "-c",
             "import sys;print('.'.join(map(str,sys.version_info[:3])))"],
            timeout=60,
        )
        return res.stdout.strip() or "unknown"

    def baseline(self) -> tuple[set[str], int]:
        """Packages and site-packages size of the untouched base, so every
        footprint number is a delta against the same starting point."""
        machine = LocalMachine("base", self.base)
        res = machine.run(
            [machine.python(), "-m", "pip", "list", "--format=json",
             "--disable-pip-version-check"],
            timeout=120,
        )
        names: set[str] = set()
        try:
            names = {p["name"].lower() for p in json.loads(res.stdout or "[]")}
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        return names, machine.dir_size_kb(machine.site_packages())

    # -- fork -------------------------------------------------------------

    def fork(self, candidate: Candidate) -> tuple[LocalMachine, ForkInfo]:
        dest = self.forks_dir / f"fork-{candidate.name}"
        shutil.rmtree(dest, ignore_errors=True)

        started = time.perf_counter()
        method = self._clone(self.base, dest)
        elapsed = time.perf_counter() - started

        machine = LocalMachine(candidate.name, dest)
        self._forks.append(machine)
        return machine, ForkInfo(seconds=round(elapsed, 3), method=method)

    def _clone(self, src: Path, dest: Path) -> str:
        """Copy-on-write clone where the filesystem supports it."""
        if sys.platform == "darwin":
            res = _run(["cp", "-Rc", str(src), str(dest)], timeout=300)
            if res.ok:
                return "apfs-clone"
            shutil.rmtree(dest, ignore_errors=True)
        else:
            res = _run(["cp", "-a", "--reflink=auto", str(src), str(dest)], timeout=300)
            if res.ok:
                return "reflink-copy"
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest, symlinks=True)
        return "deep-copy"

    def cleanup(self) -> None:
        # Forks are kept so a failed run can be inspected; the base is the
        # expensive artefact and it is deliberately preserved between runs.
        return

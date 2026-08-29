"""Observability hook. Auto-imported by CPython's ``site`` module.

This file is put on PYTHONPATH for the install, import and test phases, so
*every* Python process in the forked machine loads it -- including the build
backend that runs a package's own ``setup.py``. That is the point: a sleeping
install hook runs in a child process, not in ours.

It records three things via ``sys.addaudithook``:

  * outbound connections and DNS lookups
  * files opened for writing outside the package's own directory
  * subprocesses and shell commands

The hook is deliberately NOT active during the timed performance reps, so
its overhead cannot contaminate the speed column.
"""

import os
import sys

_LOG_PATH = os.environ.get("AUDITION_AUDIT_LOG")
_PHASE = os.environ.get("AUDITION_PHASE", "unknown")

if _LOG_PATH:
    import json
    import threading

    _SAFE_PREFIXES = tuple(
        p for p in os.environ.get("AUDITION_SAFE_PREFIXES", "").split(os.pathsep) if p
    )
    _LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "", None}

    # Opened once, before the hook exists, so writing to it cannot re-enter.
    try:
        _LOG = open(_LOG_PATH, "a", buffering=1, encoding="utf-8")
    except OSError:
        _LOG = None

    _busy = threading.local()

    # pip's own main process talks to PyPI as its entire job; recording that
    # would bury the signal we actually want. Child processes during the same
    # phase -- the build backend running setup.py -- are still recorded.
    _IS_PIP_MAIN = any("pip" in str(a) for a in sys.argv[:2])

    def _emit(kind, detail):
        if _LOG is None or getattr(_busy, "on", False):
            return
        _busy.on = True
        try:
            _LOG.write(
                json.dumps(
                    {"phase": _PHASE, "kind": kind, "detail": str(detail)[:400], "pid": os.getpid()}
                )
                + "\n"
            )
        except Exception:
            pass
        finally:
            _busy.on = False

    def _is_safe_path(path):
        try:
            real = os.path.realpath(str(path))
        except Exception:
            return True
        return real.startswith(_SAFE_PREFIXES) if _SAFE_PREFIXES else False

    def _wants_write(mode, flags):
        if mode:
            return any(c in mode for c in "wax+")
        if flags:
            return bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT))
        return False

    def _host_of(address):
        if isinstance(address, tuple) and address:
            return address[0]
        return None

    def _hook(event, args):
        try:
            if event == "socket.connect":
                if _IS_PIP_MAIN:
                    return
                host = _host_of(args[1] if len(args) > 1 else None)
                if host not in _LOCAL_HOSTS:
                    _emit("network", f"connect {host}")
            elif event == "socket.getaddrinfo":
                if _IS_PIP_MAIN:
                    return
                host = args[0] if args else None
                if host not in _LOCAL_HOSTS:
                    _emit("network", f"resolve {host}")
            elif event == "open":
                path = args[0] if args else None
                mode = args[1] if len(args) > 1 else None
                flags = args[2] if len(args) > 2 else None
                if path and _wants_write(mode, flags) and not _is_safe_path(path):
                    _emit("write", path)
            elif event == "subprocess.Popen":
                if _IS_PIP_MAIN:
                    return
                _emit("subprocess", args[1] if len(args) > 1 else args)
            elif event == "os.system":
                _emit("subprocess", args[0] if args else "")
        except Exception:
            # An audit hook that raises takes the whole interpreter with it.
            pass

    if _LOG is not None:
        sys.addaudithook(_hook)

from __future__ import annotations
import os
import socket
import sys
import time
from pathlib import Path

PROFILE = 2396255917
NETWORK_SENSITIVE = False
FILESYSTEM_SENSITIVE = False
INJECTION_SENSITIVE = True
FUZZ_SENSITIVE = False
RESOURCE_SENSITIVE = False

payload = sys.stdin.read()
if not payload and len(sys.argv) > 1:
    payload = " ".join(sys.argv[1:])

repo = Path.cwd()

# Fuzzing: malformed and unexpected input should reveal whether the target handles it.
if FUZZ_SENSITIVE and (payload == "" or payload in {"{", "[", "{\"a\":", "\' OR \'1\'=\'1"}):
    print("malformed input rejected", file=sys.stderr)
    sys.exit(1)

# Injection: echo suspicious text and optionally expose a marker that the test can observe.
if INJECTION_SENSITIVE and any(marker in payload for marker in ["\' OR \'1\'=\'1", "&& id", "../", "{{7*7}}"]):
    print("syntax error near unexpected token", file=sys.stderr)
    print("uid=1000(sentrya)")

# Filesystem: write a file inside the repo and, for some inputs, outside the repo root.
if FILESYSTEM_SENSITIVE and any(marker in payload for marker in ["../", "..\\", "../../../../etc/passwd", "/etc/passwd", "..%2F..%2F"]):
    outside = repo.parent / f"unexpected-{PROFILE}.txt"
    outside.write_text("filesystem side effect", encoding="utf-8")
else:
    (repo / "safe-output.txt").write_text(payload or "safe", encoding="utf-8")

# Network: controlled localhost connect attempt.
if NETWORK_SENSITIVE and any(marker in payload for marker in ["network-probe", "..", "id", "{{"]):
    try:
        socket.create_connection(("127.0.0.1", 9), timeout=0.1)
    except OSError:
        pass

# Resources: keep it safe but measurable.
if RESOURCE_SENSITIVE and len(payload) > 1024:
    _ = [payload] * 5000
    time.sleep(0.05)

print(payload)

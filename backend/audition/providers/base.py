"""Provider interface.

A provider knows how to prepare *one* base machine and then fork it once per
candidate. Everything above this layer -- measurement, scoring, reporting --
is written against these two operations only, so swapping a local
copy-on-write clone for a Daytona sandbox fork changes nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import Candidate, ForkInfo


@dataclass
class Completed:
    rc: int
    stdout: str
    stderr: str
    seconds: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.rc == 0 and not self.timed_out


class Machine(Protocol):
    """One forked machine, dedicated to one candidate."""

    name: str

    def run(
        self,
        argv: list[str],
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Completed: ...

    def python(self) -> str:
        """Path to the interpreter inside this machine."""

    def site_packages(self) -> str: ...

    def read_text(self, path: str) -> str: ...

    def dir_size_kb(self, path: str) -> int: ...

    def safe_prefixes(self) -> list[str]:
        """Paths a well-behaved package is allowed to write to."""

    def destroy(self) -> None: ...


class Provider(Protocol):
    name: str

    def prepare_base(self) -> float:
        """Build (or reuse) the one base machine. Returns seconds spent."""

    def fork(self, candidate: Candidate) -> tuple[Machine, ForkInfo]: ...

    def cleanup(self) -> None: ...

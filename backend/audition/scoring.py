"""The ranking rule.

Two properties matter more than the exact numbers here:

1. It is arithmetic over measured facts, not a model's judgement. Swap the
   model out and the same library wins.
2. It is printed next to the result, so a reader can disagree with the
   weights rather than with a black box.

Keep both. If you add a dimension, add it to WEIGHTS and to the printed
formula in the same commit.
"""

from __future__ import annotations

from .models import CandidateResult

WEIGHTS: dict[str, float] = {
    "conformance": 50.0,   # does it do the job
    "maintenance": 20.0,   # will it still work next year
    "speed": 15.0,         # what it costs to run
    "footprint": 10.0,     # what it drags in
    "memory": 5.0,
}

GATE_RULES: list[str] = [
    "install_failed",
    "conformance < 60%",
    "writes outside package dir",
    "unexpected network",
]

FORMULA = (
    "score = 50 x conformance_rate + 20 x maintenance_freshness "
    "+ 15 x speed_percentile + 10 x footprint_percentile + 5 x memory_percentile"
)

# A release within FRESH_DAYS scores 1.0; one older than STALE_DAYS scores 0.0;
# in between it decays linearly. 18 months is the point at which "maintained"
# stops being a fair description of a package.
FRESH_DAYS = 90
STALE_DAYS = 550

CONFORMANCE_GATE = 0.60


def maintenance_freshness(age_days: int | None) -> float:
    if age_days is None:
        return 0.5  # unknown: neither rewarded nor punished
    if age_days <= FRESH_DAYS:
        return 1.0
    if age_days >= STALE_DAYS:
        return 0.0
    return 1.0 - (age_days - FRESH_DAYS) / (STALE_DAYS - FRESH_DAYS)


def _percentile_lower_is_better(value: float | None, all_values: list[float]) -> float:
    """1.0 for the best (lowest) value on the board, 0.0 for the worst.

    Linear between them, so the column reflects the size of the gap and not
    just the ordering: a library that is twice as slow loses twice as much.
    """
    usable = [v for v in all_values if v is not None and v > 0]
    if value is None or value <= 0 or not usable:
        return 0.0
    lo, hi = min(usable), max(usable)
    if hi == lo:
        return 1.0
    return (hi - value) / (hi - lo)


def evaluate_gates(result: CandidateResult) -> list[str]:
    """Hard gates. Any one of these disqualifies, regardless of score."""
    gates: list[str] = []
    if not result.install.ok:
        gates.append("install_failed")
        return gates  # nothing downstream was measured, so nothing else applies
    if result.conformance.total and result.conformance.rate < CONFORMANCE_GATE:
        gates.append(f"conformance {result.conformance.rate:.0%} < 60%")
    if result.behaviour.writes:
        gates.append("writes outside package dir")
    if result.behaviour.network:
        gates.append("unexpected network")
    return gates


def score_all(results: list[CandidateResult]) -> str | None:
    """Fill in gates, scores and breakdowns; return the winner's name.

    Percentiles are computed across the survivors only. A candidate that
    cannot install would otherwise sit at the bottom of every distribution
    and flatter everyone above it.
    """
    for r in results:
        r.gates = evaluate_gates(r)

    survivors = [r for r in results if not r.disqualified and r.status == "done"]

    speeds = [r.perf.wall_ms for r in survivors if r.perf.wall_ms]
    mems = [r.perf.peak_mem_mb for r in survivors if r.perf.peak_mem_mb]
    sizes = [float(r.footprint.install_kb) for r in survivors if r.footprint.install_kb]

    for r in results:
        if r.disqualified or r.status != "done":
            r.score = None
            r.breakdown = {}
            continue
        parts = {
            "conformance": WEIGHTS["conformance"] * r.conformance.rate,
            "maintenance": WEIGHTS["maintenance"] * maintenance_freshness(r.maintenance.age_days),
            "speed": WEIGHTS["speed"] * _percentile_lower_is_better(r.perf.wall_ms, speeds),
            "footprint": WEIGHTS["footprint"]
            * _percentile_lower_is_better(float(r.footprint.install_kb or 0), sizes),
            "memory": WEIGHTS["memory"] * _percentile_lower_is_better(r.perf.peak_mem_mb, mems),
        }
        r.breakdown = {k: round(v, 2) for k, v in parts.items()}
        r.score = round(sum(parts.values()), 2)

    ranked = sorted(survivors, key=lambda r: r.score or 0.0, reverse=True)
    return ranked[0].name if ranked else None

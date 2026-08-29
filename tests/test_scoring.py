"""Self-checks for the ranking rule.

The scorecard's whole claim is that the recommendation is arithmetic over
measured facts. These tests are what keep that claim true: stdlib unittest
only, so they run in the same bare machine the tool does.

    python3 -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from audition import scoring, verdict  # noqa: E402
from audition.models import (  # noqa: E402
    BehaviourInfo, Candidate, CandidateResult, CaseResult, ConformanceInfo,
    FootprintInfo, InstallInfo, MaintenanceInfo, PerfInfo, Report,
)


def make(name, *, passed=7, total=7, ms=100.0, mem=20.0, deps=1, kb=1024,
         age=30, network=(), writes=(), installed=True):
    return CandidateResult(
        candidate=Candidate(spec=name, import_name=name, name=name),
        status="done",
        install=InstallInfo(ok=installed, seconds=1.0),
        conformance=ConformanceInfo(
            total=total, passed=passed,
            cases=[CaseResult(name=f"test_{i}", passed=i < passed) for i in range(total)],
        ),
        perf=PerfInfo(wall_ms=ms, peak_mem_mb=mem, reps=3),
        footprint=FootprintInfo(deps=deps, install_kb=kb),
        maintenance=MaintenanceInfo(age_days=age, last_release="2026-08-01"),
        behaviour=BehaviourInfo(observed=True, network=list(network), writes=list(writes)),
    )


class HardGates(unittest.TestCase):
    def test_failed_install_is_disqualified(self):
        r = make("broken", installed=False)
        self.assertIn("install_failed", scoring.evaluate_gates(r))

    def test_failed_install_reports_only_that_gate(self):
        # Nothing downstream was measured, so nothing downstream should be claimed.
        r = make("broken", installed=False, passed=0, network=["connect evil.example"])
        self.assertEqual(scoring.evaluate_gates(r), ["install_failed"])

    def test_low_conformance_is_disqualified(self):
        self.assertTrue(any("conformance" in g for g in scoring.evaluate_gates(make("weak", passed=3))))

    def test_conformance_gate_is_inclusive_at_60_percent(self):
        self.assertEqual(scoring.evaluate_gates(make("edge", passed=6, total=10)), [])
        self.assertTrue(scoring.evaluate_gates(make("under", passed=59, total=100)))

    def test_network_and_writes_are_disqualifying(self):
        gates = scoring.evaluate_gates(make("villain", network=["connect x"], writes=["~/.marker"]))
        self.assertIn("unexpected network", gates)
        self.assertIn("writes outside package dir", gates)

    def test_quiet_conforming_candidate_passes_every_gate(self):
        self.assertEqual(scoring.evaluate_gates(make("good")), [])


class Ranking(unittest.TestCase):
    def test_conformance_outweighs_every_other_dimension(self):
        thorough = make("thorough", passed=7, ms=900.0, mem=90.0, deps=9, kb=40000, age=20)
        quick = make("quick", passed=4, total=7, ms=10.0, mem=10.0, deps=0, kb=100, age=20)
        self.assertEqual(scoring.score_all([thorough, quick]), "thorough")

    def test_a_disqualified_candidate_never_wins(self):
        villain = make("villain", passed=7, ms=5.0, deps=0, kb=50, network=["connect x"])
        plain = make("plain", passed=7, ms=800.0, deps=8, kb=30000, age=400)
        self.assertEqual(scoring.score_all([villain, plain]), "plain")
        self.assertIsNone(villain.score)

    def test_percentiles_ignore_disqualified_rows(self):
        # A disqualified outlier must not stretch the scale and flatter the rest.
        good_a = make("a", ms=100.0)
        good_b = make("b", ms=200.0)
        outlier = make("dq", ms=100000.0, network=["connect x"])
        scoring.score_all([good_a, good_b, outlier])
        self.assertEqual(good_a.breakdown["speed"], scoring.WEIGHTS["speed"])
        self.assertEqual(good_b.breakdown["speed"], 0.0)

    def test_freshness_decays_and_is_clamped(self):
        self.assertEqual(scoring.maintenance_freshness(0), 1.0)
        self.assertEqual(scoring.maintenance_freshness(10_000), 0.0)
        self.assertEqual(scoring.maintenance_freshness(None), 0.5)
        mid = scoring.maintenance_freshness(320)
        self.assertTrue(0.0 < mid < 1.0)

    def test_single_survivor_is_not_punished_on_percentiles(self):
        only = make("only")
        self.assertEqual(scoring.score_all([only]), "only")
        self.assertAlmostEqual(only.score, 100.0, places=1)

    def test_a_clean_sweep_of_the_cheap_columns_can_beat_two_failed_cases(self):
        """Documented tension in the brief's weights, pinned deliberately.

        Conformance is worth 50 and the three cost columns are worth 30
        between them. A candidate that fails 2 of 7 cases (-14.3) but takes
        speed, footprint and memory outright (+30) wins on arithmetic. That
        is what the stated formula does; it is not a bug, but it is the case
        to raise the maintenance/conformance weights against if the shortlist
        makes it likely.
        """
        thorough = make("thorough", passed=7, ms=1000.0, mem=60.0, kb=5000, age=10)
        cheap = make("cheap", passed=5, total=7, ms=50.0, mem=10.0, kb=500, age=10)
        self.assertEqual(scoring.score_all([thorough, cheap]), "cheap")
        self.assertAlmostEqual(cheap.score - thorough.score, 30 - 50 * (2 / 7), places=1)

    def test_no_survivors_yields_no_winner(self):
        self.assertIsNone(scoring.score_all([make("a", installed=False), make("b", passed=0)]))


class Verdict(unittest.TestCase):
    """The sentence must never claim a weakness the winner does not have."""

    def _report(self, results):
        rep = Report(requirement="r", python="3.13", provider="local-fork", candidates=results)
        rep.winner = scoring.score_all(results)
        rep.verdict, rep.verdict_by = verdict.write(rep)
        return rep

    def test_does_not_invent_a_cost_for_a_dominant_winner(self):
        best = make("best", passed=7, ms=10.0, mem=5.0, deps=0, kb=50, age=5)
        rest = make("rest", passed=5, ms=500.0, mem=50.0, deps=5, kb=5000, age=5)
        rep = self._report([best, rest])
        self.assertEqual(rep.winner, "best")
        self.assertNotIn("lightest option on the board", rep.verdict)
        self.assertTrue(rep.verdict.startswith("best."))

    def test_names_a_real_cost_when_one_exists(self):
        winner = make("slow_but_correct", passed=7, ms=1000.0, mem=10.0, kb=500, deps=0, age=10)
        rival = make("fast_but_wrong", passed=5, total=7, ms=50.0, mem=60.0, kb=5000, deps=0, age=10)
        rep = self._report([winner, rival])
        self.assertEqual(rep.winner, "slow_but_correct")
        self.assertIn("slower than fast_but_wrong", rep.verdict)

    def test_ignores_a_speed_gap_that_is_only_noise(self):
        winner = make("w", passed=7, ms=105.0, deps=0, age=10)
        rival = make("r", passed=5, total=7, ms=100.0, deps=0, age=10)
        self.assertNotIn("slower", self._report([winner, rival]).verdict)

    def test_explains_when_nothing_survives(self):
        rep = self._report([make("a", installed=False), make("b", network=["connect x"])])
        self.assertIsNone(rep.winner)
        self.assertIn("hard gates", rep.verdict)


class SuiteGeneration(unittest.TestCase):
    def test_offline_suite_is_valid_and_can_fail(self):
        from audition import testgen

        names = testgen._validate(testgen.offline_suite("parse human dates like next tuesday"))
        self.assertEqual(len(names), 7)

    def test_a_suite_without_assertions_is_rejected(self):
        from audition import testgen

        with self.assertRaises(testgen.SuiteError):
            testgen._validate("def test_a(lib):\n    return True\n" * 3)


if __name__ == "__main__":
    unittest.main()

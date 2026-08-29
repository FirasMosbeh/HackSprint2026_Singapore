"""The closing sentence.

The model writes the explanation. It never selects the winner -- the winner
is already decided by scoring.py before this module is called, and is passed
in as a fact. Swap the model out and the same library wins; only the prose
changes. The offline template exists so that is demonstrably true.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from . import config
from .models import Report

MEANINGFUL_SLOWDOWN = 1.25

SYSTEM = """You explain a dependency recommendation that has ALREADY been made by a \
scoring formula. You are given the winner and the measured facts.

Write ONE sentence, at most 45 words, starting with the winner's name. It must name the \
winner's real costs first (slower, heavier, more dependencies -- whatever the numbers show), \
then the reason it still won. Do not hedge, do not use bullet points, do not recommend a \
different library, do not mention scores or formulas. Plain declarative prose."""


def write(report: Report) -> tuple[str, str]:
    """Returns (sentence, author)."""
    if not report.winner:
        return _no_winner(report), "audition"

    facts = _facts(report)
    api_key = config.kimi_api_key()
    if api_key:
        try:
            return _ask_kimi(report, facts, api_key), config.llm_label()
        except (urllib.error.URLError, OSError, KeyError, IndexError, json.JSONDecodeError):
            pass
    return _template(report), "audition"


def _facts(report: Report) -> str:
    lines = [f"Requirement: {report.requirement}", f"Winner: {report.winner}", "", "Measured:"]
    for r in report.candidates:
        if not r.install.ok:
            lines.append(f"- {r.name}: failed to install on Python {report.python}")
            continue
        lines.append(
            f"- {r.name}: passes {r.conformance.passed}/{r.conformance.total} cases, "
            f"{r.perf.wall_ms or 0:.0f} ms, {r.perf.peak_mem_mb or 0:.0f} MB peak, "
            f"{r.footprint.deps} deps, {r.footprint.install_kb / 1024:.1f} MB on disk, "
            f"last release {r.maintenance.last_release or 'unknown'}, "
            f"behaviour: {r.behaviour.flag}"
            + (f", DISQUALIFIED ({'; '.join(r.gates)})" if r.gates else "")
        )
    return "\n".join(lines)


def _ask_kimi(report: Report, facts: str, api_key: str) -> str:
    base = config.kimi_base_url()
    payload = json.dumps({
        "model": config.kimi_model(),
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": facts},
        ],
        "temperature": 0.3,
        "max_tokens": 200,
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        body = json.loads(resp.read().decode())
    sentence = body["choices"][0]["message"]["content"].strip().strip('"')
    if not sentence.lower().startswith(report.winner.lower()):
        sentence = f"{report.winner}. {sentence}"
    return sentence


def _template(report: Report) -> str:
    """Offline stand-in for the model's sentence.

    It states the winner's genuine costs first, exactly as the model is asked
    to. Every clause is derived from a measured comparison, so the sentence
    can never claim a weakness the winner does not have.
    """
    winner = next(r for r in report.candidates if r.name == report.winner)
    others = [r for r in report.candidates if r.name != report.winner and r.install.ok]

    costs: list[str] = []

    faster = [o for o in others if o.perf.wall_ms and winner.perf.wall_ms
              and o.perf.wall_ms < winner.perf.wall_ms]
    if faster:
        best = min(faster, key=lambda o: o.perf.wall_ms or 0)
        ratio = (winner.perf.wall_ms or 0) / (best.perf.wall_ms or 1)
        # Below this, the gap is run-to-run noise rather than a cost, and
        # naming it only weakens the sentence.
        if ratio >= MEANINGFUL_SLOWDOWN:
            costs.append(f"it is {ratio:.1f} times slower than {best.name}")

    leaner = [o for o in others if o.footprint.deps < winner.footprint.deps]
    if leaner:
        fewest = min(leaner, key=lambda o: o.footprint.deps)
        costs.append(
            f"it drags in {winner.footprint.deps - fewest.footprint.deps} more "
            f"dependencies than {fewest.name}"
        )

    age = winner.maintenance.age_days
    fresher = [o.maintenance.age_days for o in others
               if o.maintenance.age_days is not None and age is not None
               and o.maintenance.age_days < age]
    if age is not None and age > 365 and fresher:
        costs.append(f"it has not shipped a release in {age // 365} years")

    reasons: list[str] = []
    perfect = winner.conformance.total and winner.conformance.passed == winner.conformance.total
    others_perfect = any(
        o.conformance.total and o.conformance.passed == o.conformance.total for o in others
    )
    if perfect and not others_perfect:
        reasons.append(f"passes all {winner.conformance.total} of your cases")
    else:
        reasons.append(
            f"passes {winner.conformance.passed} of {winner.conformance.total} of your cases"
        )
    if age is not None and age <= 365:
        reasons.append("is actively maintained")
    if winner.behaviour.flag == "quiet":
        reasons.append("touches nothing outside its own directory")

    tail = _join(reasons)

    if not costs:
        # The winner is best on everything we measured. Say so rather than
        # inventing a weakness to sound balanced.
        strengths = []
        if winner.perf.wall_ms and all(
            (o.perf.wall_ms or 1e9) >= winner.perf.wall_ms for o in others
        ):
            strengths.append("the fastest")
        if all(o.footprint.install_kb >= winner.footprint.install_kb for o in others):
            strengths.append("the lightest")
        lead = (
            f"It is {_join(strengths)} candidate on the board"
            if strengths
            else "It carries no measured penalty against the rest of the shortlist"
        )
        return f"{report.winner}. {lead}, and it {tail}."

    return (
        f"{report.winner}. {_capitalise(_join(costs))} — and it is the only candidate "
        f"that {tail}."
    )


def _join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _capitalise(text: str) -> str:
    return text[0].upper() + text[1:] if text else text


def _no_winner(report: Report) -> str:
    tripped = [r for r in report.candidates if r.disqualified]
    if tripped:
        return (
            "No candidate survives the hard gates: "
            + "; ".join(f"{r.name} ({r.gates[0]})" for r in tripped)
            + ". Widen the shortlist rather than picking the least-bad row."
        )
    return "No candidate produced a usable result. Check the detail rows for what went wrong."

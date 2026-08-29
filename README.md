# Audition

**Which library is actually best for your use case?**

You need a library. Four claim to do the job. Today you pick by GitHub stars
and a skim of the README — then find out in production.

Audition takes your requirement in plain English and three to five candidates,
gives each one an **identical machine forked from the same base**, and measures
them: does it install, does it pass a test written from *your* requirement, how
fast and how heavy is it, is it maintained, and what does it quietly do to your
system while it runs.

```
$ audition run "parse human-written dates like 'next tuesday' into a datetime" \
    --candidates dateparser,arrow,parsedatetime,pendulum==2.1.2,./sandboxes/villain/chrono-py::chrono_py

 Candidate        Installs    My tests    Speed     Peak mem    Behaviour    Footprint          Maintained
 dateparser       clean       6 / 7       672 ms    64 MB       quiet        5 deps · 9.0 MB    24 days
 arrow            clean       3 / 7       37 ms     17 MB       quiet        3 deps · 4.2 MB    10 months
     ! disqualified: conformance 43% < 60%
 parsedatetime    clean       7 / 7       42 ms     15 MB       quiet        0 deps · 0.4 MB    6 years
 pendulum         failed      —           —         —           —            —                  6 years
     ! disqualified: install_failed
 chrono-py        clean       5 / 7       44 ms     17 MB       network      5 deps · 3.7 MB    unknown
     ! disqualified: writes outside package dir; unexpected network

  Winner: parsedatetime
  parsedatetime. It has not shipped a release in 6 years — and it is the only
  candidate that passes all 7 of your cases and touches nothing outside its own
  directory.
```

Five rows, five different lessons, and no row is simply "the best".

## Quickstart

No dependencies, no install step, no API keys. Python 3.10+.

```bash
./audition demo --serve        # replay a cached run — instant, no network
./audition rule                # print the ranking rule and exit

./audition run "parse human-written dates like 'next tuesday' into a datetime" \
  --candidates dateparser,arrow,parsedatetime \
  --serve
```

`--serve` opens the live scorecard on localhost; rows fill in as results land.
Use `spec::module` when the import name differs from the package name
(`./sandboxes/villain/chrono-py::chrono_py`).

Installing it properly (`pip install -e .`) puts `audition` on your PATH.

### It has an exit code, so it drops into CI

```bash
audition run "must parse ISO 8601 timestamps" --candidates arrow,pendulum --require arrow
```

| exit | meaning |
| ---- | ------- |
| `0`  | a winner survived the gates (or `--require`d library is clean) |
| `1`  | nothing survived the hard gates |
| `2`  | the `--require`d library was disqualified |
| `3`  | the run itself failed |

## The five things it measures

| # | Column | How |
| - | ------ | --- |
| 1 | **Does it install at all, on my setup?** | A real `pip install` from a clean state, on your Python. This alone often eliminates one. |
| 2 | **Does it do my thing?** | Kimi turns your sentence into a conformance suite. The *same* suite runs against every candidate. Not "does it have tests" — does it pass *mine*. |
| 3 | **What does it cost me to run?** | Wall time and peak RSS over the same battery, best-of-N. Nearly free, since we are already running the code. |
| 4 | **What am I signing up for long-term?** | Dependencies added and bytes on disk, measured in the fork. Last release date from PyPI. |
| 5 | **What does it do when nobody is watching?** | Files written outside its own directory, outbound connections, subprocesses — during install *and* import. |

## The recommendation is arithmetic, not an opinion

```
# hard gates — any one of these disqualifies, regardless of score
install_failed · conformance < 60% · writes outside package dir · unexpected network

# then rank the survivors
score = 50 x conformance_rate      # does it do the job
      + 20 x maintenance_freshness # will it still work next year
      + 15 x speed_percentile      # what it costs to run
      + 10 x footprint_percentile  # what it drags in
      +  5 x memory_percentile
```

The weights live in [`backend/audition/scoring.py`](backend/audition/scoring.py)
and are printed next to the result, so you can disagree with the weights rather
than with a black box.

**Kimi writes the closing sentence. It never selects the winner.** The winner is
decided by `scoring.py` before the model is called, and is handed to it as a
fact. Run with `--no-kimi` and the same library wins — that is the point, and
the offline path exists to make it demonstrable.

## One base, forked five ways

Fork is not a speed trick here. It is what makes the comparison mean anything.

Audition prepares **one** machine — your Python, the harness, the measurement
wrapper — and then forks it once per candidate. Each fork installs only its own
library. Nothing else differs: not a package version, not an environment
variable, not a warm cache.

Five separately-built environments are five slightly different machines, and any
speed or memory number you read off them is noise. Five forks of one machine are
the same machine five times, and the only variable is the thing you are actually
testing.

Two providers implement that same pair of operations:

- **`local`** (default) — clones the prepared venv with `cp -c` / `--reflink`, a
  copy-on-write snapshot on APFS and btrfs. Five forks in ~1.7s. Runs with no
  API keys.
- **`daytona`** — forks a real disposable sandbox. Isolation is what makes it
  safe to let unknown install scripts genuinely run; fan-out makes five
  candidates cost the wall time of one. Needs `DAYTONA_API_KEY` and
  `pip install daytona`.

## How the behaviour column works

A CPython audit hook (`sys.addaudithook`) is loaded via `sitecustomize` into
*every* Python process in the fork — including the build backend that runs a
package's own `setup.py`, because a sleeping install hook runs in a child
process, not in ours. It records outbound connections, writes outside the
package's own directory, and subprocess spawns.

Two deliberate choices:

- The hook is **off during the timed reps** and runs once afterwards, so its
  overhead cannot contaminate the speed column.
- pip's own main process talking to PyPI is **not** recorded — that is its
  entire job, and recording it would bury the signal. Child processes during
  the same phase still are.

## The cast

Four of the demo candidates are real packages from PyPI. The fifth was written
for the demo and is disclosed as such — see
[`sandboxes/villain/chrono-py/README.md`](sandboxes/villain/chrono-py/README.md).
Disclosed staging reads as rigour; an undisclosed rig that a judge notices costs
you everything else you said.

| Archetype | Row | What it teaches |
| --------- | --- | --------------- |
| The fastest one that does not actually work | `arrow` | Fastest and lightest of the real candidates — and passes 3 of your 7 cases. Destroys "just pick the popular one". |
| The one that works but is abandoned | `parsedatetime` | 7/7, zero dependencies, 400 KB — and no release in six years. |
| The one that will not install | `pendulum==2.1.2` | `ModuleNotFoundError: No module named 'distutils'`. Removed in Python 3.12. Ten seconds of the demo, and the check is not theoretical. |
| The one that phones home | `chrono-py` | Newest, most attractive on paper — opens a socket and writes to `~` on **import**. |
| The winner, which is nobody's favourite | `parsedatetime` | Not the fastest, not the newest, not the most popular. |

### An honest note on the result

The brief for this project predicted `dateparser` would win. It does not: it
fails "next tuesday", which is the exact phrase in the requirement, and
`parsedatetime` passes all seven cases. That result was measured, not authored.

It is the more interesting demo anyway — the recommendation is a package that
has not shipped in six years, and the formula that says so is printed right
underneath it. If you think maintenance deserves more than 20 points, change one
line in `scoring.py` and re-run. That is the difference between a scorecard and
an opinion.

## Layout

```
backend/audition/       engine, scoring, CLI, test generation, verdict
  providers/            local copy-on-write forks · Daytona sandbox forks
sandboxes/probe/        what runs inside the fork: audit hook + conformance runner
sandboxes/villain/      the staged, disclosed demo package
frontend/scorecard.html the live scorecard (polls report.json)
database/runs/          cached runs, replayable with `audition demo`
```

## Configuration

**Nothing is required.** With no configuration at all, Audition runs end to
end: local copy-on-write forks, the offline conformance-test generator, and a
template verdict. Keys only add the Kimi and Daytona tiers on top.

```bash
cp .env.example .env     # then fill in whatever you actually have
./audition config        # shows what is wired up and what will run
```

`.env` lives at the repo root and is gitignored. A real environment variable
always beats the file, so you can override any line for a single run:

```bash
KIMI_MODEL=kimi-k2-0905-preview ./audition run ...
```

| Variable | Needed for | Where to get it |
| -------- | ---------- | --------------- |
| `KIMI_API_KEY` | Kimi writes the conformance suite and the closing sentence | [platform.moonshot.ai](https://platform.moonshot.ai/console/api-keys) |
| `KIMI_MODEL`, `KIMI_BASE_URL` | overriding the model or the endpoint | optional; defaults to `kimi-k2-turbo-preview` |
| `DAYTONA_API_KEY` | `--provider daytona` | [app.daytona.io](https://app.daytona.io) → Dashboard → Keys |
| `DAYTONA_TARGET`, `DAYTONA_API_URL` | non-default region or control plane | optional; only if your dashboard shows one |

### Running against Daytona

```bash
pip install daytona          # the SDK is an optional extra, not a dependency
echo "DAYTONA_API_KEY=dtn_..." >> .env
./audition config            # confirm: "daytona available"
./audition run "..." --candidates dateparser,arrow --provider daytona
```

The Daytona provider implements the same two operations as the local one
(`prepare_base` and `fork`), so nothing above it changes. Its SDK calls are
capability-probed rather than assumed, because the SDK surface has moved
between versions — if your version exposes neither `sandbox.fork()` nor
snapshot creation, it says so and names the method it wanted. **This path has
not been exercised against a live API key**; the local provider is the default
and is what the demo depends on.

## Roadmap

The same machine that audits what you install, auditing what you push.

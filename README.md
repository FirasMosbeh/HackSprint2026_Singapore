<div align="center">

# Sentrya

### Stop choosing libraries by stars. Make them audition.

*Five candidates. Twenty-five sandboxes. One answer backed by evidence.*

</div>

![Sentrya dashboard](docs/screenshot.png)

---

## The 3 a.m. problem

You need to parse `"next Tuesday"` into a `datetime`. You search PyPI and find six
libraries that all claim to do it. So you do what everyone does:

```
dateparser      ★ 2.6k    "Simple and fast"
arrow           ★ 8.8k    "Better dates & times"
parsedatetime   ★ 700     "Parse human-readable dates"
delorean        ★ 1.9k    "Time travel made easy"
```

You pick the one with the most stars, `pip install` it, and move on.

**You just executed arbitrary code from a stranger on your laptop, and the only thing
you checked was a popularity counter.**

Stars measure how many people bookmarked a repo years ago. They don't tell you whether
the package phones home on import, writes outside its directory, crashes on empty
input, or drags in nine transitive dependencies. Nobody chooses dependencies by
evidence, because gathering the evidence means installing six unknown packages and
poking at each one by hand. So nobody does it.

## Why this needs to exist

GitHub already gives you CodeQL, Dependabot and secret scanning. All three read
**source code** and compare it to known patterns. They are good at "does this look
like a known vulnerability."

None of them answer the question you actually have:

> ### What happens when this thing *runs*?

Static analysis can't tell you that a library opens a socket during `import`. It has to
run to find out. Sentrya runs it — and runs its competitors under identical conditions,
so the comparison means something.

```
        "I have six libraries and no idea which to pick."
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │  install each one, in isolation         │
        │  hit it with the same five suites       │
        │  measure what actually happens          │
        └─────────────────────────────────────────┘
                              │
                              ▼
     "I tested them against my requirements. Here's the evidence."
```

That transformation is the product. The scoreboard is just how it's displayed.

## What gets measured

Every candidate faces the same battery. Same inputs, same limits, same clock.

| Suite | The question it answers |
| :-- | :-- |
| 🗂 **Filesystem** | Does it write outside its own directory? Can input escape via `../`? |
| 🎲 **Fuzzing** | What does empty, malformed, enormous or Unicode input do to it? |
| 💉 **Injection** | Does untrusted input reach a shell, a query, a path, a template? |
| 🌐 **Network** | Does it open connections — at import time, or when called? |
| 📊 **Resources** | Peak memory, CPU and disk against a hard ceiling. |

Findings become a score. The score becomes a ranking. Every number on the scoreboard
traces back to something that was observed, and clicking a row shows you the trace.

**No LLM decides the winner.** There is no model in the frontend and no model in the
ranking — the recommendation is a deterministic function of measured output. An AI that
says "I'm 94% confident in dateparser" is worth nothing. `7/7 cases, 0 network calls,
4 dependencies` is worth something.

## How we used Daytona

Running five untrusted packages in parallel is the entire technical problem, and
isolation is what makes it tractable.

**One sandbox per suite, per candidate.** Five candidates × five suites = **25
independent sandboxes** per audition. Not one per candidate — one per *suite*. The
filesystem suite deliberately provokes writes outside the working directory; the
resource suite deliberately pushes memory toward its ceiling. If those shared an
environment, each would be measuring the other's damage. Isolation isn't a safety
checkbox here, it's what makes the measurements *valid*.

The whole `testing/` layer is written against Daytona's sandbox lifecycle:

```python
sandbox = create_sandbox(provider, workdir=...)   # provision
sandbox.clone_repository(subject)                 # place the subject
before = sandbox.snapshot()                       # fingerprint the filesystem
sandbox.execute(cmd, stdin=payload, timeout=8)    # run it under a clock
after  = sandbox.snapshot()                       # diff → filesystem findings
sandbox.destroy()                                 # burn it down
```

That `snapshot → execute → snapshot` sandwich is how the filesystem suite detects
side effects at all: it doesn't read the source looking for `open()` calls, it compares
the environment before and after and reports the delta. Only a disposable environment
makes that possible.

`create_sandbox()` is the seam. `BaseSandbox` defines the contract, `LocalSandbox` and
`DaytonaSandbox` implement it, and swapping providers is one config value —
`TESTING_SANDBOX_PROVIDER`. Nothing in the five suites, the orchestrator, or the UI
knows which one it got.

> **Honest status:** the local provider is what runs today and what produced the
> screenshot above. `DaytonaSandbox` implements the interface but still needs SDK
> wiring — every method currently raises. The architecture is built around Daytona's
> model; the adapter is the last mile.

### A bug worth telling you about

The first parallel run failed spectacularly — every suite drowning in
`FileNotFoundError`. `LocalSandbox` treats its `workdir` as a directory it *owns* and
`rmtree`s on `destroy()`. We handed all 25 sandboxes the same path. The first suite to
finish deleted the environments of the other 24 while they were still running.

Every sandbox now gets its own root. It's the kind of bug you only find by actually
running things in parallel, which is the same reason this project exists.

## Watch it work

```bash
./dev.sh
```

* **App** → <http://localhost:5173>
* **Agent API** → <http://127.0.0.1:8000> · docs at `/docs`

First run creates the virtualenv, installs Python and npm dependencies, and starts both
halves. Ctrl+C stops everything. Needs Python 3.11+ and Node 18+. **No API keys** — the
suites run locally out of the box.

Then: describe what you need, name your candidates, hit **Start Audition**. Suites fill
in left to right as they land — the parallelism is visible, not implied. A five-
candidate run settles in under two seconds.

<details>
<summary>Running the halves separately</summary>

```bash
# agent + testing
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PYTHONPATH=. .venv/bin/python -m uvicorn agent.server:app --port 8000

# app
cd app && npm install && npm run dev
```
</details>

The app probes the agent on startup. If `/api/health` answers it runs live; if not it
falls back to a built-in demo mode, so the interface is never dead in front of an
audience. Override with `VITE_DEMO_MODE=true|false` in `app/.env`.

## How it's built

```text
   app/                    agent/                   testing/
┌──────────────┐  HTTP  ┌──────────────┐  calls  ┌──────────────┐
│  React + TS  │───────▶│ orchestrator │────────▶│  5 suites    │
│  dashboard   │◀───────│  score       │◀────────│  sandboxes   │
└──────────────┘  poll  │  recommend   │ results └──────┬───────┘
                        └──────────────┘                │
                                          ┌─────────────┴─────────────┐
                                          ▼      ▼      ▼      ▼      ▼
                                         FS    FUZZ   INJ    NET    RES
                                          └── one sandbox each ──┘
```

Three components, developed independently, joined by one contract.

| Method | Path | Purpose |
| :-- | :-- | :-- |
| `GET` | `/api/health` | mode detection |
| `POST` | `/api/auditions` | start a run |
| `GET` | `/api/auditions/{id}` | full state, **including partial results** |
| `GET` | `/api/auditions/{id}/status` | just the status |
| `DELETE` | `/api/auditions/{id}` | cancel |

That third endpoint is the interesting one. The orchestrator writes each suite into the
store the *instant* it lands rather than batching at the end, so the dashboard fills in
progressively. A judge watching the screen sees work happening, because work is
happening.

`agent/models.py` and `app/src/types/audition.ts` are the same data model in two
languages — the seam where the Python and TypeScript halves agree. Change one, change
the other.

```text
├── app/        # React + TypeScript dashboard (Vite, zero UI dependencies)
├── agent/      # FastAPI orchestrator — runs candidates, scores, recommends
├── testing/    # Five runtime suites + sandbox lifecycle
└── dev.sh      # Starts everything
```

The frontend never learns *how* an evaluation happens. Replace the entire testing
backend and the UI doesn't change by a line.

## Where it stands

**Working end to end.** Five suites execute in parallel per candidate, results stream
to the dashboard as they land, scores and the recommendation come from measured output,
and one failed sandbox never takes down the scoreboard.

**Scaffolding still in place**, named honestly:

* Candidates are exercised through a generated subject program rather than a real
  `pip install` of the package. The harness is real; the subject is the next milestone.
* `LocalSandbox` is process-level isolation. The Daytona adapter needs SDK wiring
  before genuinely untrusted code should run through it.
* The audition store is in-memory and unbounded.

## Built with

Python · FastAPI · React · TypeScript · Vite · Daytona

<div align="center">

**Don't choose dependencies by popularity.**
**Test them against your actual requirements.**

</div>

# Sentrya — app/

**Stop choosing libraries by stars. Make them audition.**

The frontend for Sentrya: describe what you need, run competing libraries under the
same conditions in isolated environments, and get evidence for your decision instead of
a star count.

This folder contains **only** the web application. The evaluation engine lives in
`agent/` and `testing/` and is reached through one thin service module.

## Run it

From the repository root, `./dev.sh` starts the agent and this app together. To run
just the app:

```bash
cd app
npm install
npm run dev
```

Open http://localhost:5173. The app probes the agent on startup: if `/api/health`
answers it runs live against `agent/` + `testing/`, otherwise it falls back to demo
mode, so it is always usable with or without a backend.

Other scripts: `npm run build`, `npm run preview`, `npm run typecheck`.

## Configuration

Copy `.env.example` to `.env`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `VITE_DEMO_MODE` | unset | Unset auto-detects. `true` forces the mock engine; `false` forces live and surfaces errors instead of falling back. |
| `VITE_API_URL` | empty | Leave empty so requests go through the Vite proxy. Set it to talk to an agent on another host. |
| `VITE_AGENT_URL` | `http://127.0.0.1:8000` | Where the dev-server proxy forwards `/api`. |

If the agent is unreachable, the app falls back to demo mode and says so in the header
rather than dead-ending.

## Integration boundary

The UI never knows *how* an evaluation is performed — only what it produces.
Everything backend-related goes through [`src/services/auditionApi.ts`](src/services/auditionApi.ts):

```ts
startAudition(request): Promise<Audition>
getAuditionStatus(id):  Promise<{ id, status }>
getAuditionResults(id): Promise<Audition>
cancelAudition(id):     Promise<void>
```

Expected HTTP endpoints when `VITE_DEMO_MODE=false`:

| Method | Path | Returns |
| --- | --- | --- |
| `GET` | `/api/health` | `{ status }` — used for mode detection |
| `POST` | `/api/auditions` | `Audition` (status `queued`/`running`) |
| `GET` | `/api/auditions/:id` | `Audition` with all partial results so far |
| `GET` | `/api/auditions/:id/status` | `{ id, status }` |
| `DELETE` | `/api/auditions/:id` | cancel a run |

`GET /api/auditions/:id` is polled while a run is in flight and should return whatever
is known so far — partial results are expected and rendered progressively. Every field
on `CandidateResult` except `candidate` and `status` is optional; missing data renders as
`—` and never breaks the scoreboard.

### Test suites

Every candidate runs the same five-suite battery, in this order:

| Suite | What it checks |
| --- | --- |
| `filesystem` | Writes outside the sandbox working directory |
| `fuzzing` | Behaviour under malformed and hostile input |
| `injection` | Evaluation of untrusted input (eval/format-string style) |
| `network` | Outbound connections at import and at call time |
| `resources` | Memory and CPU against the configured limits |

Each one is reported as a `TestSuite` on `CandidateResult.suites`:

```ts
{ name: "network", status: "failed", passed: 1, total: 3,
  durationMs: 1450, summary: "…", findings: ["…"] }
```

Suites render as compact pass/fail pips in the scoreboard (`FS FUZZ INJ NET RES`) and
expand into full per-suite findings when a row is opened. They arrive progressively —
send each suite as it lands and the columns fill in live. `status: "skipped"` is the
right value when a candidate never installed. The names are a convention, not a
constraint: `TestSuite.name` is a plain string, so adding a sixth suite needs no
frontend change.

`status` accepts the app's vocabulary (`queued`, `running`, `passed`, `failed`,
`skipped`, `error`) plus `warning` and `inconclusive`, which the testing package
distinguishes: `warning` ran clean but produced signals worth reviewing,
`inconclusive` ran without reaching a verdict.

The full data model is in [`src/types/audition.ts`](src/types/audition.ts) — that file is
the contract shared with `agent/` and `testing/`.

Swapping polling for a WebSocket or SSE stream later only touches
[`src/hooks/useAudition.ts`](src/hooks/useAudition.ts).

**The recommendation is produced by the backend/agent.** The frontend renders the verdict
and its supporting evidence; it never scores or picks a winner itself, and contains no LLM.

## Demo mode

`src/services/mockEngine.ts` simulates a realistic run: sandboxes provision, packages
install, tests execute, and results land one candidate at a time with staggered timing.
It deliberately produces mixed outcomes — a clear winner, two partial passes, one
candidate that fails to install, and one with runtime-behaviour findings — so every UI
state is visible in a single demo. Unknown libraries typed by the user still get
plausible results, so the demo never breaks off-script.

Final mock outcomes live in `src/data/mockResults.ts`.

## Structure

```
src/
├── components/
│   ├── RequirementInput.tsx     what the user needs, in plain language
│   ├── CandidateSelector.tsx    add/remove candidates (any number)
│   ├── AuditionButton.tsx       start / cancel / reset
│   ├── ResultsTable.tsx         the scoreboard — the centerpiece
│   ├── CandidateRow.tsx         one candidate, expandable
│   ├── CandidateDetails.tsx     the evidence behind a result
│   ├── SuitePips.tsx            the five suites, one table cell
│   ├── SuiteBreakdown.tsx       per-suite findings, when expanded
│   ├── ScoreComparison.tsx      compact score bars
│   ├── SandboxGrid.tsx          isolated + parallel, made visible
│   ├── RecommendationCard.tsx   the backend's verdict
│   ├── BrandMark.tsx            the Sentrya mark
│   ├── ScoreBar.tsx
│   └── StatusBadge.tsx
├── services/
│   ├── auditionApi.ts           the only module that knows a backend exists
│   └── mockEngine.ts            demo-mode stand-in for agent/ + testing/
├── hooks/useAudition.ts         run lifecycle + progressive polling
├── types/audition.ts            shared data model
├── data/mockResults.ts          demo fixtures
├── pages/AuditionPage.tsx       the dashboard
├── App.tsx
└── styles.css
```

## Error handling

One bad sandbox never breaks the scoreboard. Installation failures, timeouts, sandbox
errors and a missing backend each render as their own state with the rest of the results
intact.

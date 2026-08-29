import type {
  Audition,
  AuditionRequest,
  CandidateResult,
} from "../types/audition";
import { allSuitesPassed, MOCK_OUTCOMES, MOCK_RECOMMENDATION } from "../data/mockResults";

/**
 * An in-memory stand-in for the agent + Daytona testing infrastructure.
 *
 * It exists purely so the frontend can be developed, demoed and reviewed while
 * agent/ and testing/ are built independently. It mimics the *shape* and
 * *timing* of a real run: sandboxes boot, packages install, tests execute, and
 * results land one candidate at a time.
 */

interface MockRun {
  audition: Audition;
  timers: number[];
}

const runs = new Map<string, MockRun>();

let counter = 0;
function nextId(): string {
  counter += 1;
  return `aud_${Date.now().toString(36)}_${counter}`;
}

/** Randomised but bounded, so the demo is lively without ever dragging. */
function jitter(base: number, spread = 0.35): number {
  return Math.round(base * (1 - spread + Math.random() * spread * 2));
}

function outcomeFor(name: string): Omit<CandidateResult, "candidate"> {
  const known = MOCK_OUTCOMES[name.toLowerCase()];
  if (known) return known;

  // Unknown candidates still get a plausible result so the demo never breaks
  // when a user types their own library name.
  const passed = 3 + Math.floor(Math.random() * 5);
  return {
    status: "passed",
    installation: { passed: true, durationMs: jitter(2500) },
    tests: { passed, total: 7 },
    suites: allSuitesPassed([4, 24, 8, 3, 5]),
    performance: {
      executionTimeMs: jitter(90),
      memoryMb: jitter(35),
    },
    dependencies: { count: 1 + Math.floor(Math.random() * 8) },
    runtimeBehaviour: {
      networkActivity: false,
      filesystemChanges: 0,
      spawnedProcesses: 0,
      summary: "No unexpected runtime activity.",
    },
    sourceAnalysis: { status: "clean", findings: [], summary: "No significant findings." },
    score: 45 + passed * 6,
  };
}

function schedule(run: MockRun, delay: number, fn: () => void): void {
  run.timers.push(window.setTimeout(fn, delay));
}

export function createMockAudition(request: AuditionRequest): Audition {
  const id = nextId();
  const audition: Audition = {
    id,
    status: "running",
    requirement: request.requirement,
    startedAt: new Date().toISOString(),
    candidates: request.candidates.map((candidate) => ({
      candidate,
      status: "queued",
      stage: "waiting for sandbox",
    })),
  };

  const run: MockRun = { audition, timers: [] };
  runs.set(id, run);

  const update = (index: number, patch: Partial<CandidateResult>) => {
    const current = run.audition.candidates[index];
    if (!current) return;
    run.audition.candidates = run.audition.candidates.map((c, i) =>
      i === index ? { ...c, ...patch } : c,
    );
  };

  request.candidates.forEach((candidate, index) => {
    const outcome = outcomeFor(candidate.name);
    // Sandboxes boot in parallel, but not perfectly in lockstep.
    const boot = jitter(700) + index * jitter(180);
    const install = boot + jitter(1900);
    const finish = install + jitter(2600);

    schedule(run, boot, () =>
      update(index, { status: "running", stage: "provisioning sandbox" }),
    );
    schedule(run, install, () =>
      update(index, { status: "running", stage: "installing package" }),
    );

    if (outcome.installation?.passed === false) {
      // Failed installs resolve early — there is nothing left to test.
      schedule(run, install + jitter(900), () =>
        update(index, { ...outcome, stage: undefined }),
      );
      return;
    }

    const suites = outcome.suites ?? [];
    const testsStart = install + jitter(800);

    schedule(run, testsStart, () =>
      update(index, {
        status: "running",
        stage: suites.length ? `running ${suites[0].name} suite` : "running use-case tests",
        installation: outcome.installation,
        // The battery is announced up front so the columns never shift.
        suites: suites.map((suite) => ({ ...suite, status: "queued" as const })),
      }),
    );

    // Suites land one at a time, so the scoreboard fills in visibly.
    const suiteWindow = Math.max(finish - testsStart, 600);
    suites.forEach((_suite, suiteIndex) => {
      const at = testsStart + (suiteWindow * (suiteIndex + 1)) / (suites.length + 1);
      schedule(run, at, () =>
        update(index, {
          stage: suites[suiteIndex + 1]
            ? `running ${suites[suiteIndex + 1].name} suite`
            : "scoring",
          suites: suites.map((entry, i) =>
            i <= suiteIndex ? entry : { ...entry, status: "queued" as const },
          ),
        }),
      );
    });

    schedule(run, finish, () => update(index, { ...outcome, stage: undefined }));
  });

  // Everything above lands well before this; the recommendation closes the run.
  const total = 1200 + request.candidates.length * 260 + 5200;
  schedule(run, total, () => {
    const scored = run.audition.candidates
      .filter((c) => typeof c.score === "number")
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    const winner = scored[0];

    run.audition = {
      ...run.audition,
      status: "completed",
      completedAt: new Date().toISOString(),
      recommendation: winner
        ? winner.candidate.name.toLowerCase() === MOCK_RECOMMENDATION.candidate
          ? MOCK_RECOMMENDATION
          : {
              candidate: winner.candidate.name,
              score: winner.score ?? 0,
              explanation: `${winner.candidate.name} produced the strongest overall fit for the stated requirement based on the measured evaluation results.`,
              strengths: [
                `${winner.tests?.passed ?? 0}/${winner.tests?.total ?? 0} use-case tests passed`,
                "Installed cleanly in the target environment",
                winner.runtimeBehaviour?.summary ?? "Runtime behaviour recorded",
              ],
            }
        : undefined,
      error: winner ? undefined : "No candidate completed evaluation successfully.",
    };
  });

  return snapshot(audition);
}

export function getMockAudition(id: string): Audition | undefined {
  const run = runs.get(id);
  return run ? snapshot(run.audition) : undefined;
}

export function cancelMockAudition(id: string): void {
  const run = runs.get(id);
  if (!run) return;
  run.timers.forEach((t) => window.clearTimeout(t));
  runs.delete(id);
}

/** Deep-ish copy so React always sees new references for changed data. */
function snapshot(audition: Audition): Audition {
  return { ...audition, candidates: audition.candidates.map((c) => ({ ...c })) };
}

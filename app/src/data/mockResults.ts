import type {
  Candidate,
  CandidateResult,
  Recommendation,
  TestSuite,
} from "../types/audition";
import { TEST_SUITES } from "../types/audition";

export const DEFAULT_REQUIREMENT =
  'I need a Python library that can parse human-written dates such as "next Tuesday", "tomorrow at 5pm", and "last Friday" into datetime objects.';

export const DEFAULT_CANDIDATES: Candidate[] = [
  { name: "dateparser", package: "dateparser", ecosystem: "pypi" },
  { name: "arrow", package: "arrow", ecosystem: "pypi" },
  { name: "parsedatetime", package: "parsedatetime", ecosystem: "pypi" },
  { name: "delorean", package: "delorean", ecosystem: "pypi" },
  { name: "chrono", package: "chrono-python", ecosystem: "pypi" },
];

/** Every candidate runs the same five suites, in this order. */
export function allSuitesPassed(counts: number[]): TestSuite[] {
  return TEST_SUITES.map((name, i) => ({
    name,
    status: "passed" as const,
    passed: counts[i],
    total: counts[i],
    summary: "No issues observed.",
  }));
}

/** Install failures never reach the battery, so every suite is skipped. */
export const SKIPPED_SUITES: TestSuite[] = TEST_SUITES.map((name) => ({
  name,
  status: "skipped" as const,
  summary: "Not run — the candidate never installed.",
}));

/**
 * Final outcomes the mock engine converges on. Deliberately mixed: a clear
 * winner, a couple of partial passes, and one candidate that never installs.
 */
export const MOCK_OUTCOMES: Record<string, Omit<CandidateResult, "candidate">> = {
  dateparser: {
    status: "passed",
    installation: { passed: true, durationMs: 3120 },
    tests: { passed: 7, total: 7 },
    suites: allSuitesPassed([4, 24, 8, 3, 5]),
    performance: { executionTimeMs: 82, memoryMb: 41, cpuTimeMs: 74 },
    dependencies: { count: 4, sizeMb: 12.4 },
    runtimeBehaviour: {
      networkActivity: false,
      filesystemChanges: 0,
      spawnedProcesses: 0,
      summary: "No unexpected network, filesystem or process activity.",
    },
    sourceAnalysis: {
      status: "clean",
      findings: [],
      summary: "No significant findings.",
    },
    score: 92,
  },
  arrow: {
    status: "passed",
    installation: { passed: true, durationMs: 1840 },
    tests: {
      passed: 4,
      total: 7,
      failures: [
        {
          name: '"next Tuesday"',
          expected: "2026-09-01T00:00:00",
          actual: "ParserError: could not match input",
          explanation: "Relative weekday expressions are not supported.",
        },
        {
          name: '"in three weeks"',
          expected: "2026-09-19T00:00:00",
          actual: "ParserError: could not match input",
          explanation: "Relative offsets written in words are not parsed.",
        },
        {
          name: '"tomorrow at 5pm"',
          expected: "2026-08-30T17:00:00",
          actual: "ParserError: could not match input",
          explanation: "Only ISO-like and explicitly formatted inputs are handled.",
        },
      ],
    },
    suites: [
      { name: "filesystem", status: "passed", passed: 4, total: 4, durationMs: 120, summary: "No writes outside the sandbox working directory." },
      { name: "fuzzing", status: "failed", passed: 18, total: 24, durationMs: 2140, summary: "6 malformed inputs raised uncaught exceptions instead of a parse error.", findings: ["Uncaught TypeError on empty string input.", "Uncaught OverflowError on a 10^6-digit year."] },
      { name: "injection", status: "passed", passed: 8, total: 8, durationMs: 310, summary: "No format-string or eval-style evaluation of untrusted input." },
      { name: "network", status: "passed", passed: 3, total: 3, durationMs: 90, summary: "No outbound connections during import or parsing." },
      { name: "resources", status: "passed", passed: 5, total: 5, durationMs: 640, summary: "Memory and CPU stayed within the configured limits." },
    ],
    performance: { executionTimeMs: 41, memoryMb: 23, cpuTimeMs: 38 },
    dependencies: { count: 1, sizeMb: 2.1 },
    runtimeBehaviour: {
      networkActivity: false,
      filesystemChanges: 0,
      spawnedProcesses: 0,
      summary: "No unexpected runtime activity.",
    },
    sourceAnalysis: { status: "clean", findings: [], summary: "No significant findings." },
    score: 71,
  },
  parsedatetime: {
    status: "passed",
    installation: { passed: true, durationMs: 1520 },
    tests: {
      passed: 6,
      total: 7,
      failures: [
        {
          name: '"last Friday"',
          expected: "2026-08-28T00:00:00",
          actual: "2026-09-04T00:00:00",
          explanation: "Past-facing weekday expressions resolve to the next occurrence.",
        },
      ],
    },
    suites: [
      { name: "filesystem", status: "passed", passed: 4, total: 4, durationMs: 130, summary: "No writes outside the sandbox working directory." },
      { name: "fuzzing", status: "failed", passed: 21, total: 24, durationMs: 2560, summary: "3 malformed inputs hung past the per-case timeout.", findings: ["Repeated-token input did not terminate within 2s."] },
      { name: "injection", status: "passed", passed: 8, total: 8, durationMs: 290, summary: "Untrusted input is never evaluated." },
      { name: "network", status: "passed", passed: 3, total: 3, durationMs: 85, summary: "No outbound connections observed." },
      { name: "resources", status: "passed", passed: 5, total: 5, durationMs: 700, summary: "Stayed within memory and CPU limits." },
    ],
    performance: { executionTimeMs: 67, memoryMb: 31, cpuTimeMs: 61 },
    dependencies: { count: 1, sizeMb: 3.0 },
    runtimeBehaviour: {
      networkActivity: false,
      filesystemChanges: 0,
      spawnedProcesses: 0,
      summary: "No unexpected runtime activity.",
    },
    sourceAnalysis: { status: "clean", findings: [], summary: "No significant findings." },
    score: 78,
  },
  delorean: {
    status: "failed",
    installation: {
      passed: false,
      durationMs: 4200,
      error:
        "Build failed: incompatible with Python 3.13 (uses removed `distutils` API). Candidate excluded from functional testing.",
    },
    suites: SKIPPED_SUITES,
    dependencies: { count: 6 },
    score: undefined,
  },
  chrono: {
    status: "passed",
    installation: { passed: true, durationMs: 5300 },
    tests: {
      passed: 5,
      total: 7,
      failures: [
        {
          name: '"last Friday"',
          expected: "2026-08-28T00:00:00",
          actual: "None",
          explanation: "Returned no match for past relative dates.",
        },
        {
          name: '"in three weeks"',
          expected: "2026-09-19T00:00:00",
          actual: "2026-09-19T12:00:00",
          explanation: "Defaulted to midday instead of midnight.",
        },
      ],
    },
    suites: [
      { name: "filesystem", status: "failed", passed: 2, total: 4, durationMs: 210, summary: "Wrote 2 files outside the sandbox working directory.", findings: ["Created ~/.chrono/cache.db without opt-in.", "Wrote a log file to /tmp on every import."] },
      { name: "fuzzing", status: "passed", passed: 24, total: 24, durationMs: 3100, summary: "All malformed inputs handled without crashing." },
      { name: "injection", status: "passed", passed: 8, total: 8, durationMs: 340, summary: "No evaluation of untrusted input." },
      { name: "network", status: "failed", passed: 1, total: 3, durationMs: 1450, summary: "Contacted an external host at import time.", findings: ["POST to telemetry.chrono.dev during module import.", "No way to disable the call via configuration."] },
      { name: "resources", status: "passed", passed: 5, total: 5, durationMs: 880, summary: "Within limits, though peak memory was the highest of the field." },
    ],
    performance: { executionTimeMs: 95, memoryMb: 62, cpuTimeMs: 88 },
    dependencies: { count: 9, sizeMb: 28.7 },
    runtimeBehaviour: {
      networkActivity: true,
      filesystemChanges: 2,
      spawnedProcesses: 1,
      summary:
        "Contacted an external host during import and wrote 2 files outside the working directory.",
    },
    sourceAnalysis: {
      status: "warning",
      findings: [
        "Network call issued at import time (telemetry endpoint).",
        "Writes a cache file to the user home directory without opt-in.",
      ],
      summary: "2 findings worth reviewing before adoption.",
    },
    score: 69,
  },
};

export const MOCK_RECOMMENDATION: Recommendation = {
  candidate: "dateparser",
  score: 92,
  explanation:
    "dateparser was the only candidate that correctly interpreted every requested natural-language format, and it did so with clean runtime behaviour and a modest dependency footprint.",
  strengths: [
    "7/7 use-case tests passed",
    "Compatible with the target environment",
    "Clean runtime behaviour — no network, filesystem or process side effects",
    "4 dependencies, 12.4 MB installed",
  ],
  weaknesses: ["Slower than arrow (82 ms vs 41 ms) on the same workload"],
};

/**
 * Shared data model between the app, the agent and the testing infrastructure.
 *
 * This file is the integration boundary. The frontend knows *what* an
 * evaluation produces, never *how* it is produced.
 */

export type AuditionStatus = "queued" | "running" | "completed" | "failed";

export type CandidateStatus =
  | "queued"
  | "running"
  | "passed"
  /** Fully evaluated, but the suites reported findings. */
  | "findings"
  | "failed"
  | "error";

export interface Candidate {
  name: string;
  package: string;
  version?: string;
  ecosystem: string;
}

/**
 * The fixed battery every candidate runs. Names are stable so the app, the
 * agent and the testing infrastructure agree on what each suite means; the
 * `TestSuite.name` field stays a plain string so the backend can add more
 * without a frontend change.
 */
export const TEST_SUITES = [
  "filesystem",
  "fuzzing",
  "injection",
  "network",
  "resources",
] as const;

export type TestSuiteName = (typeof TEST_SUITES)[number];

export type TestSuiteStatus =
  | "queued"
  | "running"
  | "passed"
  /** Ran clean but produced signals worth reviewing. */
  | "warning"
  | "failed"
  /** Ran but could not reach a verdict. */
  | "inconclusive"
  | "skipped"
  | "error";

/** Compact labels for the scoreboard, where horizontal space is scarce. */
export const SUITE_LABELS: Record<string, string> = {
  filesystem: "FS",
  fuzzing: "FUZZ",
  injection: "INJ",
  network: "NET",
  resources: "RES",
};

export function suiteLabel(name: string): string {
  return SUITE_LABELS[name] ?? name.slice(0, 4).toUpperCase();
}

export interface TestSuite {
  name: string;
  status: TestSuiteStatus;
  passed?: number;
  total?: number;
  durationMs?: number;
  summary?: string;
  findings?: string[];
}

export interface TestFailure {
  name: string;
  expected: string;
  actual: string;
  explanation?: string;
}

export interface CandidateResult {
  candidate: Candidate;
  status: CandidateStatus;
  /** Free-form progress label, e.g. "installing", "running tests". */
  stage?: string;
  installation?: {
    passed: boolean;
    durationMs?: number;
    error?: string;
  };
  tests?: {
    passed: number;
    total: number;
    failures?: TestFailure[];
  };
  /** Per-suite breakdown: filesystem, fuzzing, injection, network, resources. */
  suites?: TestSuite[];
  performance?: {
    executionTimeMs?: number;
    memoryMb?: number;
    cpuTimeMs?: number;
  };
  dependencies?: {
    count?: number;
    sizeMb?: number;
  };
  runtimeBehaviour?: {
    networkActivity?: boolean;
    filesystemChanges?: number;
    spawnedProcesses?: number;
    summary?: string;
  };
  sourceAnalysis?: {
    status?: "clean" | "warning" | "error";
    findings?: string[];
    summary?: string;
  };
  /** Why a candidate ended in `error` — sandbox died, timed out, etc. */
  error?: string;
  score?: number;
}

export interface Recommendation {
  candidate: string;
  score: number;
  explanation: string;
  strengths: string[];
  weaknesses?: string[];
}

export interface Audition {
  id: string;
  status: AuditionStatus;
  requirement: string;
  candidates: CandidateResult[];
  recommendation?: Recommendation;
  startedAt?: string;
  completedAt?: string;
  error?: string;
}

export interface AuditionRequest {
  requirement: string;
  candidates: Candidate[];
}

export const TERMINAL_CANDIDATE_STATUSES: CandidateStatus[] = [
  "passed",
  "findings",
  "failed",
  "error",
];

export function isTerminal(status: AuditionStatus): boolean {
  return status === "completed" || status === "failed";
}

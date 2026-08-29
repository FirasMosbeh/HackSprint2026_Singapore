import type { CandidateStatus } from "../types/audition";

const LABELS: Record<CandidateStatus, string> = {
  queued: "Queued",
  running: "Running",
  passed: "Clean",
  findings: "Findings",
  failed: "Failed",
  error: "Error",
};

const GLYPHS: Record<CandidateStatus, string> = {
  queued: "○",
  running: "●",
  passed: "✓",
  findings: "!",
  failed: "✗",
  error: "⚠",
};

export function StatusBadge({
  status,
  label,
}: {
  status: CandidateStatus;
  label?: string;
}) {
  return (
    <span className={`badge badge--${status}`}>
      <span className={status === "running" ? "badge__glyph pulse" : "badge__glyph"}>
        {GLYPHS[status]}
      </span>
      {label ?? LABELS[status]}
    </span>
  );
}

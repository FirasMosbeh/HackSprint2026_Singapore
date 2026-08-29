import type { TestSuite } from "../types/audition";
import { suiteLabel } from "../types/audition";

/** Compact one-glance view of the five suites, sized for a table cell. */
export function SuitePips({ suites }: { suites?: TestSuite[] }) {
  if (!suites || suites.length === 0) {
    return <span className="muted">—</span>;
  }

  return (
    <span className="pips">
      {suites.map((suite) => (
        <span
          key={suite.name}
          className={`pip pip--${suite.status}`}
          title={`${suite.name}: ${suite.status}${
            suite.total != null ? ` (${suite.passed ?? 0}/${suite.total})` : ""
          }`}
        >
          {suiteLabel(suite.name)}
        </span>
      ))}
    </span>
  );
}

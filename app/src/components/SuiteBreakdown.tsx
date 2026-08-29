import type { TestSuite } from "../types/audition";

const GLYPHS: Record<TestSuite["status"], string> = {
  queued: "○",
  running: "●",
  passed: "✓",
  failed: "✗",
  skipped: "–",
  error: "⚠",
};

/** The full per-suite evidence, shown when a candidate row is expanded. */
export function SuiteBreakdown({ suites }: { suites?: TestSuite[] }) {
  if (!suites || suites.length === 0) return null;

  return (
    <div className="suites">
      <h4 className="suites__title">Test suites</h4>
      <div className="suites__list">
        {suites.map((suite) => (
          <div className={`suite suite--${suite.status}`} key={suite.name}>
            <div className="suite__head">
              <span className="suite__glyph">{GLYPHS[suite.status]}</span>
              <span className="suite__name">{suite.name}</span>
              <span className="suite__count">
                {suite.status === "skipped"
                  ? "skipped"
                  : suite.total != null
                    ? `${suite.passed ?? 0}/${suite.total}`
                    : suite.status}
              </span>
            </div>

            {suite.summary && <p className="suite__summary">{suite.summary}</p>}

            {suite.findings && suite.findings.length > 0 && (
              <ul className="suite__findings">
                {suite.findings.map((finding) => (
                  <li key={finding}>{finding}</li>
                ))}
              </ul>
            )}

            {suite.durationMs != null && (
              <span className="suite__duration">{suite.durationMs} ms</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

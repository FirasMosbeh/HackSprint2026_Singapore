import type { CandidateResult } from "../types/audition";
import { StatusBadge } from "./StatusBadge";

/**
 * Secondary to the scoreboard: its only job is to make the parallel, isolated
 * nature of the evaluation obvious at a glance.
 */
export function SandboxGrid({ results }: { results: CandidateResult[] }) {
  if (results.length === 0) return null;

  return (
    <section className="panel">
      <header className="panel__head">
        <h2 className="panel__title">Daytona sandboxes</h2>
        <span className="panel__hint">
          Each candidate is installed and tested in its own isolated environment, in parallel.
        </span>
      </header>

      <div className="sandboxes">
        {results.map((result, index) => (
          <div
            key={result.candidate.name}
            className={`sandbox sandbox--${result.status}`}
          >
            <div className="sandbox__id">
              Sandbox {String(index + 1).padStart(2, "0")}
            </div>
            <div className="sandbox__name">{result.candidate.name}</div>
            <StatusBadge status={result.status} />
            {result.stage && <div className="sandbox__stage">{result.stage}</div>}
          </div>
        ))}
      </div>
    </section>
  );
}

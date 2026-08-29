import type { ReactNode } from "react";
import type { CandidateResult } from "../types/audition";
import { CandidateDetails } from "./CandidateDetails";
import { ScoreBar } from "./ScoreBar";
import { SuiteBreakdown } from "./SuiteBreakdown";
import { SuitePips } from "./SuitePips";
import { StatusBadge } from "./StatusBadge";

const COLUMN_COUNT = 9;

function dash(value: ReactNode, fallback = "—") {
  return value === null || value === undefined || value === "" ? (
    <span className="muted">{fallback}</span>
  ) : (
    value
  );
}

export function CandidateRow({
  result,
  expanded,
  onToggle,
  isWinner,
}: {
  result: CandidateResult;
  expanded: boolean;
  onToggle: () => void;
  isWinner: boolean;
}) {
  const { tests, performance, dependencies, installation, sourceAnalysis } = result;

  return (
    <>
      <tr
        className={`row row--${result.status}${expanded ? " row--open" : ""}${
          isWinner ? " row--winner" : ""
        }`}
        onClick={onToggle}
        tabIndex={0}
        role="button"
        aria-expanded={expanded}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onToggle();
          }
        }}
      >
        <td className="cell cell--name">
          <span className="row__caret" aria-hidden>
            {expanded ? "▾" : "▸"}
          </span>
          <span className="row__name">{result.candidate.name}</span>
          {isWinner && (
            <span className="row__best" title="Recommended">BEST FIT</span>
          )}
        </td>

        <td className="cell">
          <StatusBadge status={result.status} />
          {result.stage && <div className="row__stage">{result.stage}</div>}
        </td>

        <td className="cell cell--num">
          {installation
            ? installation.passed
              ? <span className="ok">✓</span>
              : <span className="bad">✗</span>
            : dash(null)}
        </td>

        <td className="cell cell--suites">
          <SuitePips suites={result.suites} />
        </td>

        <td className="cell cell--num">
          {tests ? (
            <span className={tests.passed === tests.total ? "ok" : "warn"}>
              {tests.passed}/{tests.total}
            </span>
          ) : (
            dash(null)
          )}
        </td>

        <td className="cell cell--num">
          {dash(performance?.executionTimeMs != null ? `${performance.executionTimeMs} ms` : null)}
        </td>

        <td className="cell cell--num">
          {dash(performance?.memoryMb != null ? `${performance.memoryMb} MB` : null)}
        </td>

        <td className="cell cell--num">{dash(dependencies?.count ?? null)}</td>

        <td className="cell cell--score">
          <ScoreBar score={result.score} best={isWinner} />
        </td>
      </tr>

      {expanded && (
        <tr className="row-detail">
          <td colSpan={COLUMN_COUNT}>
            <SuiteBreakdown suites={result.suites} />
            <CandidateDetails result={result} />
            {sourceAnalysis?.status === "warning" && (
              <p className="detail__note detail__note--warn">
                ⚠ Review the source-analysis findings before adopting this candidate.
              </p>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

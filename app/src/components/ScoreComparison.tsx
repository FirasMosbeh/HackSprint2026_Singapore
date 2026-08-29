import type { CandidateResult } from "../types/audition";

/** Compact bar comparison — the table stays the source of truth. */
export function ScoreComparison({
  results,
  winner,
}: {
  results: CandidateResult[];
  winner?: string;
}) {
  const scored = results.filter((r) => typeof r.score === "number");
  if (scored.length === 0) return null;

  const ordered = [...results].sort(
    (a, b) => (b.score ?? -1) - (a.score ?? -1),
  );

  return (
    <div className="comparison">
      {ordered.map((result) => {
        const isWinner =
          !!winner && winner.toLowerCase() === result.candidate.name.toLowerCase();
        return (
          <div className="comparison__row" key={result.candidate.name}>
            <span className="comparison__name">{result.candidate.name}</span>
            <span className="comparison__track">
              {typeof result.score === "number" ? (
                <span
                  className={`comparison__fill${isWinner ? " comparison__fill--best" : ""}`}
                  style={{ width: `${Math.min(result.score, 100)}%` }}
                />
              ) : (
                <span className="comparison__none" />
              )}
            </span>
            <span className="comparison__value">
              {typeof result.score === "number" ? (
                result.score
              ) : (
                <span className="bad">
                  {result.installation?.passed === false ? "FAILED" : "—"}
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

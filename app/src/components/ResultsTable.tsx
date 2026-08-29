import { useState } from "react";
import type { CandidateResult } from "../types/audition";
import { CandidateRow } from "./CandidateRow";

const COLUMNS = [
  "Candidate",
  "Status",
  "Install",
  "Suites",
  "Tests",
  "Time",
  "Memory",
  "Deps",
  "Score",
];

function rank(result: CandidateResult): number {
  // Scored candidates first (highest score wins), then everything unscored.
  return typeof result.score === "number" ? -result.score : 1000;
}

export function ResultsTable({
  results,
  winner,
}: {
  results: CandidateResult[];
  winner?: string;
}) {
  const [open, setOpen] = useState<string | null>(null);

  const ordered = [...results].sort((a, b) => rank(a) - rank(b));

  return (
    <section className="panel panel--primary">
      <header className="panel__head">
        <h2 className="panel__title">Audition results</h2>
        <span className="panel__hint">
          Measured in isolated environments. Click a row for the evidence.
        </span>
      </header>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column} className={column === "Candidate" ? "" : "th--num"}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ordered.map((result) => (
              <CandidateRow
                key={result.candidate.name}
                result={result}
                expanded={open === result.candidate.name}
                isWinner={
                  !!winner &&
                  winner.toLowerCase() === result.candidate.name.toLowerCase()
                }
                onToggle={() =>
                  setOpen((current) =>
                    current === result.candidate.name ? null : result.candidate.name,
                  )
                }
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

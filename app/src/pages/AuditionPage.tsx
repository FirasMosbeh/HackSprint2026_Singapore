import { useMemo, useState } from "react";
import { AuditionButton } from "../components/AuditionButton";
import { BrandMark } from "../components/BrandMark";
import { CandidateSelector } from "../components/CandidateSelector";
import { RecommendationCard } from "../components/RecommendationCard";
import { RequirementInput } from "../components/RequirementInput";
import { ResultsTable } from "../components/ResultsTable";
import { SandboxGrid } from "../components/SandboxGrid";
import { ScoreComparison } from "../components/ScoreComparison";
import { DEFAULT_CANDIDATES, DEFAULT_REQUIREMENT } from "../data/mockResults";
import { useAudition } from "../hooks/useAudition";
import type { Candidate } from "../types/audition";

export function AuditionPage() {
  const [requirement, setRequirement] = useState(DEFAULT_REQUIREMENT);
  const [candidates, setCandidates] = useState<Candidate[]>(DEFAULT_CANDIDATES);

  const { audition, isStarting, isRunning, error, mode, start, reset } = useAudition();

  const results = audition?.candidates ?? [];
  const winner = audition?.recommendation?.candidate;
  const winnerResult = useMemo(
    () =>
      winner
        ? results.find(
            (r) => r.candidate.name.toLowerCase() === winner.toLowerCase(),
          )
        : undefined,
    [results, winner],
  );

  const settled = results.filter((r) => r.status !== "queued" && r.status !== "running");
  const canStart = requirement.trim().length > 0 && candidates.length > 0;
  const finished = audition ? !isRunning : false;

  return (
    <div className="page">
      <header className="masthead">
        <div className="masthead__glow" aria-hidden />

        <div className="masthead__bar">
          <div className="masthead__brand">
            <BrandMark />
            <div className="masthead__words">
              <h1 className="masthead__title">SENTRYA</h1>
              <p className="masthead__kicker">Open source code selection made easy...</p>
            </div>
          </div>

          <div className="masthead__status">
            <span
              className={`conn ${
                mode.demo ? "conn--demo" : mode.connected ? "conn--live" : "conn--down"
              }`}
            >
              <span className="conn__dot" />
              {mode.demo ? "Demo mode" : mode.connected ? "Connected" : "Backend unavailable"}
            </span>
            {mode.reason && <span className="masthead__reason">{mode.reason}</span>}
          </div>
        </div>

        <p className="masthead__tagline">
          Stop choosing libraries by stars. <em>Make them audition.</em>
        </p>

        <div className="masthead__steps">
          <span className="masthead__step">Describe the requirement</span>
          <span className="masthead__sep" aria-hidden />
          <span className="masthead__step">Run every candidate in isolation</span>
          <span className="masthead__sep" aria-hidden />
          <span className="masthead__step">Decide on measured evidence</span>
        </div>
      </header>

      <main className="layout">
        <div className="column column--input">
          <RequirementInput
            value={requirement}
            onChange={setRequirement}
            disabled={isRunning}
          />
          <CandidateSelector
            candidates={candidates}
            onChange={setCandidates}
            disabled={isRunning}
          />
          <AuditionButton
            onStart={() => void start({ requirement, candidates })}
            onReset={reset}
            running={isRunning}
            starting={isStarting}
            canStart={canStart}
            finished={finished}
          />

          {error && (
            <div className="alert alert--error">
              <strong>⚠ {error}</strong>
              <span>Existing results are preserved below.</span>
            </div>
          )}

          {audition?.status === "failed" && (
            <div className="alert alert--error">
              <strong>⚠ Audition failed</strong>
              <span>{audition.error ?? "The evaluation run did not complete."}</span>
            </div>
          )}

          {audition && (
            <div className="run-meta">
              <span className="run-meta__id">{audition.id}</span>
              <span>
                {settled.length}/{results.length} candidates settled
              </span>
            </div>
          )}
        </div>

        <div className="column column--results">
          {!audition ? (
            <EmptyState />
          ) : (
            <>
              <ResultsTable results={results} winner={winner} />
              <ScoreComparison results={results} winner={winner} />
              <SandboxGrid results={results} />
              {audition.recommendation ? (
                <RecommendationCard
                  recommendation={audition.recommendation}
                  result={winnerResult}
                />
              ) : (
                isRunning && (
                  <div className="pending">
                    Recommendation appears once every candidate has been measured.
                  </div>
                )
              )}
            </>
          )}
        </div>
      </main>

      <footer className="footer">
        Audition runs competing libraries under the same conditions, measures what actually
        happens, and gives you evidence for your decision.
      </footer>
    </div>
  );
}

function EmptyState() {
  return (
    <section className="panel panel--primary empty">
      <div className="empty__flow">
        <span>What do I need?</span>
        <span className="empty__arrow">↓</span>
        <span>N candidate libraries</span>
        <span className="empty__arrow">↓</span>
        <span className="empty__box">Isolated sandboxes · in parallel</span>
        <span className="empty__arrow">↓</span>
        <span>Real tests · real measurements</span>
        <span className="empty__arrow">↓</span>
        <span className="empty__box">Scoreboard</span>
        <span className="empty__arrow">↓</span>
        <span className="empty__win">Best fit</span>
      </div>
      <p className="empty__cta">
        Describe your requirement, pick the candidates, then start the audition.
      </p>
    </section>
  );
}

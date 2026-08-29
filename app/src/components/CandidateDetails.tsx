import type { ReactNode } from "react";
import type { CandidateResult } from "../types/audition";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="detail__row">
      <span className="detail__label">{label}</span>
      <div className="detail__value">{children}</div>
    </div>
  );
}

/**
 * Evidence-oriented: everything shown here is something that was measured,
 * including the reasons a candidate fell short.
 */
export function CandidateDetails({ result }: { result: CandidateResult }) {
  const { installation, tests, performance, dependencies, runtimeBehaviour, sourceAnalysis } =
    result;

  const nothingMeasured =
    !installation && !tests && !performance && !dependencies && !runtimeBehaviour;

  return (
    <div className="detail">
      <div className="detail__grid">
        {installation && (
          <Row label="Installation">
            {installation.passed ? (
              <span className="ok">
                ✓ Installed
                {installation.durationMs ? ` in ${(installation.durationMs / 1000).toFixed(1)}s` : ""}
              </span>
            ) : (
              <span className="bad">✗ {installation.error ?? "Installation failed"}</span>
            )}
          </Row>
        )}

        {tests && (
          <Row label="Use-case tests">
            <span className={tests.passed === tests.total ? "ok" : "warn"}>
              {tests.passed} / {tests.total} passed
            </span>
          </Row>
        )}

        {performance && (performance.executionTimeMs || performance.memoryMb) && (
          <Row label="Performance">
            {performance.executionTimeMs != null && `${performance.executionTimeMs} ms`}
            {performance.executionTimeMs != null && performance.memoryMb != null && " · "}
            {performance.memoryMb != null && `${performance.memoryMb} MB peak`}
            {performance.cpuTimeMs != null && ` · ${performance.cpuTimeMs} ms CPU`}
          </Row>
        )}

        {dependencies?.count != null && (
          <Row label="Dependencies">
            {dependencies.count} {dependencies.count === 1 ? "dependency" : "dependencies"}
            {dependencies.sizeMb != null && ` · ${dependencies.sizeMb} MB installed`}
          </Row>
        )}

        {runtimeBehaviour && (
          <Row label="Runtime behaviour">
            <ul className="checks">
              <li className={runtimeBehaviour.networkActivity ? "bad" : "ok"}>
                {runtimeBehaviour.networkActivity ? "✗" : "✓"} Network activity
                {runtimeBehaviour.networkActivity ? " observed" : ": none"}
              </li>
              <li className={runtimeBehaviour.spawnedProcesses ? "bad" : "ok"}>
                {runtimeBehaviour.spawnedProcesses ? "✗" : "✓"} Spawned processes:{" "}
                {runtimeBehaviour.spawnedProcesses ?? 0}
              </li>
              <li className={runtimeBehaviour.filesystemChanges ? "bad" : "ok"}>
                {runtimeBehaviour.filesystemChanges ? "✗" : "✓"} Filesystem changes:{" "}
                {runtimeBehaviour.filesystemChanges ?? 0}
              </li>
            </ul>
            {runtimeBehaviour.summary && (
              <p className="detail__note">{runtimeBehaviour.summary}</p>
            )}
          </Row>
        )}

        {sourceAnalysis && (
          <Row label="Source analysis">
            <span className={sourceAnalysis.status === "clean" ? "ok" : "warn"}>
              {sourceAnalysis.status === "clean" ? "✓" : "⚠"}{" "}
              {sourceAnalysis.summary ?? sourceAnalysis.status}
            </span>
            {sourceAnalysis.findings && sourceAnalysis.findings.length > 0 && (
              <ul className="findings">
                {sourceAnalysis.findings.map((finding) => (
                  <li key={finding}>{finding}</li>
                ))}
              </ul>
            )}
          </Row>
        )}

        {result.error && (
          <Row label="Error">
            <span className="bad">⚠ {result.error}</span>
          </Row>
        )}
      </div>

      {tests?.failures && tests.failures.length > 0 && (
        <div className="failures">
          <h4 className="failures__title">
            Failed tests ({tests.failures.length})
          </h4>
          {tests.failures.map((failure) => (
            <div className="failure" key={failure.name}>
              <div className="failure__name">✗ {failure.name}</div>
              <div className="failure__diff">
                <span className="failure__expected">expected {failure.expected}</span>
                <span className="failure__actual">got {failure.actual}</span>
              </div>
              {failure.explanation && (
                <p className="failure__why">{failure.explanation}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {nothingMeasured && (
        <p className="detail__note">
          No measurements are available for this candidate yet.
        </p>
      )}
    </div>
  );
}

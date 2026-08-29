import type { CandidateResult, Recommendation } from "../types/audition";

/**
 * Displays the recommendation produced by the backend/agent. The frontend
 * never decides a winner itself — it only renders the verdict and the
 * measured evidence behind it.
 */
export function RecommendationCard({
  recommendation,
  result,
}: {
  recommendation: Recommendation;
  result?: CandidateResult;
}) {
  return (
    <section className="recommendation">
      <div className="recommendation__label">Best fit</div>
      <div className="recommendation__name">{recommendation.candidate}</div>
      <div className="recommendation__score">
        {recommendation.score}
        <span className="recommendation__outof"> / 100</span>
      </div>

      <ul className="recommendation__strengths">
        {recommendation.strengths.map((strength) => (
          <li key={strength}>
            <span className="ok">✓</span> {strength}
          </li>
        ))}
        {recommendation.weaknesses?.map((weakness) => (
          <li key={weakness} className="muted">
            <span className="warn">·</span> {weakness}
          </li>
        ))}
      </ul>

      <div className="recommendation__why">
        <span className="recommendation__why-label">Why?</span>
        <p>{recommendation.explanation}</p>
      </div>

      {result?.tests && (
        <div className="recommendation__evidence">
          {result.tests.passed}/{result.tests.total} tests
          {result.performance?.executionTimeMs != null &&
            ` · ${result.performance.executionTimeMs} ms`}
          {result.performance?.memoryMb != null && ` · ${result.performance.memoryMb} MB`}
          {result.dependencies?.count != null && ` · ${result.dependencies.count} deps`}
        </div>
      )}
    </section>
  );
}

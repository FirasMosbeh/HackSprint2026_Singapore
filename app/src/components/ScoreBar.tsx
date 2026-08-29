export function ScoreBar({ score, best }: { score?: number; best?: boolean }) {
  if (typeof score !== "number") {
    return <span className="score score--none">—</span>;
  }
  const tone = score >= 85 ? "high" : score >= 70 ? "mid" : "low";
  return (
    <span className={`score score--${tone}${best ? " score--best" : ""}`}>
      <span className="score__track">
        <span className="score__fill" style={{ width: `${Math.min(score, 100)}%` }} />
      </span>
      <span className="score__value">{score}</span>
    </span>
  );
}

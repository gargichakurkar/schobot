export default function MatchScore({ score }) {
  const label = score >= 90 ? "Very High Match" : score >= 80 ? "Strong Match" : "Good Match";
  return (
    <div
      className="match-score"
      role="img"
      aria-label={`${score}% match — ${label}`}
      style={{ "--match-angle": `${score * 3.6}deg` }}
    >
      <span className="match-score-value">{score}<small>%</small></span>
      <span className="match-score-label">{label}</span>
    </div>
  );
}

import Icon from "./Icon";

export default function StatCard({ label, value, detail, icon, tone = "blue" }) {
  return (
    <article className="stat-card">
      <span className={`stat-icon stat-icon-${tone}`}><Icon name={icon} size={19} /></span>
      <div className="stat-copy">
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  );
}

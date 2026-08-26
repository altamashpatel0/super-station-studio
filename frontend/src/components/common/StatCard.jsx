import './StatCard.css';

export default function StatCard({ label, value, sub, tone = 'default' }) {
  return (
    <div className={`statcard statcard--${tone}`}>
      <span className="statcard__label">{label}</span>
      <span className="statcard__value mono">{value}</span>
      {sub && <span className="statcard__sub">{sub}</span>}
    </div>
  );
}

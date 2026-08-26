import './Switch.css';

export default function Switch({ checked, onChange, label }) {
  return (
    <button
      className={`switch${checked ? ' switch--on' : ''}`}
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
    >
      <span className="switch__thumb" />
    </button>
  );
}

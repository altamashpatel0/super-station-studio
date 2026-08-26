import './Button.css';

export default function Button({ children, variant = 'secondary', icon: Icon, onClick, ...rest }) {
  return (
    <button className={`btn btn--${variant}`} onClick={onClick} {...rest}>
      {Icon && <Icon size={14} strokeWidth={2} />}
      {children}
    </button>
  );
}

import './PageHeader.css';

export default function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="pageheader">
      <div>
        <h1 className="pageheader__title">{title}</h1>
        {subtitle && <p className="pageheader__subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="pageheader__actions">{actions}</div>}
    </div>
  );
}

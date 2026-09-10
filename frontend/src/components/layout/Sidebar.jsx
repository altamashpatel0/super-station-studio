import {
  LayoutDashboard,
  Library,
  ListMusic,
  Radio,
  Megaphone,
  BadgeInfo,
  CalendarClock,
  ScrollText,
  Settings,
} from 'lucide-react';
import './Sidebar.css';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'library', label: 'Music Library', icon: Library },
  { id: 'playlists', label: 'Playlists', icon: ListMusic },
  { id: 'jingles', label: 'Jingles', icon: Radio },
  { id: 'advertisements', label: 'Advertisements', icon: Megaphone },
  { id: 'promos', label: 'Promos', icon: BadgeInfo },
  { id: 'scheduler', label: 'Scheduler', icon: CalendarClock },
  { id: 'logs', label: 'Logs', icon: ScrollText },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export default function Sidebar({ activePage, onNavigate }) {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <div className="sidebar__brand-mark">
          <img src="/super-station-logo.png" alt="Super Station Studio" />
        </div>
        <div className="sidebar__brand-text">
          <span className="sidebar__brand-name">SUPER STATION</span>
          <span className="sidebar__brand-sub">STUDIO</span>
        </div>
      </div>

      <nav className="sidebar__nav" aria-label="Primary">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activePage === item.id;
          return (
            <button
              key={item.id}
              className={`sidebar__item${isActive ? ' sidebar__item--active' : ''}`}
              onClick={() => onNavigate(item.id)}
              aria-current={isActive ? 'page' : undefined}
            >
              <span className="sidebar__item-indicator" />
              <Icon size={17} strokeWidth={2} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar__footer">
        <span className="sidebar__version mono">V0.1.0</span>
      </div>
    </aside>
  );
}

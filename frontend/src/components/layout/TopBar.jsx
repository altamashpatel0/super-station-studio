import { useEffect, useState } from 'react';
import { Radio, Settings, ChevronDown } from 'lucide-react';
import './TopBar.css';

function useClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export default function TopBar({ onAir, onNavigate }) {
  const now = useClock();
  const time = now.toLocaleTimeString('en-US', { hour12: false });
  const date = now.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });

  return (
    <header className="topbar">
      <div className="topbar__station">
        <span className="topbar__station-name">101.3 FM — The Coastline</span>
        <span className="topbar__station-tag">Automation Console</span>
      </div>

      <div className="topbar__center">
        <button
          className={`onair${onAir ? ' onair--live' : ' onair--off'}`}
          aria-pressed={onAir}
          title="Live station state"
        >
          <span className="onair__dot" />
          {onAir ? 'ON AIR' : 'OFF AIR'}
        </button>
      </div>

      <div className="topbar__right">
        <div className="topbar__clock">
          <span className="topbar__clock-time mono">{time}</span>
          <span className="topbar__clock-date">{date}</span>
        </div>
        <div className="topbar__divider" />
        <button className="topbar__icon-btn" title="Broadcast output" >
          <Radio size={16} strokeWidth={2} />
        </button>
        <button
          className="topbar__icon-btn"
          title="Settings"
          onClick={() => onNavigate('settings')}
        >
          <Settings size={16} strokeWidth={2} />
        </button>
        <button className="topbar__user">
          <span className="topbar__user-avatar">OP</span>
          <span className="topbar__user-name">Operator</span>
          <ChevronDown size={14} strokeWidth={2} />
        </button>
      </div>
    </header>
  );
}

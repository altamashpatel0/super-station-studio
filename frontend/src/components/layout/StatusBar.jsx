import { CircleCheck, CircleX } from 'lucide-react';
import './StatusBar.css';

export default function StatusBar({ player }) {
  const connected = Boolean(player?.connected);
  const state = String(player?.station?.player_state || 'UNKNOWN').toUpperCase();
  const health = String(player?.raw?.health?.overall || 'UNKNOWN').toUpperCase();
  return (
    <footer className="statusbar">
      <div className="statusbar__group">
        <span className="statusbar__item">
          {connected ? <CircleCheck size={12} className="statusbar__icon--ok" /> : <CircleX size={12} />}
          BACKEND: <strong>{connected ? 'CONNECTED' : 'OFFLINE'}</strong>
        </span>
        <span className="statusbar__sep" />
        <span className="statusbar__item">PLAYBACK: <strong>{state}</strong></span>
        <span className="statusbar__sep" />
        <span className="statusbar__item">HEALTH: <strong>{health}</strong></span>
      </div>
      <div className="statusbar__group">
        <span className="statusbar__item mono">QUEUE {player?.queue?.length ?? 0}</span>
        <span className="statusbar__sep" />
        <span className="statusbar__item mono">VOL {Math.round(player?.volume ?? 100)}%</span>
      </div>
    </footer>
  );
}

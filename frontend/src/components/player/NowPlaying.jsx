import { Music4, Repeat } from 'lucide-react';
import { formatTime } from '../../utils/format';
import './NowPlaying.css';

export default function NowPlaying({ track, elapsed = 0, isPlaying, crossfading }) {
  const duration = Number(track?.duration ?? 0);
  const safeElapsed = Math.max(0, Number(elapsed ?? 0));
  const progressPct = duration > 0
    ? Math.min(100, Math.max(0, (safeElapsed / duration) * 100))
    : 0;
  const segments = 40;
  const litSegments = Math.round((progressPct / 100) * segments);

  if (!track) {
    return (
      <div className="nowplaying">
        <div className="nowplaying__art-wrap">
          <div className="nowplaying__art">
            <Music4 size={40} strokeWidth={1.5} />
          </div>
        </div>
        <div className="nowplaying__meta">
          <span className="nowplaying__eyebrow">NO TRACK</span>
          <h1 className="nowplaying__title">Nothing playing</h1>
          <span className="nowplaying__artist">Select a track to start playback</span>
        </div>
        <div className="nowplaying__progress-block">
          <div className="nowplaying__segments" role="progressbar" aria-valuenow={0} aria-valuemin={0} aria-valuemax={100}>
            {Array.from({ length: segments }).map((_, i) => (
              <span key={i} className="nowplaying__segment" />
            ))}
          </div>
          <div className="nowplaying__time-row">
            <span className="mono">0:00</span>
            <div className="nowplaying__crossfade">
              <Repeat size={11} strokeWidth={2.25} />
              <span>CROSSFADE</span>
            </div>
            <span className="mono">0:00</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="nowplaying">
      <div className="nowplaying__art-wrap">
        <div className={`nowplaying__art${isPlaying ? ' nowplaying__art--spinning' : ''}`}>
          <Music4 size={40} strokeWidth={1.5} />
        </div>
        {isPlaying && <div className="nowplaying__art-ring" />}
      </div>

      <div className="nowplaying__meta">
        <div className="nowplaying__eyebrow-row">
          <span className="nowplaying__eyebrow">{isPlaying ? 'NOW PLAYING' : 'PAUSED'}</span>
          {track.type && track.type !== 'SONG' && <span className="nowplaying__type">{track.type}</span>}
        </div>
        <h1 className="nowplaying__title">{track.title || 'Unknown track'}</h1>
        <span className="nowplaying__artist">{track.artist || (track.type !== 'SONG' ? `Asset #${track.id}` : 'Unknown artist')}</span>
      </div>

      <div className="nowplaying__progress-block">
        <div className="nowplaying__segments" role="progressbar" aria-valuenow={Math.round(progressPct)} aria-valuemin={0} aria-valuemax={100}>
          {Array.from({ length: segments }).map((_, i) => (
            <span key={i} className={`nowplaying__segment${i < litSegments ? ' nowplaying__segment--lit' : ''}`} />
          ))}
        </div>
        <div className="nowplaying__time-row">
          <span className="mono">{formatTime(safeElapsed)}</span>
          <div className={`nowplaying__crossfade${crossfading ? ' nowplaying__crossfade--active' : ''}`}>
            <Repeat size={11} strokeWidth={2.25} />
            <span>CROSSFADE</span>
          </div>
          <span className="mono">{formatTime(duration)}</span>
        </div>
      </div>
    </div>
  );
}

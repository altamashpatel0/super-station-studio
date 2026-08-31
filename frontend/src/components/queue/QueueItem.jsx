import { Music2, Radio, Megaphone, Signal } from 'lucide-react';
import { api } from '../../api';
import './QueueItem.css';

const TYPE_CONFIG = {
  song: { label: 'SONG', icon: Music2, className: 'song' },
  jingle: { label: 'JINGLE', icon: Radio, className: 'jingle' },
  ad: { label: 'AD', icon: Megaphone, className: 'ad' },
  'station-id': { label: 'STATION ID', icon: Signal, className: 'stationid' },
};

export default function QueueItem({ item, position, isImmediate, onClick }) {
  const normalizedType = String(item?.type ?? item?.kind ?? item?.content_type ?? "SONG").toLowerCase();
  const config = TYPE_CONFIG[normalizedType] ?? TYPE_CONFIG.song;
  const Icon = config.icon;
  const songId = item?.song_id ?? (item?.type === 'song' ? item?.id : null);
  const artwork = item?.artwork || item?.artwork_url || item?.cover_url || (songId != null ? api.getSongArtworkUrl(songId) : null);

  return (
    <button type="button" className={`queueitem${isImmediate ? ' queueitem--next' : ''}`} onClick={onClick}>
      <span className="queueitem__position mono">{String(position).padStart(2, '0')}</span>
      <span className={`queueitem__type-icon queueitem__type-icon--${config.className}${artwork && config.className === 'song' ? ' queueitem__type-icon--artwork' : ''}`}>
        {artwork && config.className === 'song' ? (
          <img
            className="queueitem__artwork"
            src={artwork}
            alt=""
            loading="lazy"
            onError={(event) => { event.currentTarget.style.display = 'none'; }}
          />
        ) : (
          <Icon size={14} strokeWidth={2} />
        )}
      </span>
      <span className="queueitem__meta">
        <span className="queueitem__title">{item.title ?? item.name ?? item.song_title ?? "Unknown track"}</span>
        <span className="queueitem__sub">{item.artist ?? item.artist_name ?? ""}</span>
      </span>
      <span className="queueitem__right">
        <span className={`queueitem__badge queueitem__badge--${config.className}`}>{config.label}</span>
        <span className="queueitem__duration mono">{item.duration ?? item.duration_seconds ?? ""}</span>
      </span>
    </button>
  );
}

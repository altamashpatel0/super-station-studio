import { Music2, Radio, Megaphone, Signal, Megaphone as PromoIcon } from 'lucide-react';
import { api } from '../../api';
import './QueueItem.css';

const TYPE_CONFIG = {
  song: { label: 'SONG', icon: Music2, className: 'song' },
  jingle: { label: 'JINGLE', icon: Radio, className: 'jingle' },
  ad: { label: 'AD', icon: Megaphone, className: 'ad' },
  advertisement: { label: 'AD', icon: Megaphone, className: 'ad' },
  promo: { label: 'PROMO', icon: PromoIcon, className: 'promo' },
  stationid: { label: 'STATION ID', icon: Signal, className: 'stationid' },
};

export default function QueueItem({ item, position, isImmediate, onClick }) {
  const rawType = String(item?.type || item?.item_type || item?.kind || item?.content_type || item?.asset_type || (item?.asset_id != null ? 'PROMO' : 'SONG')).toLowerCase();
  const normalizedType = rawType === 'advertisement' ? 'ad' : rawType === 'station_id' ? 'stationid' : rawType;
  const config = TYPE_CONFIG[normalizedType] ?? TYPE_CONFIG.song;
  const Icon = config.icon;
  const isPromo = config.className === 'promo';
  const songId = item?.song_id ?? (normalizedType === 'song' ? item?.id : null);
  const artwork = item?.artwork || item?.artwork_url || item?.cover_url || (songId != null ? api.getSongArtworkUrl(songId) : null);
  const title = item?.title || item?.name || (isPromo ? `Promo #${item?.asset_id ?? item?.id ?? '?'}` : 'Unknown track');
  const sub = item?.artist || item?.artist_name || item?.asset?.category || (isPromo ? 'Promo' : '');

  return (
    <button type="button" className={`queueitem${isImmediate ? ' queueitem--next' : ''}${isPromo ? ' queueitem--promo' : ''}`} onClick={onClick}>
      <span className="queueitem__position mono">{String(position).padStart(2, '0')}</span>
      <span className={`queueitem__type-icon queueitem__type-icon--${config.className}${artwork && config.className === 'song' ? ' queueitem__type-icon--artwork' : ''}`}>
        {artwork && config.className === 'song' ? (
          <img className="queueitem__artwork" src={artwork} alt="" loading="lazy" onError={(event) => { event.currentTarget.style.display = 'none'; }} />
        ) : (
          <Icon size={14} strokeWidth={2} />
        )}
      </span>
      <span className="queueitem__meta">
        <span className="queueitem__title">{title}</span>
        <span className="queueitem__sub">{sub}</span>
      </span>
      <span className="queueitem__right">
        <span className={`queueitem__badge queueitem__badge--${config.className}`}>{config.label}</span>
        <span className="queueitem__duration mono">{item.duration}</span>
      </span>
    </button>
  );
}

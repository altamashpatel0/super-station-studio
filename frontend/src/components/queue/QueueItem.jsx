import { Music2, Radio, Megaphone, Signal } from 'lucide-react';
import './QueueItem.css';

const TYPE_CONFIG = {
  song: { label: 'SONG', icon: Music2, className: 'song' },
  jingle: { label: 'JINGLE', icon: Radio, className: 'jingle' },
  ad: { label: 'AD', icon: Megaphone, className: 'ad' },
  'station-id': { label: 'STATION ID', icon: Signal, className: 'stationid' },
};

export default function QueueItem({ item, position, isImmediate, onClick }) {
  const config = TYPE_CONFIG[item.type] ?? TYPE_CONFIG.song;
  const Icon = config.icon;

  return (
    <button className={`queueitem${isImmediate ? ' queueitem--next' : ''}`} onClick={onClick}>
      <span className="queueitem__position mono">{String(position).padStart(2, '0')}</span>
      <span className={`queueitem__type-icon queueitem__type-icon--${config.className}`}>
        <Icon size={14} strokeWidth={2} />
      </span>
      <span className="queueitem__meta">
        <span className="queueitem__title">{item.title}</span>
        <span className="queueitem__sub">{item.artist}</span>
      </span>
      <span className="queueitem__right">
        <span className={`queueitem__badge queueitem__badge--${config.className}`}>{config.label}</span>
        <span className="queueitem__duration mono">{item.duration}</span>
      </span>
    </button>
  );
}

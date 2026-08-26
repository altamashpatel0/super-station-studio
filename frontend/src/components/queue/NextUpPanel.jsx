import QueueItem from './QueueItem';
import './NextUpPanel.css';

export default function NextUpPanel({ queue = [], onSelect }) {
  return (
    <div className="nextup">
      <div className="nextup__header">
        <h2 className="nextup__title">NEXT UP</h2>
        <span className="nextup__count mono">{queue.length} ITEMS</span>
      </div>
      <div className="nextup__list scrollable">
        {queue.map((item, idx) => (
          <QueueItem
            key={item.id ?? item.queue_item_id ?? idx}
            item={item}
            position={idx + 1}
            isImmediate={idx === 0}
            onClick={() => onSelect(item)}
          />
        ))}
        {!queue.length && (
          <div style={{ padding: 20, color: 'var(--text-tertiary)', fontSize: 12 }}>
            Queue is empty.
          </div>
        )}
      </div>
    </div>
  );
}

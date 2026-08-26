import { Volume, Volume1, Volume2, VolumeX } from 'lucide-react';
import './VolumeControl.css';

function VolumeIcon({ volume }) {
  const props = { size: 16, strokeWidth: 2 };
  if (volume === 0) return <VolumeX {...props} />;
  if (volume < 34) return <Volume {...props} />;
  if (volume < 67) return <Volume1 {...props} />;
  return <Volume2 {...props} />;
}

export default function VolumeControl({ volume, onChange }) {
  return (
    <div className="volume">
      <button
        className="volume__icon-btn"
        onClick={() => onChange(volume === 0 ? 78 : 0)}
        title={volume === 0 ? 'Unmute' : 'Mute'}
      >
        <VolumeIcon volume={volume} />
      </button>
      <div className="volume__slider-wrap">
        <div className="volume__track">
          <div className="volume__fill" style={{ width: `${volume}%` }} />
        </div>
        <input
          className="volume__input"
          type="range"
          min={0}
          max={100}
          value={volume}
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label="Volume"
        />
      </div>
      <span className="volume__value mono">{volume}</span>
    </div>
  );
}

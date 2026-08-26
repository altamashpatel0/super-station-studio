import { Play, Pause, Square, SkipBack, SkipForward } from 'lucide-react';
import VolumeControl from './VolumeControl';
import './PlayerControls.css';

export default function PlayerControls({
  isPlaying,
  onPlay,
  onPause,
  onStop,
  onNext,
  onPrevious,
  volume,
  onVolumeChange,
}) {
  return (
    <div className="controls">
      <div className="controls__transport">
        <button className="controls__btn controls__btn--secondary" onClick={onPrevious} title="Previous">
          <SkipBack size={17} strokeWidth={2} fill="currentColor" />
        </button>

        <button className="controls__btn controls__btn--secondary" onClick={onStop} title="Stop">
          <Square size={15} strokeWidth={2} fill="currentColor" />
        </button>

        {isPlaying ? (
          <button className="controls__btn controls__btn--primary" onClick={onPause} title="Pause">
            <Pause size={22} strokeWidth={2} fill="currentColor" />
          </button>
        ) : (
          <button className="controls__btn controls__btn--primary" onClick={onPlay} title="Play">
            <Play size={22} strokeWidth={2} fill="currentColor" style={{ marginLeft: 2 }} />
          </button>
        )}

        <button className="controls__btn controls__btn--secondary" onClick={onNext} title="Next">
          <SkipForward size={17} strokeWidth={2} fill="currentColor" />
        </button>
      </div>

      <VolumeControl volume={volume} onChange={onVolumeChange} />
    </div>
  );
}

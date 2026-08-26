import NowPlaying from '../components/player/NowPlaying';
import PlayerControls from '../components/player/PlayerControls';
import NextUpPanel from '../components/queue/NextUpPanel';
import './Dashboard.css';

export default function Dashboard({ player }) {
  const {
    track,
    queue,
    isPlaying,
    elapsed,
    volume,
    crossfading,
    setVolume,
    play,
    pause,
    stop,
    next,
    previous,
    playFromQueue,
  } = player;

  return (
    <div className="dashboard">
      <div className="dashboard__main">
        <NowPlaying track={track} elapsed={elapsed} isPlaying={isPlaying} crossfading={crossfading} />
        <PlayerControls
          isPlaying={isPlaying}
          onPlay={play}
          onPause={pause}
          onStop={stop}
          onNext={next}
          onPrevious={previous}
          volume={volume}
          onVolumeChange={setVolume}
        />
      </div>
      <NextUpPanel queue={queue} onSelect={playFromQueue} />
    </div>
  );
}

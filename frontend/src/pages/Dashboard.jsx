import { useEffect, useMemo, useState } from "react";
import {
  Activity, CalendarClock, Database, Headphones, ListMusic,
  RadioTower, Server, Trash2, Clock3,
} from "lucide-react";
import NowPlaying from "../components/player/NowPlaying";
import PlayerControls from "../components/player/PlayerControls";
import NextUpPanel from "../components/queue/NextUpPanel";
import { api } from "../api";
import "./Dashboard.css";

function numberOf(...values) {
  for (const value of values) {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return 0;
}

function artworkFor(item) {
  const id = item?.song_id ?? item?.id;
  return id == null ? null : api.getSongArtworkUrl(id);
}

export default function Dashboard({ player }) {
  const {
    track, queue, isPlaying, elapsed, volume, crossfading,
    crossfadeProgress, activeDeck, crossfadeSourceDeck, crossfadeTargetDeck,
    setVolume, play, pause, stop, next, previous, playFromQueue,
    clearQueue,
  } = player;

  const [stats, setStats] = useState(null);
  const [schedules, setSchedules] = useState([]);
  const [recentlyPlayed, setRecentlyPlayed] = useState([]);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const [statsResult, schedulesResult, historyResult] = await Promise.all([
        api.getStats().catch(() => null),
        api.listSchedules().catch(() => []),
        api.getRecentlyPlayed(8).catch(() => []),
      ]);
      if (!alive) return;
      setStats(statsResult);
      setSchedules(Array.isArray(schedulesResult) ? schedulesResult : []);
      const history = Array.isArray(historyResult)
        ? historyResult
        : Array.isArray(historyResult?.items) ? historyResult.items : [];
      setRecentlyPlayed(history);
    };
    load();
    const timer = window.setInterval(load, 4000);
    return () => { alive = false; window.clearInterval(timer); };
  }, []);

  const enabledSchedules = useMemo(
    () => schedules.filter((schedule) => schedule.enabled),
    [schedules]
  );

  const listeners = numberOf(
    player.raw?.listeners,
    player.raw?.listener_count,
    player.raw?.station?.listeners
  );
  const songCount = numberOf(stats?.total_songs, stats?.song_count, stats?.songs_count);
  const health = String(player.raw?.health?.overall || "HEALTHY").toUpperCase();

  const handleClearQueue = async () => {
    if (!queue.length || clearing) return;
    if (!window.confirm(`Clear all ${queue.length} queued items?`)) return;
    setClearing(true);
    try {
      await clearQueue();
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="dashboard">
      <section className="dashboard__stats">
        <div className="stat">
          <span className="stat__icon stat__icon--red"><RadioTower size={17} /></span>
          <div><small>STATION</small><strong>{player.station?.name || "Super Station Studio"}</strong><em className={isPlaying ? "live" : ""}>{isPlaying ? "PLAYING" : "STANDBY"}</em></div>
        </div>
        <div className="stat">
          <span className="stat__icon stat__icon--green"><Headphones size={17} /></span>
          <div><small>LISTENERS</small><strong>{listeners.toLocaleString()}</strong><em>LIVE</em></div>
        </div>
        <div className="stat">
          <span className="stat__icon stat__icon--blue"><Database size={17} /></span>
          <div><small>LIBRARY</small><strong>{songCount.toLocaleString()}</strong><em>TRACKS</em></div>
        </div>
        <div className="stat">
          <span className="stat__icon stat__icon--amber"><CalendarClock size={17} /></span>
          <div><small>SCHEDULE</small><strong>{enabledSchedules.length}</strong><em>ENABLED</em></div>
        </div>
        <div className="stat">
          <span className="stat__icon"><Server size={17} /></span>
          <div><small>ENGINE</small><strong>{player.connected ? "READY" : "OFFLINE"}</strong><em>{health}</em></div>
        </div>
      </section>

      <section className="dashboard__workspace">
        <div className="dashboard__left">
          <section className="panel panel--now">
            <header className="panel__header">
              <div><span className="panel__eyebrow">ON AIR</span><h2>Now Playing</h2></div>
              <span className={`status-pill ${isPlaying ? "status-pill--live" : ""}`}>{isPlaying ? "LIVE" : "PAUSED"}</span>
            </header>
            <NowPlaying
              track={track}
              elapsed={elapsed}
              isPlaying={isPlaying}
              crossfading={crossfading}
              crossfadeProgress={crossfadeProgress}
              activeDeck={activeDeck}
              crossfadeSourceDeck={crossfadeSourceDeck}
              crossfadeTargetDeck={crossfadeTargetDeck}
            />
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
          </section>

          <div className="dashboard__bottom">
            <section className="panel compact-panel">
              <header className="panel__header">
                <div><span className="panel__eyebrow">LIVE HISTORY</span><h2>Recently Played</h2></div>
                <Clock3 size={17} />
              </header>
              <div className="history-list">
                {recentlyPlayed.slice(0, 5).map((item, index) => (
                  <div className="history-row" key={item.id ?? `${item.song_id}-${index}`}>
                    <span className="mono">{String(index + 1).padStart(2, "0")}</span>
                    <img src={artworkFor(item)} alt="" onError={(event) => { event.currentTarget.style.visibility = "hidden"; }} />
                    <div><b title={item.title}>{item.title || item.name || "Unknown track"}</b><small>{item.artist || item.artist_name || "Unknown artist"}</small></div>
                    <span className="history-status">{item.status === "SKIPPED" ? "SKIP" : "PLAYED"}</span>
                  </div>
                ))}
                {!recentlyPlayed.length && <div className="empty-small">No recent playback history.</div>}
              </div>
            </section>

            <section className="panel compact-panel">
              <header className="panel__header">
                <div><span className="panel__eyebrow">AUTOMATION</span><h2>Scheduler</h2></div>
                <span className="panel__counter">{enabledSchedules.length} ENABLED</span>
              </header>
              <div className="schedule-list">
                {enabledSchedules.slice(0, 5).map((schedule) => (
                  <div className="schedule-row" key={schedule.id}>
                    <span className="mono">{schedule.start_time}</span>
                    <div><b>{schedule.name}</b><small>{schedule.target_type} · {schedule.target_id ?? "—"}</small></div>
                    <span className="schedule-dot" />
                  </div>
                ))}
                {!enabledSchedules.length && <div className="empty-small">No enabled schedules.</div>}
              </div>
            </section>
          </div>
        </div>

        <aside className="panel panel--queue">
          <header className="panel__header">
            <div><span className="panel__eyebrow">PLAYBACK ORDER</span><h2>Up Next</h2></div>
            <div className="queue-actions">
              <span className="panel__counter"><ListMusic size={14} />{queue.length}</span>
              <button className="clear-btn" onClick={handleClearQueue} disabled={!queue.length || clearing}>
                <Trash2 size={14} />{clearing ? "Clearing" : "Clear"}
              </button>
            </div>
          </header>
          <NextUpPanel queue={queue} onSelect={playFromQueue} onClear={handleClearQueue} clearing={clearing} />
        </aside>
      </section>

      <section className="dashboard__footer-cards">
        <div className="mini-card"><Activity size={16} /><span>Crossfade</span><b>{crossfading ? `${Math.round(crossfadeProgress * 100)}%` : `Deck ${activeDeck || "A"} ready`}</b></div>
        <div className="mini-card"><Database size={16} /><span>Storage</span><b>{stats?.storage ?? "—"}</b></div>
        <div className="mini-card"><RadioTower size={16} /><span>Volume</span><b>{Math.round(volume ?? 100)}%</b></div>
      </section>
    </div>
  );
}

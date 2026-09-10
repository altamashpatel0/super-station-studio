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


function parseClock(value) {
  if (!value) return null;
  const match = String(value).trim().match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?$/i);
  if (!match) return null;

  let hour = Number(match[1]);
  const minute = Number(match[2]);
  const second = Number(match[3] || 0);
  const meridiem = match[4]?.toUpperCase();

  if (meridiem) {
    if (hour === 12) hour = 0;
    if (meridiem === "PM") hour += 12;
  }
  if (hour > 23 || minute > 59 || second > 59) return null;
  return { hour, minute, second };
}

function dateOnly(value) {
  if (!value) return null;
  const text = String(value).slice(0, 10);
  const parts = text.split("-").map(Number);
  if (parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) return null;
  return new Date(parts[0], parts[1] - 1, parts[2]);
}

function nextScheduleEvent(scheduleList, now = new Date()) {
  let best = null;

  for (const schedule of scheduleList) {
    const clock = parseClock(schedule?.start_time);
    if (!schedule?.enabled || !clock) continue;

    const startDate = dateOnly(schedule.start_date);
    const endDate = dateOnly(schedule.end_date);
    const days = Array.isArray(schedule.days_of_week) ? schedule.days_of_week.map(Number) : [];

    // Check the next 8 days. This handles recurring schedules correctly,
    // including schedules whose time has already passed today.
    for (let offset = 0; offset <= 7; offset += 1) {
      const candidate = new Date(now);
      candidate.setHours(0, 0, 0, 0);
      candidate.setDate(candidate.getDate() + offset);

      if (startDate && candidate < startDate) continue;
      if (endDate && candidate > endDate) continue;

      // JavaScript: Sunday=0; scheduler stores Monday=0 ... Sunday=6.
      const schedulerDay = (candidate.getDay() + 6) % 7;
      if (days.length && !days.includes(schedulerDay)) continue;

      candidate.setHours(clock.hour, clock.minute, clock.second, 0);
      if (candidate <= now) continue;

      if (!best || candidate < best.start) {
        best = { schedule, start: candidate };
      }
    }
  }

  return best;
}

function formatEventTime(date) {
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatCountdown(milliseconds) {
  const totalSeconds = Math.max(0, Math.ceil(milliseconds / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function scheduleOccurrence(schedule, now = new Date()) {
  if (!schedule?.enabled) return null;
  const startClock = parseClock(schedule.start_time);
  const endClock = parseClock(schedule.end_time);
  if (!startClock || !endClock) return null;
  const startDate = dateOnly(schedule.start_date);
  const endDate = dateOnly(schedule.end_date);
  const days = Array.isArray(schedule.days_of_week) ? schedule.days_of_week.map(Number) : [];
  for (let offset = 0; offset <= 7; offset += 1) {
    const day = new Date(now); day.setHours(0,0,0,0); day.setDate(day.getDate()+offset);
    if (startDate && day < startDate) continue;
    if (endDate && day > endDate) continue;
    const schedulerDay = (day.getDay()+6)%7;
    if (days.length && !days.includes(schedulerDay)) continue;
    const start = new Date(day); start.setHours(startClock.hour,startClock.minute,startClock.second,0);
    const end = new Date(day); end.setHours(endClock.hour,endClock.minute,endClock.second,0);
    if (end <= start) continue;
    if (now >= start && now < end) return {phase:'LIVE',start,end};
    if (start > now) return {phase:'UPCOMING',start,end};
  }
  return {phase:'ENDED',start:null,end:null};
}

function formatScheduleDateTime(date) {
  if (!date) return '—';
  return date.toLocaleString([], {weekday:'short',day:'2-digit',month:'short',year:'numeric',hour:'numeric',minute:'2-digit'});
}

export default function Dashboard({ player, stationName, onNavigate }) {
  const {
    track, queue, isPlaying, elapsed, volume, crossfading,
    crossfadeProgress, activeDeck, crossfadeSourceDeck, crossfadeTargetDeck,
    setVolume, play, pause, stop, next, previous, playFromQueue,
    clearQueue,
  } = player;

  const [stats, setStats] = useState(null);
  const [schedules, setSchedules] = useState([]);
  const [recentlyPlayed, setRecentlyPlayed] = useState([]);
  const [clockNow, setClockNow] = useState(() => new Date());
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

  useEffect(() => {
    const timer = window.setInterval(() => setClockNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const enabledSchedules = useMemo(
    () => schedules.filter((schedule) => schedule.enabled),
    [schedules]
  );

  const nextEvent = useMemo(
    () => nextScheduleEvent(enabledSchedules, clockNow),
    [enabledSchedules, clockNow]
  );

  const nextEventCountdown = nextEvent
    ? formatCountdown(nextEvent.start.getTime() - clockNow.getTime())
    : null;

  const scheduleCards = useMemo(() => enabledSchedules
    .map((schedule) => ({ schedule, timing: scheduleOccurrence(schedule, clockNow) }))
    .filter((entry) => entry.timing && entry.timing.phase !== 'ENDED')
    .sort((a,b) => {
      const rank={LIVE:0,UPCOMING:1};
      const p=rank[a.timing.phase]-rank[b.timing.phase];
      if(p) return p;
      return (a.timing.start?.getTime()||0)-(b.timing.start?.getTime()||0);
    }), [enabledSchedules, clockNow]);

  const openSchedulerWindow = () => {
    if (typeof onNavigate === "function") {
      onNavigate("scheduleCenter");
      return;
    }
    window.location.hash = "#schedule-center";
  };

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
          <div><small>STATION</small><strong>{stationName || player.station?.name || "Super Station Studio"}</strong><em className={isPlaying ? "live" : ""}>{isPlaying ? "PLAYING" : "STANDBY"}</em></div>
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
                <div className="panel__header-action"><Clock3 size={16} /><button type="button" onClick={openSchedulerWindow}>View all</button></div>
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
                <div className="panel__header-action"><span className="panel__counter">{enabledSchedules.length} ENABLED</span><button type="button" onClick={openSchedulerWindow}>Open</button></div>
              </header>
              <div className="schedule-list dashboard-schedule-list">
                {scheduleCards.length ? scheduleCards.slice(0,4).map(({schedule,timing}) => {
                  const live=timing.phase==='LIVE';
                  const remaining=live ? timing.end.getTime()-clockNow.getTime() : timing.start.getTime()-clockNow.getTime();
                  return <button type="button" key={schedule.id} className={`dashboard-schedule-card dashboard-schedule-card--${timing.phase.toLowerCase()}`} onClick={() => { sessionStorage.setItem("sss-open-schedule-id", String(schedule.id)); openSchedulerWindow(); }}>
                    <span className="dashboard-schedule-card__time"><b>{schedule.start_time}</b><small>→ {schedule.end_time}</small></span>
                    <span className="dashboard-schedule-card__main"><strong>{schedule.name}</strong><small>{schedule.target_type} · {live ? 'RUNNING NOW' : formatScheduleDateTime(timing.start)}</small></span>
                    <span className="dashboard-schedule-card__timer"><small>{live ? 'ENDS IN' : 'STARTS IN'}</small><b>{formatCountdown(remaining)}</b></span>
                  </button>;
                }) : <div className="empty-small">No upcoming schedules.</div>}
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

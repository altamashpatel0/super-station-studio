import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import "./LiveMonitor.css";

function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "--:--";
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function progressPercent(position, duration) {
  if (!Number.isFinite(duration) || duration <= 0) return 0;
  return Math.min(100, Math.max(0, (position / duration) * 100));
}

function statusLabel(value) {
  return String(value || "UNKNOWN").replaceAll("_", " ");
}

function HealthPill({ label, value, tone }) {
  return (
    <div className={`live-health-pill live-health-pill--${tone}`}>
      <span className="live-health-pill__dot" />
      <span className="live-health-pill__label">{label}</span>
      <strong>{statusLabel(value)}</strong>
    </div>
  );
}

export default function LiveMonitor() {
  const [snapshot, setSnapshot] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const loadStatus = useCallback(async (signal) => {
    try {
      const result = await api.getLiveStatus({ signal });
      setSnapshot(result);
      setErrorMessage(null);
      setLastUpdated(new Date());
    } catch (error) {
      if (error?.name === "AbortError") return;
      setErrorMessage(error?.message || "Live monitor is unavailable.");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    loadStatus(controller.signal);
    const timer = window.setInterval(() => {
      loadStatus(controller.signal);
    }, 1000);

    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [loadStatus]);

  const current = snapshot?.now_playing ?? null;
  const station = snapshot?.station;
  const health = snapshot?.health;
  const nextUp = snapshot?.next_up ?? [];

  const progress = useMemo(
    () =>
      current
        ? progressPercent(current.position_seconds, current.duration_seconds)
        : 0,
    [current]
  );

  if (errorMessage && !snapshot) {
    return (
      <section className="live-monitor">
        <div className="live-monitor__offline">
          <div className="live-monitor__offline-icon">!</div>
          <h2>Live Monitor unavailable</h2>
          <p>{errorMessage}</p>
          <button type="button" onClick={() => loadStatus()}>
            Retry
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="live-monitor">
      <div className="live-monitor__hero">
        <div>
          <span className="live-monitor__eyebrow">LIVE STATION MONITOR</span>
          <h2>Broadcast Control</h2>
          <p className="live-monitor__subtitle">
            Real playback, scheduler and station-runtime state.
          </p>
        </div>

        <div
          className={`live-monitor__air-badge ${
            station?.mode === "ON_AIR"
              ? "live-monitor__air-badge--on"
              : "live-monitor__air-badge--off"
          }`}
        >
          <span />
          {station?.mode === "ON_AIR" ? "ON AIR" : statusLabel(station?.mode)}
        </div>
      </div>

      {errorMessage && (
        <div className="live-monitor__warning">
          Live refresh temporarily unavailable. Showing the last successful snapshot.
        </div>
      )}

      <div className="live-monitor__grid">
        <article className="live-card live-card--now">
          <div className="live-card__heading">
            <div>
              <span className="live-card__eyebrow">NOW PLAYING</span>
              <h3>
                {current?.title || "Nothing is playing"}
              </h3>
            </div>
            {current && (
              <span className="live-card__type">{statusLabel(current.kind)}</span>
            )}
          </div>

          <div className="live-now-playing">
            <div className="live-now-playing__art">
              <span>{current ? "♪" : "—"}</span>
            </div>

            <div className="live-now-playing__details">
              <strong>{current?.title || "No active track"}</strong>
              <span>{current?.artist || "Waiting for live content"}</span>
              {current?.album && <small>{current.album}</small>}

              <div className="live-progress">
                <div
                  className="live-progress__bar"
                  style={{ width: `${progress}%` }}
                />
              </div>

              <div className="live-progress__times">
                <span>{formatTime(current?.position_seconds)}</span>
                <span>{formatTime(current?.duration_seconds)}</span>
              </div>
            </div>
          </div>
        </article>

        <article className="live-card live-card--health">
          <div className="live-card__heading">
            <div>
              <span className="live-card__eyebrow">SYSTEM HEALTH</span>
              <h3>{statusLabel(health?.overall || "UNKNOWN")}</h3>
            </div>
            <span className="live-health-summary">
              {health?.watchdog_recoveries ?? 0} recoveries
            </span>
          </div>

          <div className="live-health-list">
            <HealthPill
              label="Station"
              value={health?.station_runtime}
              tone={health?.station_runtime === "RUNNING" ? "ok" : "bad"}
            />
            <HealthPill
              label="Automation"
              value={health?.automation_worker}
              tone={health?.automation_worker === "RUNNING" ? "ok" : "bad"}
            />
            <HealthPill
              label="Continuation"
              value={health?.playback_continuation}
              tone={health?.playback_continuation === "ATTACHED" ? "ok" : "bad"}
            />
            <HealthPill
              label="Watchdog"
              value={health?.watchdog}
              tone={
                health?.watchdog === "HEALTHY" || health?.watchdog === "IDLE"
                  ? "ok"
                  : "warn"
              }
            />
          </div>
        </article>
      </div>

      <article className="live-card live-card--next">
        <div className="live-card__heading">
          <div>
            <span className="live-card__eyebrow">NEXT UP</span>
            <h3>Real queue preview</h3>
          </div>
          <span className="live-next-count">
            {snapshot?.queue?.queued_count ?? 0} shown
          </span>
        </div>

        {nextUp.length > 0 ? (
          <div className="live-next-list">
            {nextUp.map((item) => (
              <div className="live-next-row" key={item.queue_item_id}>
                <span className="live-next-row__number">
                  {String(item.position + 1).padStart(2, "0")}
                </span>
                <div className="live-next-row__main">
                  <strong>{item.title}</strong>
                  <span>{item.artist || "Unknown artist"}</span>
                </div>
                <span className="live-next-row__duration">
                  {formatTime(item.duration_seconds)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="live-empty">
            The real playback queue is currently empty.
          </div>
        )}
      </article>

      <div className="live-monitor__footer">
        <span>
          Player: <strong>{statusLabel(station?.player_state)}</strong>
        </span>
        <span>
          Last update:{" "}
          <strong>
            {lastUpdated ? lastUpdated.toLocaleTimeString() : "—"}
          </strong>
        </span>
      </div>
    </section>
  );
}

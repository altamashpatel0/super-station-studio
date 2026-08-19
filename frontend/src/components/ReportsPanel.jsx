import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import "./ReportsPanel.css";

function formatDuration(seconds) {
  const value = Number(seconds || 0);
  if (!Number.isFinite(value) || value <= 0) return "00:00";
  const total = Math.round(value);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function typeLabel(type) {
  return {
    SONG: "Song",
    JINGLE: "Jingle",
    ADVERTISEMENT: "Advertisement",
    AUDIO: "Audio",
  }[type] || type;
}

export default function ReportsPanel() {
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = date ? { date } : {};
      const [summaryResult, historyResult] = await Promise.all([
        api.getReportSummary(params),
        api.getPlaybackReport({ ...params, ...(type ? { content_type: type } : {}), ...(status ? { status } : {}) }),
      ]);
      setSummary(summaryResult);
      setItems(historyResult.items || []);
      setError(null);
    } catch (err) {
      setError(err?.message || "Could not load reports.");
    } finally {
      setLoading(false);
    }
  }, [date, type, status]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="reports">
      <div className="reports__hero">
        <div>
          <span className="reports__eyebrow">REPORTS & HISTORY</span>
          <h2>Station Playback Report</h2>
          <p>Every row below is generated from real AudioEngine playback events.</p>
        </div>
        <div className="reports__filters">
          <label>
            <span>Date</span>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label>
            <span>Type</span>
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">All</option>
              <option value="SONG">Songs</option>
              <option value="JINGLE">Jingles</option>
              <option value="ADVERTISEMENT">Advertisements</option>
            </select>
          </label>
          <label>
            <span>Status</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              <option value="COMPLETED">Completed</option>
              <option value="SKIPPED">Skipped</option>
              <option value="FAILED">Failed</option>
              <option value="PLAYING">Playing</option>
            </select>
          </label>
        </div>
      </div>

      {error && <div className="reports__error">{error}</div>}

      <div className="reports__cards">
        <div className="report-card report-card--purple"><span>Songs Played</span><strong>{summary?.songs_played ?? 0}</strong></div>
        <div className="report-card report-card--orange"><span>Jingles Played</span><strong>{summary?.jingles_played ?? 0}</strong></div>
        <div className="report-card report-card--blue"><span>Ads Played</span><strong>{summary?.advertisements_played ?? 0}</strong></div>
        <div className="report-card report-card--red"><span>Failures</span><strong>{summary?.failures ?? 0}</strong></div>
      </div>

      <div className="reports__stats">
        <div><span>Completed</span><strong>{summary?.completed ?? 0}</strong></div>
        <div><span>Skipped</span><strong>{summary?.skipped ?? 0}</strong></div>
        <div><span>Total Events</span><strong>{summary?.total ?? 0}</strong></div>
        <div><span>Played Time</span><strong>{formatDuration(summary?.total_duration_seconds)}</strong></div>
      </div>

      <article className="reports__table-card">
        <div className="reports__table-heading">
          <div>
            <span className="reports__eyebrow">PLAYBACK HISTORY</span>
            <h3>Real station events</h3>
          </div>
          <button type="button" onClick={load} disabled={loading}>{loading ? "Refreshing…" : "↻ Refresh"}</button>
        </div>

        {loading ? (
          <div className="reports__empty">Loading playback history…</div>
        ) : items.length === 0 ? (
          <div className="reports__empty">No playback events recorded for this date.</div>
        ) : (
          <div className="reports__table-wrap">
            <table className="reports__table">
              <thead>
                <tr>
                  <th>Time</th><th>Type</th><th>Content</th><th>Duration</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{formatTime(item.started_at)}</td>
                    <td><span className={`report-type report-type--${item.content_type.toLowerCase()}`}>{typeLabel(item.content_type)}</span></td>
                    <td>
                      <strong>{item.content_name}</strong>
                      {item.error_message && <small>{item.error_message}</small>}
                    </td>
                    <td>{formatDuration(item.duration_seconds)}</td>
                    <td><span className={`report-status report-status--${item.status.toLowerCase()}`}>{item.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </section>
  );
}

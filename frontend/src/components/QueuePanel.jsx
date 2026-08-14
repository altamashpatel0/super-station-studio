import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import "./QueuePanel.css";

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return "--:--";
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

export default function QueuePanel({
  nowPlaying,
  setNowPlaying,
  playSongNow,
  queueVersion,
  bumpQueueVersion,
}) {
  const [queueItems, setQueueItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  const loadQueue = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const items = await api.getQueue();
      setQueueItems(items);
    } catch (err) {
      setErrorMessage(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadQueue();
  }, [loadQueue, queueVersion]);

  const handleRemove = async (item) => {
    setErrorMessage(null);
    try {
      await api.removeQueueItem(item.id);
      await loadQueue();
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const handleMoveUp = async (item) => {
    setErrorMessage(null);
    try {
      await api.moveQueueItemUp(item.id);
      await loadQueue();
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const handleMoveDown = async (item) => {
    setErrorMessage(null);
    try {
      await api.moveQueueItemDown(item.id);
      await loadQueue();
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const handleClearQueue = async () => {
    if (queueItems.length === 0) return;
    if (!window.confirm("Clear the entire queue?")) return;
    setErrorMessage(null);
    try {
      await api.clearQueue();
      await loadQueue();
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  // Advances playback: pulls the front item off the queue and starts
  // playing it via the V0.1 AudioEngine.
  const handlePlayNext = async () => {
    if (queueItems.length === 0) return;
    const front = queueItems[0];
    setErrorMessage(null);
    try {
      if (front.song) {
        await playSongNow(front.song);
      }
      await api.removeQueueItem(front.id);
      await loadQueue();
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const handleTransport = async (action) => {
    setErrorMessage(null);
    try {
      const status = await action();
      setNowPlaying((prev) => ({ ...prev, state: status.state.toLowerCase() }));
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const nowPlayingSong = nowPlaying?.song ?? null;

  return (
    <section className="queue">
      {errorMessage && <div className="banner banner--error">{errorMessage}</div>}

      <div className="queue__now-playing">
        <div className="queue__now-playing-label">Currently Playing</div>
        <div className="queue__now-playing-body">
          {nowPlayingSong ? (
            <div className="queue__now-playing-track">
              <strong>{nowPlayingSong.title}</strong> — {nowPlayingSong.artist}
            </div>
          ) : (
            <div className="queue__now-playing-track queue__now-playing-track--empty">
              Nothing playing
            </div>
          )}
          <div className="queue__now-playing-actions">
            <button onClick={handlePlayNext} disabled={queueItems.length === 0}>
              ⏭ Play Next
            </button>
            <button onClick={() => handleTransport(api.pause)} disabled={!nowPlayingSong}>
              ⏸ Pause
            </button>
            <button onClick={() => handleTransport(api.resume)} disabled={!nowPlayingSong}>
              ⏵ Resume
            </button>
            <button onClick={() => handleTransport(api.stop)} disabled={!nowPlayingSong}>
              ⏹ Stop
            </button>
            <span className="queue__player-state">{nowPlaying?.state ?? "stopped"}</span>
          </div>
        </div>
      </div>

      <div className="queue__list-header">
        <h2>Up Next ({queueItems.length})</h2>
        <button onClick={handleClearQueue} disabled={queueItems.length === 0} className="queue__danger">
          Clear Queue
        </button>
      </div>

      <div className="queue__table-wrap">
        <table className="queue__table">
          <thead>
            <tr>
              <th>#</th>
              <th>Title</th>
              <th>Artist</th>
              <th>Duration</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {queueItems.map((item, index) => (
              <tr key={item.id}>
                <td className="queue__mono">{index + 1}</td>
                <td>{item.song?.title ?? `Song #${item.song_id}`}</td>
                <td>{item.song?.artist ?? "—"}</td>
                <td className="queue__mono">{formatDuration(item.song?.duration)}</td>
                <td className="queue__row-actions">
                  <button onClick={() => handleMoveUp(item)} disabled={index === 0} title="Move up">
                    ↑
                  </button>
                  <button
                    onClick={() => handleMoveDown(item)}
                    disabled={index === queueItems.length - 1}
                    title="Move down"
                  >
                    ↓
                  </button>
                  <button onClick={() => handleRemove(item)} title="Remove">
                    ✕
                  </button>
                </td>
              </tr>
            ))}
            {!loading && queueItems.length === 0 && (
              <tr>
                <td colSpan={5} className="queue__empty">
                  Queue is empty. Add songs from a playlist, or queue one from the Music Library.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

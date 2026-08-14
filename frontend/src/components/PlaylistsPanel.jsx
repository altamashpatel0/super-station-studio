import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import "./PlaylistsPanel.css";

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return "--:--";
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

export default function PlaylistsPanel({
  selectedLibrarySong,
  playSongNow,
  bumpQueueVersion,
  onWentToQueue,
}) {
  const [playlists, setPlaylists] = useState([]);
  const [selectedPlaylistId, setSelectedPlaylistId] = useState(null);
  const [playlistDetail, setPlaylistDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [infoMessage, setInfoMessage] = useState(null);

  const loadPlaylists = useCallback(async () => {
    setErrorMessage(null);
    try {
      const results = await api.listPlaylists();
      setPlaylists(results);
      return results;
    } catch (err) {
      setErrorMessage(err.message);
      return [];
    }
  }, []);

  const loadPlaylistDetail = useCallback(async (id) => {
    if (id == null) {
      setPlaylistDetail(null);
      return;
    }
    setLoading(true);
    setErrorMessage(null);
    try {
      const detail = await api.getPlaylist(id);
      setPlaylistDetail(detail);
    } catch (err) {
      setErrorMessage(err.message);
      setPlaylistDetail(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPlaylists();
  }, [loadPlaylists]);

  useEffect(() => {
    loadPlaylistDetail(selectedPlaylistId);
  }, [selectedPlaylistId, loadPlaylistDetail]);

  const flash = (message) => {
    setInfoMessage(message);
    setTimeout(() => setInfoMessage((cur) => (cur === message ? null : cur)), 3000);
  };

  const handleCreate = async () => {
    const name = window.prompt("Playlist name:");
    if (!name || !name.trim()) return;
    setErrorMessage(null);
    try {
      const playlist = await api.createPlaylist(name.trim());
      await loadPlaylists();
      setSelectedPlaylistId(playlist.id);
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const handleRename = async () => {
    if (!playlistDetail) return;
    const name = window.prompt("New playlist name:", playlistDetail.name);
    if (!name || !name.trim() || name.trim() === playlistDetail.name) return;
    setErrorMessage(null);
    try {
      await api.updatePlaylist(playlistDetail.id, { name: name.trim() });
      await loadPlaylists();
      await loadPlaylistDetail(playlistDetail.id);
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const handleDelete = async () => {
    if (!playlistDetail) return;
    if (!window.confirm(`Delete playlist "${playlistDetail.name}"? This can't be undone.`)) return;
    setErrorMessage(null);
    try {
      await api.deletePlaylist(playlistDetail.id);
      setSelectedPlaylistId(null);
      setPlaylistDetail(null);
      await loadPlaylists();
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const handleAddSelectedSong = async () => {
    if (!playlistDetail || !selectedLibrarySong) return;
    setErrorMessage(null);
    try {
      await api.addTrackToPlaylist(playlistDetail.id, selectedLibrarySong.id);
      await loadPlaylistDetail(playlistDetail.id);
      await loadPlaylists();
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const handleRemoveTrack = async (track) => {
    if (!playlistDetail) return;
    setErrorMessage(null);
    try {
      await api.removeTrackFromPlaylist(playlistDetail.id, track.id);
      await loadPlaylistDetail(playlistDetail.id);
      await loadPlaylists();
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const swapAndReorder = async (index, direction) => {
    if (!playlistDetail) return;
    const tracks = playlistDetail.tracks;
    const otherIndex = index + direction;
    if (otherIndex < 0 || otherIndex >= tracks.length) return;
    const ids = tracks.map((t) => t.id);
    [ids[index], ids[otherIndex]] = [ids[otherIndex], ids[index]];
    setErrorMessage(null);
    try {
      await api.reorderPlaylistTracks(playlistDetail.id, ids);
      await loadPlaylistDetail(playlistDetail.id);
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const handlePlayPlaylist = async () => {
    if (!playlistDetail) return;
    setErrorMessage(null);
    try {
      const items = await api.addPlaylistToQueue(playlistDetail.id);
      bumpQueueVersion();
      if (items.length === 0) {
        flash("Playlist is empty — nothing to play.");
        return;
      }
      const [first, ...rest] = items;
      if (first.song) {
        await playSongNow(first.song);
      }
      await api.removeQueueItem(first.id);
      bumpQueueVersion();
      flash(`Playing "${playlistDetail.name}" — ${rest.length} more queued.`);
      onWentToQueue?.();
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const handleAddToQueue = async () => {
    if (!playlistDetail) return;
    setErrorMessage(null);
    try {
      const items = await api.addPlaylistToQueue(playlistDetail.id);
      bumpQueueVersion();
      flash(`Added ${items.length} track${items.length === 1 ? "" : "s"} to the queue.`);
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  return (
    <section className="playlists">
      {errorMessage && <div className="banner banner--error">{errorMessage}</div>}
      {infoMessage && <div className="banner banner--success">{infoMessage}</div>}

      <div className="playlists__layout">
        <div className="playlists__list-col">
          <div className="playlists__list-header">
            <h2>Playlists</h2>
            <button onClick={handleCreate}>+ New</button>
          </div>
          <ul className="playlists__list">
            {playlists.map((p) => (
              <li
                key={p.id}
                className={p.id === selectedPlaylistId ? "is-selected" : ""}
                onClick={() => setSelectedPlaylistId(p.id)}
              >
                <span className="playlists__list-name">{p.name}</span>
                <span className="playlists__list-count">{p.track_count}</span>
              </li>
            ))}
            {playlists.length === 0 && (
              <li className="playlists__list-empty">No playlists yet.</li>
            )}
          </ul>
        </div>

        <div className="playlists__detail-col">
          {!playlistDetail && (
            <div className="playlists__empty-state">
              Select a playlist on the left, or create a new one.
            </div>
          )}

          {playlistDetail && (
            <>
              <div className="playlists__detail-header">
                <div>
                  <h2>{playlistDetail.name}</h2>
                  {playlistDetail.description && (
                    <p className="playlists__description">{playlistDetail.description}</p>
                  )}
                </div>
                <div className="playlists__detail-actions">
                  <button onClick={handlePlayPlaylist} disabled={loading}>
                    ▶ Play Playlist
                  </button>
                  <button onClick={handleAddToQueue} disabled={loading}>
                    + Add to Queue
                  </button>
                  <button onClick={handleRename}>Rename</button>
                  <button onClick={handleDelete} className="playlists__danger">
                    Delete
                  </button>
                </div>
              </div>

              <div className="playlists__add-row">
                <span>
                  {selectedLibrarySong
                    ? (
                      <>
                        Selected in Library: <strong>{selectedLibrarySong.title}</strong> — {selectedLibrarySong.artist}
                      </>
                    )
                    : "Select a song in the Music Library to add it here."}
                </span>
                <button onClick={handleAddSelectedSong} disabled={!selectedLibrarySong}>
                  Add Selected Song
                </button>
              </div>

              <div className="playlists__table-wrap">
                <table className="playlists__table">
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
                    {playlistDetail.tracks.map((track, index) => (
                      <tr key={track.id}>
                        <td className="playlists__mono">{index + 1}</td>
                        <td>{track.song?.title ?? `Song #${track.song_id}`}</td>
                        <td>{track.song?.artist ?? "—"}</td>
                        <td className="playlists__mono">{formatDuration(track.song?.duration)}</td>
                        <td className="playlists__row-actions">
                          <button
                            onClick={() => swapAndReorder(index, -1)}
                            disabled={index === 0}
                            title="Move up"
                          >
                            ↑
                          </button>
                          <button
                            onClick={() => swapAndReorder(index, 1)}
                            disabled={index === playlistDetail.tracks.length - 1}
                            title="Move down"
                          >
                            ↓
                          </button>
                          <button onClick={() => handleRemoveTrack(track)} title="Remove">
                            ✕
                          </button>
                        </td>
                      </tr>
                    ))}
                    {playlistDetail.tracks.length === 0 && (
                      <tr>
                        <td colSpan={5} className="playlists__empty">
                          No tracks yet. Select a song in the Music Library and click "Add Selected Song".
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

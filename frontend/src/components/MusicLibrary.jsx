import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api, pollScanJob } from "../api.js";
import "./MusicLibrary.css";

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return "--:--";
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

const SORT_COLUMNS = [
  { key: "title", label: "Title" },
  { key: "artist", label: "Artist" },
  { key: "album", label: "Album" },
  { key: "duration", label: "Duration" },
];

export default function MusicLibrary() {
  const [songs, setSongs] = useState([]);
  const [stats, setStats] = useState(null);
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState("title");
  const [sortDir, setSortDir] = useState("asc");
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [scanProgress, setScanProgress] = useState(null); // {processed, added, ...} while scanning
  const [playerState, setPlayerState] = useState("stopped");
  const [errorMessage, setErrorMessage] = useState(null);

  const loadSongs = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const results = query.trim()
        ? await api.searchSongs(query.trim())
        : await api.listSongs({ sort_by: sortBy, sort_dir: sortDir });
      setSongs(results);
      setStats(await api.getStats());
    } catch (err) {
      setErrorMessage(err.message);
    } finally {
      setLoading(false);
    }
  }, [query, sortBy, sortDir]);

  useEffect(() => {
    loadSongs();
  }, [loadSongs]);

  const handleSort = (columnKey) => {
    if (sortBy === columnKey) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(columnKey);
      setSortDir("asc");
    }
  };

  const handleImportFolder = async () => {
    const folderPath = window.prompt("Folder to scan for music (e.g. D:\\Music):");
    if (!folderPath) return;
    setErrorMessage(null);
    setScanProgress({ status: "starting", processed: 0, added: 0, updated: 0, errors: 0 });
    try {
      const job = await api.startScan(folderPath);
      const finished = await pollScanJob(job.job_id, { onProgress: setScanProgress });
      setScanProgress(finished);
      await loadSongs();
    } catch (err) {
      setErrorMessage(err.message);
      setScanProgress(null);
    }
  };

  const handleRefresh = async () => {
    setErrorMessage(null);
    setLoading(true);
    try {
      await api.refreshLibrary();
      await loadSongs();
    } catch (err) {
      setErrorMessage(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handlePlaySelected = async () => {
    if (selectedId == null) return;
    setErrorMessage(null);
    try {
      const status = await api.playSong(selectedId);
      setPlayerState(status.state.toLowerCase());
      await loadSongs(); // refresh play_count / last_played for the played track
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const handleTransport = async (action) => {
    try {
      const status = await action();
      setPlayerState(status.state.toLowerCase());
    } catch (err) {
      setErrorMessage(err.message);
    }
  };

  const selectedSong = useMemo(
    () => songs.find((s) => s.id === selectedId) ?? null,
    [songs, selectedId]
  );

  return (
    <section className="library">
      <div className="library__toolbar">
        <input
          className="library__search"
          type="search"
          placeholder="Search songs, artists, albums..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button onClick={handleImportFolder} disabled={scanProgress && scanProgress.status !== "completed" && scanProgress.status !== "failed"}>
          Import Folder
        </button>
        <button onClick={handleRefresh} disabled={loading}>
          Refresh
        </button>
      </div>

      {scanProgress && scanProgress.status !== "completed" && scanProgress.status !== "failed" && (
        <div className="library__banner library__banner--info">
          Scanning… {scanProgress.processed ?? 0} files processed
          {" · "}
          {scanProgress.added ?? 0} added, {scanProgress.updated ?? 0} updated
          {scanProgress.errors ? `, ${scanProgress.errors} errors` : ""}
        </div>
      )}
      {scanProgress && scanProgress.status === "completed" && (
        <div className="library__banner library__banner--success">
          Scan complete — {scanProgress.added} added, {scanProgress.updated} updated
          {scanProgress.errors ? `, ${scanProgress.errors} skipped with errors` : ""}.
        </div>
      )}
      {errorMessage && <div className="library__banner library__banner--error">{errorMessage}</div>}

      {stats && (
        <div className="library__stats">
          <span>{stats.total_songs} songs</span>
          <span>{stats.artists} artists</span>
          <span>{stats.albums} albums</span>
          <span>{stats.genres} genres</span>
          <span>{formatDuration(stats.total_duration_seconds)} total</span>
          {stats.unavailable > 0 && (
            <span className="library__stats-warning">{stats.unavailable} unavailable</span>
          )}
        </div>
      )}

      <div className="library__table-wrap">
        <table className="library__table">
          <thead>
            <tr>
              {SORT_COLUMNS.map((col) => (
                <th key={col.key} onClick={() => handleSort(col.key)}>
                  {col.label}
                  {sortBy === col.key ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
              <th>Available</th>
            </tr>
          </thead>
          <tbody>
            {songs.map((song) => (
              <tr
                key={song.id}
                className={song.id === selectedId ? "is-selected" : ""}
                onClick={() => setSelectedId(song.id)}
                onDoubleClick={() => {
                  setSelectedId(song.id);
                  handlePlaySelected();
                }}
              >
                <td>{song.title}</td>
                <td>{song.artist}</td>
                <td>{song.album || "—"}</td>
                <td className="library__mono">{formatDuration(song.duration)}</td>
                <td>
                  <span className={`dot ${song.enabled ? "dot--ok" : "dot--missing"}`} />
                  {song.enabled ? "Available" : "Missing"}
                </td>
              </tr>
            ))}
            {!loading && songs.length === 0 && (
              <tr>
                <td colSpan={5} className="library__empty">
                  No songs yet. Click "Import Folder" to scan a music folder.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="library__transport">
        <div className="library__now-selected">
          {selectedSong ? (
            <>
              <strong>{selectedSong.title}</strong> — {selectedSong.artist}
            </>
          ) : (
            "No track selected"
          )}
        </div>
        <div className="library__transport-buttons">
          <button onClick={handlePlaySelected} disabled={!selectedSong}>
            ▶ Play
          </button>
          <button onClick={() => handleTransport(api.pause)}>⏸ Pause</button>
          <button onClick={() => handleTransport(api.resume)}>⏵ Resume</button>
          <button onClick={() => handleTransport(api.stop)}>⏹ Stop</button>
          <span className="library__player-state">{playerState}</span>
        </div>
      </div>
    </section>
  );
}

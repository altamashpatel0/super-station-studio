import { useEffect, useMemo, useRef, useState } from "react";
import { Search, FolderOpen, RefreshCw, Trash2, Play, LayoutGrid, List, Music2 } from "lucide-react";
import PageHeader from "../components/common/PageHeader";
import Button from "../components/common/Button";
import { api } from "../api";
import usePlayerState from "../hooks/usePlayerState";
import "./MusicLibrary.css";

const artworkCache = new Map();

function getArtworkEndpoint(songId) {
  return `/api/library/songs/${songId}/artwork`;
}

async function findExternalArtwork(song) {
  const key = `${song.artist || ""}|${song.title || song.file_name || ""}`.trim();
  if (!key) return null;
  if (artworkCache.has(key)) return artworkCache.get(key);

  try {
    const term = encodeURIComponent(`${song.artist || ""} ${song.title || song.file_name || ""}`.trim());
    const response = await fetch(`https://itunes.apple.com/search?term=${term}&entity=song&limit=1`);
    if (!response.ok) return null;
    const data = await response.json();
    const url = data?.results?.[0]?.artworkUrl100?.replace("100x100", "600x600") || null;
    artworkCache.set(key, url);
    return url;
  } catch {
    return null;
  }
}

function Artwork({ song, className = "" }) {
  const [src, setSrc] = useState(getArtworkEndpoint(song.id));
  const [failed, setFailed] = useState(false);

  const handleError = async () => {
    if (failed) return;
    setFailed(true);
    const external = await findExternalArtwork(song);
    if (external) {
      setSrc(external);
      setFailed(false);
    }
  };

  return (
    <div className={`music-art ${className}`}>
      {!failed ? (
        <img src={src} alt="" loading="lazy" onError={handleError} />
      ) : (
        <div className="music-art__fallback">
          <Music2 size={34} strokeWidth={1.5} />
        </div>
      )}
    </div>
  );
}

function formatDuration(value) {
  const seconds = Number(value || 0);
  if (!Number.isFinite(seconds) || seconds <= 0) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${mins}:${secs}`;
}

export default function MusicLibrary() {
  const inputRef = useRef(null);
  const player = usePlayerState({ intervalMs: 2000 });
  const [songs, setSongs] = useState([]);
  const [stats, setStats] = useState(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [importProgress, setImportProgress] = useState(null);
  const [error, setError] = useState("");
  const [view, setView] = useState("grid");

  const load = async () => {
    try {
      setError("");
      const [list, stat] = await Promise.all([
        api.listSongs({ limit: 500 }),
        api.getStats(),
      ]);
      setSongs(Array.isArray(list) ? list : list?.items || []);
      setStats(stat || {});
    } catch (e) {
      setError(e.message || "Unable to load music library.");
    }
  };

  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return songs;
    return songs.filter((s) =>
      `${s.title || ""} ${s.artist || ""} ${s.album || ""} ${s.genre || ""}`
        .toLowerCase().includes(q)
    );
  }, [songs, query]);

  const importFolder = async (event) => {
    const files = Array.from(event.target.files || []).filter((file) =>
      /\.(mp3|wav)$/i.test(file.name)
    );
    event.target.value = "";

    if (!files.length) {
      setError("No MP3/WAV files were found in the selected folder.");
      return;
    }

    const currentCount = songs.length;
    const remainingSlots = Math.max(0, 500 - currentCount);

    if (remainingSlots <= 0) {
      setError("Music Library limit reached: maximum 500 songs.");
      return;
    }

    const filesToImport = files.slice(0, remainingSlots);
    const skippedForLimit = files.length - filesToImport.length;

    setBusy(true);
    setError("");
    setMessage("");
    setImportProgress({
      total: filesToImport.length,
      completed: 0,
      imported: 0,
      failed: 0,
      remaining: filesToImport.length,
      currentName: filesToImport[0]?.name || "",
    });

    let imported = 0;
    let failed = 0;

    try {
      // Sequential upload gives a truthful per-song progress indicator and
      // avoids creating multiple simultaneous library/database writers.
      for (let index = 0; index < filesToImport.length; index += 1) {
        const file = filesToImport[index];

        setImportProgress((prev) => ({
          ...prev,
          currentName: file.name,
          remaining: filesToImport.length - index,
        }));

        try {
          await api.importMusicFiles([file]);
          imported += 1;
        } catch (e) {
          failed += 1;
          setError(`${file.name}: ${e.message || "Import failed."}`);
        }

        const completed = index + 1;
        setImportProgress((prev) => ({
          ...prev,
          completed,
          imported,
          failed,
          remaining: filesToImport.length - completed,
          currentName: completed < filesToImport.length
            ? filesToImport[completed].name
            : file.name,
        }));
      }

      await load();

      const limitNote = skippedForLimit
        ? ` · ${skippedForLimit} skipped (500-song limit)`
        : "";
      setMessage(
        `${imported} song${imported === 1 ? "" : "s"} imported` +
        `${failed ? ` · ${failed} failed` : ""}${limitNote}.`
      );
    } catch (e) {
      setError(e.message || "Music import failed.");
      setMessage("");
    } finally {
      setImportProgress((prev) => prev ? ({
        ...prev,
        completed: prev.total,
        imported,
        failed,
        remaining: 0,
      }) : null);
      setBusy(false);

      window.setTimeout(() => {
        setImportProgress(null);
      }, 1200);
    }
  };

  const removeSelected = async () => {
    if (!selected.size || busy) return;

    const count = selected.size;
    const confirmed = window.confirm(
      `Delete ${count} selected track${count === 1 ? "" : "s"} from the library and permanently delete the audio file${count === 1 ? "" : "s"} from disk?\n\nThis cannot be undone.`
    );
    if (!confirmed) return;

    try {
      setBusy(true);
      setError("");
      setMessage(`Deleting ${count} track${count === 1 ? "" : "s"} and audio file${count === 1 ? "" : "s"}...`);

      for (const id of selected) {
        await api.deleteSong(id, { deleteFile: true });
      }

      setSelected(new Set());
      await load();
      setMessage(`Deleted ${count} track${count === 1 ? "" : "s"} and removed the audio file${count === 1 ? "" : "s"} from disk.`);
    } catch (e) {
      setError(e.message || "Unable to delete selected tracks.");
      setMessage("");
      await load();
    } finally {
      setBusy(false);
    }
  };

  const removeAll = async () => {
    if (!songs.length || busy) return;

    const count = songs.length;
    const confirmed = window.confirm(
      `Delete all ${count} tracks from the library and permanently delete their audio files from disk?\n\nThis cannot be undone.`
    );
    if (!confirmed) return;

    try {
      setBusy(true);
      setError("");
      setMessage(`Deleting ${count} tracks and audio files...`);

      for (const song of songs) {
        await api.deleteSong(song.id, { deleteFile: true });
      }

      setSelected(new Set());
      await load();
      setMessage(`Deleted all ${count} tracks and removed their audio files from disk.`);
    } catch (e) {
      setError(e.message || "Unable to delete all tracks.");
      setMessage("");
      await load();
    } finally {
      setBusy(false);
    }
  };

  const toggleSelected = (id) => {
    setSelected((old) => {
      const next = new Set(old);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === filtered.length) setSelected(new Set());
    else setSelected(new Set(filtered.map((s) => s.id)));
  };

  return (
    <div className="pageshell music-library-page">
      <PageHeader
        title="Music Library"
        subtitle={`${songs.length} tracks in station catalog`}
        actions={
          <>
            <input
              ref={inputRef}
              type="file"
              accept=".mp3,.wav,audio/mpeg,audio/wav"
              multiple
              webkitdirectory=""
              directory=""
              style={{ display: "none" }}
              onChange={importFolder}
            />
            <Button variant="primary" icon={FolderOpen} onClick={() => inputRef.current?.click()} disabled={busy}>
              {busy ? "Importing..." : "Import Folder"}
            </Button>
            <Button icon={RefreshCw} onClick={load} disabled={busy}>Refresh</Button>
            <Button icon={Trash2} onClick={removeSelected} disabled={!selected.size || busy}>
              Remove Selected ({selected.size})
            </Button>
            <Button icon={Trash2} onClick={removeAll} disabled={!songs.length || busy}>Remove All</Button>
          </>
        }
      />

      <div className="pageshell__body music-library-body">
        <div className="library-toolbar">
          <div className="library-search">
            <Search size={16} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search title, artist, album or genre..." />
          </div>
          <div className="library-view-toggle" aria-label="Library view">
            <button className={view === "grid" ? "is-active" : ""} onClick={() => setView("grid")} title="Post view"><LayoutGrid size={16} /></button>
            <button className={view === "table" ? "is-active" : ""} onClick={() => setView("table")} title="Table view"><List size={16} /></button>
          </div>
        </div>

        {importProgress && (
          <div className="library-import-progress" role="status" aria-live="polite">
            <div className="library-import-progress__top">
              <div>
                <span className="library-import-progress__eyebrow">IMPORTING MUSIC</span>
                <strong>
                  {importProgress.completed} of {importProgress.total} songs processed
                </strong>
              </div>
              <strong className="library-import-progress__percent">
                {Math.round((importProgress.completed / Math.max(1, importProgress.total)) * 100)}%
              </strong>
            </div>

            <div className="library-import-progress__track">
              <div
                className="library-import-progress__fill"
                style={{
                  width: `${Math.min(100, Math.round((importProgress.completed / Math.max(1, importProgress.total)) * 100))}%`,
                }}
              />
            </div>

            <div className="library-import-progress__meta">
              <span>
                {importProgress.remaining > 0
                  ? `${importProgress.remaining} song${importProgress.remaining === 1 ? "" : "s"} remaining`
                  : "Import complete"}
              </span>
              <span>
                {importProgress.imported} imported
                {importProgress.failed ? ` · ${importProgress.failed} failed` : ""}
              </span>
            </div>

            {importProgress.remaining > 0 && (
              <div className="library-import-progress__current" title={importProgress.currentName}>
                <span>Processing</span>
                <strong>{importProgress.currentName}</strong>
              </div>
            )}
          </div>
        )}

        {message && <div className="badge badge--info library-message">{message}</div>}
        {error && <div className="badge badge--error library-message">{error}</div>}

        <div className="library-stats">
          <strong>{stats?.total_songs ?? songs.length} songs</strong>
          <span>{stats?.artists ?? "—"} artists</span>
          <span>{stats?.albums ?? "—"} albums</span>
          <span>{stats?.genres ?? "—"} genres</span>
        </div>

        {view === "grid" ? (
          <div className="music-post-grid">
            {filtered.map((song) => (
              <article className={`music-post ${selected.has(song.id) ? "is-selected" : ""}`} key={song.id}>
                <div className="music-post__media">
                  <Artwork song={song} />
                  <div className="music-post__overlay">
                    <button className="music-post__play" title={`Play ${song.title || song.file_name}`} onClick={() => player.playSong(song.id)}>
                      <Play size={19} fill="currentColor" />
                    </button>
                  </div>
                  <label className="music-post__check">
                    <input type="checkbox" checked={selected.has(song.id)} onChange={() => toggleSelected(song.id)} />
                  </label>
                  <span className="music-post__format">{song.format || "SONG"}</span>
                </div>
                <div className="music-post__body">
                  <div className="music-post__title" title={song.title || song.file_name}>{song.title || song.file_name}</div>
                  <div className="music-post__artist" title={song.artist}>{song.artist || "Unknown Artist"}</div>
                  <div className="music-post__meta">
                    <span>{song.album || "Single"}</span>
                    <span>{formatDuration(song.duration)}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <table className="datatable">
            <thead>
              <tr>
                <th><input type="checkbox" checked={filtered.length > 0 && selected.size === filtered.length} onChange={toggleAll} /></th>
                <th>Play</th><th>Title</th><th>Artist</th><th>Album</th><th>Duration</th><th>Available</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((song) => (
                <tr key={song.id}>
                  <td><input type="checkbox" checked={selected.has(song.id)} onChange={() => toggleSelected(song.id)} /></td>
                  <td><button title={`Play ${song.title}`} onClick={() => player.playSong(song.id)}><Play size={13} fill="currentColor" /></button></td>
                  <td className="strong">{song.title || song.file_name}</td>
                  <td>{song.artist || ""}</td><td>{song.album || ""}</td>
                  <td className="mono">{formatDuration(song.duration)}</td>
                  <td>{song.enabled === false ? "Disabled" : "Ready"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {!filtered.length && (
          <div className="library-empty">
            <Music2 size={30} />
            <strong>{query ? `No tracks match "${query}".` : "No songs in the library."}</strong>
            {!query && <span>Click Import Folder to add MP3/WAV files.</span>}
          </div>
        )}
      </div>
    </div>
  );
}

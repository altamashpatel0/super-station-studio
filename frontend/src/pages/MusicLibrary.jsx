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
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length) return;
    try {
      setBusy(true);
      setError("");
      setMessage(`Importing ${files.length} audio file(s)...`);
      await api.importMusicFiles(files);
      await load();
      setMessage(`Imported ${files.length} file(s).`);
    } catch (e) {
      setError(e.message || "Music import failed.");
      setMessage("");
    } finally {
      setBusy(false);
    }
  };

  const removeSelected = async () => {
    if (!selected.size) return;
    try {
      setBusy(true);
      for (const id of selected) await api.deleteSong(id);
      setSelected(new Set());
      await load();
    } catch (e) {
      setError(e.message || "Unable to remove selected tracks.");
    } finally {
      setBusy(false);
    }
  };

  const removeAll = async () => {
    if (!songs.length) return;
    if (!window.confirm(`Remove all ${songs.length} tracks from the library?`)) return;
    try {
      setBusy(true);
      for (const song of songs) await api.deleteSong(song.id);
      setSelected(new Set());
      await load();
    } catch (e) {
      setError(e.message || "Unable to remove all tracks.");
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

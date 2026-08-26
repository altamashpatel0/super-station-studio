import { useEffect, useMemo, useRef, useState } from "react";
import { Search, FolderOpen, RefreshCw, Trash2, Play } from "lucide-react";
import PageHeader from "../components/common/PageHeader";
import Button from "../components/common/Button";
import { api } from "../api";
import usePlayerState from "../hooks/usePlayerState";

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

  const toggleAll = () => {
    if (selected.size === filtered.length) setSelected(new Set());
    else setSelected(new Set(filtered.map((s) => s.id)));
  };

  return (
    <div className="pageshell">
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
            <Button icon={Trash2} onClick={removeAll} disabled={!songs.length || busy}>
              Remove All
            </Button>
          </>
        }
      />

      <div className="pageshell__body">
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 18 }}>
          <Search size={15} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search title, artist, album or genre..."
            style={{ flex: 1, padding: "10px 12px" }}
          />
        </div>

        {message && <div className="badge badge--info" style={{ marginBottom: 12 }}>{message}</div>}
        {error && <div className="badge badge--error" style={{ marginBottom: 12 }}>{error}</div>}

        <div style={{ display: "flex", gap: 24, marginBottom: 16 }}>
          <strong>{stats?.total_songs ?? songs.length} songs</strong>
          <span>{stats?.artists ?? "—"} artists</span>
          <span>{stats?.albums ?? "—"} albums</span>
          <span>{stats?.genres ?? "—"} genres</span>
        </div>

        <table className="datatable">
          <thead>
            <tr>
              <th><input type="checkbox" checked={filtered.length > 0 && selected.size === filtered.length} onChange={toggleAll} /></th>
              <th>Play</th>
              <th>Title</th>
              <th>Artist</th>
              <th>Album</th>
              <th>Duration</th>
              <th>Available</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((song) => (
              <tr key={song.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.has(song.id)}
                    onChange={() => setSelected((old) => {
                      const next = new Set(old);
                      next.has(song.id) ? next.delete(song.id) : next.add(song.id);
                      return next;
                    })}
                  />
                </td>
                <td>
                  <button title={`Play ${song.title}`} onClick={() => player.playSong(song.id)}>
                    <Play size={13} fill="currentColor" />
                  </button>
                </td>
                <td className="strong">{song.title || song.name}</td>
                <td>{song.artist || ""}</td>
                <td>{song.album || ""}</td>
                <td className="mono">{song.duration ?? song.duration_seconds ?? 0}</td>
                <td>{song.enabled === false ? "Disabled" : "Ready"}</td>
              </tr>
            ))}
            {!filtered.length && (
              <tr><td colSpan={7} style={{ textAlign: "center", padding: 32 }}>
                {query ? `No tracks match "${query}".` : "No songs in the library. Click Import Folder to add MP3/WAV files."}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

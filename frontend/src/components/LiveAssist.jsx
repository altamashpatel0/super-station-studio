import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import "./LiveAssist.css";

function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "--:--";
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function label(value) {
  return String(value || "UNKNOWN").replaceAll("_", " ");
}

function stateTone(state) {
  if (state === "PLAYING") return "ok";
  if (state === "PAUSED") return "warn";
  return "neutral";
}

export default function LiveAssist() {
  const [status, setStatus] = useState(null);
  const [songs, setSongs] = useState([]);
  const [assets, setAssets] = useState([]);
  const [selectedSongId, setSelectedSongId] = useState("");
  const [volume, setVolume] = useState(1);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importForm, setImportForm] = useState({
    name: "",
    asset_type: "JINGLE",
    category: "",
    description: "",
    priority: 0,
    cooldown_seconds: 0,
  });
  const fileInputRef = useRef(null);

  const refreshStatus = useCallback(async (signal) => {
    try {
      const result = await api.getLiveAssistStatus({ signal });
      setStatus(result);
      if (typeof result.volume === "number") setVolume(result.volume);
      setError(null);
    } catch (err) {
      if (err?.name !== "AbortError") {
        setError(err?.message || "Live Assist unavailable.");
      }
    }
  }, []);

  const loadChoices = useCallback(async () => {
    try {
      const [songResult, assetResult] = await Promise.all([
        api.listSongs({ limit: 50, enabled_only: true }),
        api.listAssets({ enabled_only: true }),
      ]);
      setSongs(Array.isArray(songResult) ? songResult : songResult.items || []);
      setAssets(Array.isArray(assetResult) ? assetResult : []);
    } catch (err) {
      setError(err?.message || "Could not load Live Assist choices.");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    refreshStatus(controller.signal);
    loadChoices();

    const timer = window.setInterval(() => {
      refreshStatus(controller.signal);
    }, 1000);

    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [loadChoices, refreshStatus]);

  const runTransport = async (name, action) => {
    setBusy(name);
    setError(null);
    try {
      const result = await action();
      setStatus(result);
      if (typeof result.volume === "number") setVolume(result.volume);
    } catch (err) {
      setError(err?.message || `${name} failed.`);
    } finally {
      setBusy(null);
    }
  };

  const playSelectedSong = async () => {
    if (!selectedSongId) return;
    setBusy("song");
    setError(null);
    try {
      const result = await api.playSong(Number(selectedSongId));
      setStatus(result);
    } catch (err) {
      setError(err?.message || "Song playback failed.");
    } finally {
      setBusy(null);
    }
  };

  const openImport = () => {
    setImportFile(null);
    setImportForm({ name: "", asset_type: "JINGLE", category: "", description: "", priority: 0, cooldown_seconds: 0 });
    setShowImport(true);
  };

  const handleImportFile = (event) => {
    const file = event.target.files?.[0] ?? null;
    setImportFile(file);
    if (file) {
      const filename = file.name.replace(/\.[^.]+$/, "");
      setImportForm((current) => ({ ...current, name: current.name || filename }));
    }
  };

  const importAsset = async () => {
    if (!importFile) {
      setError("Choose an audio file first.");
      return;
    }
    if (!importForm.name.trim()) {
      setError("Asset name is required.");
      return;
    }

    setBusy("import-asset");
    setError(null);
    try {
      await api.uploadAsset(importFile, {
        name: importForm.name.trim(),
        asset_type: importForm.asset_type,
        category: importForm.category.trim(),
        description: importForm.description,
        priority: Number(importForm.priority) || 0,
        cooldown_seconds: Math.max(0, Number(importForm.cooldown_seconds) || 0),
      });
      setShowImport(false);
      setImportFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await loadChoices();
    } catch (err) {
      setError(err?.message || "Asset import failed.");
    } finally {
      setBusy(null);
    }
  };

  const playAsset = async (asset) => {
    setBusy(`asset-${asset.id}`);
    setError(null);
    try {
      const result = await api.playAsset(asset.id);
      setStatus(result);
    } catch (err) {
      setError(err?.message || "Asset playback failed.");
    } finally {
      setBusy(null);
    }
  };

  const updateVolume = async (value) => {
    const next = Number(value);
    setVolume(next);
    try {
      const result = await api.setLiveAssistVolume(next);
      setStatus(result);
      setError(null);
    } catch (err) {
      setError(err?.message || "Volume update failed.");
      refreshStatus();
    }
  };

  const filteredSongs = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return songs;
    return songs.filter((song) =>
      [song.title, song.artist, song.album]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(q))
    );
  }, [query, songs]);

  const state = String(status?.state || "IDLE").toUpperCase();
  const currentFile = status?.file_path;
  const currentName = currentFile ? currentFile.split(/[\\/]/).pop() : "No track loaded";

  return (
    <section className="live-assist">
      <div className="live-assist__hero">
        <div>
          <span className="live-assist__eyebrow">LIVE ASSIST</span>
          <h2>Operator Control</h2>
          <p>
            Direct controls use the existing shared AudioEngine and existing
            song/asset playback APIs.
          </p>
        </div>
        <div className={`live-assist__state live-assist__state--${stateTone(state)}`}>
          <span />
          {label(state)}
        </div>
      </div>

      {error && <div className="live-assist__error">{error}</div>}

      <div className="live-assist__grid">
        <article className="assist-card">
          <div className="assist-card__heading">
            <div>
              <span className="assist-card__eyebrow">TRANSPORT</span>
              <h3>Live playback</h3>
            </div>
            <span className="assist-card__state">{label(state)}</span>
          </div>

          <div className="assist-current">
            <strong>{currentName}</strong>
            <span>
              {formatTime(status?.position_seconds)} / {formatTime(status?.duration_seconds)}
            </span>
          </div>

          <div className="assist-transport-buttons">
            <button
              className="assist-button assist-button--primary"
              disabled={busy !== null}
              onClick={() => runTransport("resume", api.resume)}
            >
              ▶ Resume
            </button>
            <button
              disabled={busy !== null || state !== "PLAYING"}
              onClick={() => runTransport("pause", api.pause)}
            >
              ❚❚ Pause
            </button>
            <button
              className="assist-button assist-button--danger"
              disabled={busy !== null || !["PLAYING", "PAUSED"].includes(state)}
              onClick={() => runTransport("stop", api.stop)}
            >
              ■ Stop
            </button>
          </div>

          <label className="assist-volume">
            <span>Master volume</span>
            <strong>{Math.round(volume * 100)}%</strong>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={volume}
              onChange={(event) => updateVolume(event.target.value)}
            />
          </label>
        </article>

        <article className="assist-card">
          <div className="assist-card__heading">
            <div>
              <span className="assist-card__eyebrow">MUSIC</span>
              <h3>Manual song</h3>
            </div>
          </div>

          <input
            className="assist-search"
            type="search"
            placeholder="Search song, artist or album..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />

          <select
            className="assist-select"
            value={selectedSongId}
            onChange={(event) => setSelectedSongId(event.target.value)}
          >
            <option value="">Select a song</option>
            {filteredSongs.map((song) => (
              <option key={song.id} value={song.id}>
                {song.title}{song.artist ? ` — ${song.artist}` : ""}
              </option>
            ))}
          </select>

          <button
            className="assist-button assist-button--primary assist-button--wide"
            disabled={!selectedSongId || busy !== null}
            onClick={playSelectedSong}
          >
            {busy === "song" ? "Starting…" : "▶ Play selected song"}
          </button>
        </article>
      </div>

      <article className="assist-card">
        <div className="assist-card__heading">
          <div>
            <span className="assist-card__eyebrow">STATION ASSETS</span>
            <h3>Jingles & advertisements</h3>
          </div>
          <div className="assist-card__heading-actions">
            <span className="assist-card__state">{assets.length} available</span>
            <button type="button" className="assist-import-button" onClick={openImport} disabled={busy !== null}>
              + Import Asset
            </button>
          </div>
        </div>

        <div className="assist-assets">
          {assets.length === 0 ? (
            <div className="assist-empty">No enabled station assets are available.</div>
          ) : (
            assets.map((asset) => (
              <div className="assist-asset" key={asset.id}>
                <div className="assist-asset__main">
                  <span className="assist-asset__type">{label(asset.asset_type)}</span>
                  <strong>{asset.name}</strong>
                  <small>
                    {asset.category || "Station asset"} · {formatTime(asset.duration)}
                  </small>
                </div>
                <button
                  disabled={busy !== null}
                  onClick={() => playAsset(asset)}
                >
                  {busy === `asset-${asset.id}` ? "Starting…" : "▶ Play"}
                </button>
              </div>
            ))
          )}
        </div>
      </article>

      {showImport && (
        <div className="assist-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && busy !== "import-asset") setShowImport(false);
        }}>
          <div className="assist-modal" role="dialog" aria-modal="true" aria-labelledby="import-asset-title">
            <div className="assist-modal__header">
              <div>
                <span className="assist-card__eyebrow">STATION ASSET</span>
                <h3 id="import-asset-title">Import Asset</h3>
              </div>
              <button type="button" className="assist-modal__close" onClick={() => setShowImport(false)} disabled={busy === "import-asset"}>×</button>
            </div>

            <label className="assist-field">
              <span>Audio file</span>
              <input ref={fileInputRef} type="file" accept="audio/*,.mp3,.wav,.ogg,.flac,.m4a,.aac" onChange={handleImportFile} />
              <small>{importFile?.name || "Select an audio file from this computer"}</small>
            </label>

            <div className="assist-form-grid">
              <label className="assist-field">
                <span>Asset type</span>
                <select value={importForm.asset_type} onChange={(e) => setImportForm((v) => ({ ...v, asset_type: e.target.value }))}>
                  <option value="JINGLE">Jingle</option>
                  <option value="ADVERTISEMENT">Advertisement</option>
                </select>
              </label>
              <label className="assist-field">
                <span>Name</span>
                <input value={importForm.name} onChange={(e) => setImportForm((v) => ({ ...v, name: e.target.value }))} placeholder="Morning Station ID" />
              </label>
              <label className="assist-field">
                <span>Category</span>
                <input value={importForm.category} onChange={(e) => setImportForm((v) => ({ ...v, category: e.target.value }))} placeholder="Station ID" />
              </label>
              <label className="assist-field">
                <span>Priority</span>
                <input type="number" value={importForm.priority} onChange={(e) => setImportForm((v) => ({ ...v, priority: e.target.value }))} />
              </label>
              <label className="assist-field">
                <span>Cooldown (seconds)</span>
                <input type="number" min="0" value={importForm.cooldown_seconds} onChange={(e) => setImportForm((v) => ({ ...v, cooldown_seconds: e.target.value }))} />
              </label>
            </div>

            <label className="assist-field">
              <span>Description</span>
              <textarea value={importForm.description} onChange={(e) => setImportForm((v) => ({ ...v, description: e.target.value }))} rows={3} placeholder="Optional description" />
            </label>

            <div className="assist-modal__actions">
              <button type="button" onClick={() => setShowImport(false)} disabled={busy === "import-asset"}>Cancel</button>
              <button type="button" className="assist-button assist-button--primary" onClick={importAsset} disabled={busy === "import-asset" || !importFile}>
                {busy === "import-asset" ? "Importing…" : "Import Asset"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

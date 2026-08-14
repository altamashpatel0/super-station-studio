import React, { useCallback, useState } from "react";
import MusicLibrary from "./components/MusicLibrary.jsx";
import PlaylistsPanel from "./components/PlaylistsPanel.jsx";
import QueuePanel from "./components/QueuePanel.jsx";
import { api } from "./api.js";

const TABS = [
  { key: "library", label: "Music Library" },
  { key: "playlists", label: "Playlists" },
  { key: "queue", label: "Queue" },
];

// V0.3 scope: Music Library (unchanged) plus new Playlist and Queue
// screens. "Now playing" and the queue's contents are shared across
// tabs so that, e.g., pressing Play on a playlist is reflected
// immediately in the Queue tab.
export default function App() {
  const [activeTab, setActiveTab] = useState("library");

  // The song currently selected in the Music Library. Carried over to
  // the Playlists tab so "Add selected song" has something to add.
  const [selectedLibrarySong, setSelectedLibrarySong] = useState(null);

  // Single source of truth for what the V0.1 AudioEngine is doing,
  // shared by the Library, Playlist, and Queue screens.
  const [nowPlaying, setNowPlaying] = useState({ song: null, state: "stopped" });

  // Bumped whenever something outside the Queue tab changes the
  // queue (e.g. "Play Playlist" / "Add Playlist to Queue"), so the
  // Queue tab knows to refetch even while it isn't mounted... it's
  // always mounted here, so this just triggers its effect.
  const [queueVersion, setQueueVersion] = useState(0);
  const bumpQueueVersion = useCallback(() => setQueueVersion((v) => v + 1), []);

  // Shared helper: actually start audio for a song via the V0.1
  // playback engine and update the shared "now playing" state.
  const playSongNow = useCallback(async (song) => {
    const status = await api.playSong(song.id);
    setNowPlaying({ song, state: (status.state || "playing").toLowerCase() });
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-header__mark">●</span>
        <h1>Super Station Studio</h1>
        <span className="app-header__badge">v0.3 — Library · Playlists · Queue</span>
      </header>

      <nav className="tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`tab-button ${activeTab === tab.key ? "is-active" : ""}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div style={{ display: activeTab === "library" ? "block" : "none" }}>
        <MusicLibrary
          selectedId={selectedLibrarySong?.id ?? null}
          onSelectSong={setSelectedLibrarySong}
          nowPlaying={nowPlaying}
          setNowPlaying={setNowPlaying}
        />
      </div>

      {activeTab === "playlists" && (
        <PlaylistsPanel
          selectedLibrarySong={selectedLibrarySong}
          playSongNow={playSongNow}
          bumpQueueVersion={bumpQueueVersion}
          onWentToQueue={() => setActiveTab("queue")}
        />
      )}

      {activeTab === "queue" && (
        <QueuePanel
          nowPlaying={nowPlaying}
          setNowPlaying={setNowPlaying}
          playSongNow={playSongNow}
          queueVersion={queueVersion}
          bumpQueueVersion={bumpQueueVersion}
        />
      )}
    </div>
  );
}

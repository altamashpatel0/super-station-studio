import React, { useCallback, useState } from "react";
import LiveMonitor from "./components/LiveMonitor.jsx";
import LiveAssist from "./components/LiveAssist.jsx";
import ReportsPanel from "./components/ReportsPanel.jsx";
import MusicLibrary from "./components/MusicLibrary.jsx";
import PlaylistsPanel from "./components/PlaylistsPanel.jsx";
import QueuePanel from "./components/QueuePanel.jsx";
import { api } from "./api.js";

const TABS = [
  { key: "live", label: "Live Monitor" },
  { key: "assist", label: "Live Assist" },
  { key: "reports", label: "Reports & History" },
  { key: "library", label: "Music Library" },
  { key: "playlists", label: "Playlists" },
  { key: "queue", label: "Queue" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState("live");
  const [selectedLibrarySong, setSelectedLibrarySong] = useState(null);
  const [nowPlaying, setNowPlaying] = useState({ song: null, state: "stopped" });
  const [queueVersion, setQueueVersion] = useState(0);

  const bumpQueueVersion = useCallback(() => setQueueVersion((v) => v + 1), []);

  const playSongNow = useCallback(async (song) => {
    const status = await api.playSong(song.id);
    setNowPlaying({ song, state: (status.state || "playing").toLowerCase() });
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__brand">
          <span className="app-header__mark">●</span>
          <div>
            <h1>Super Station Studio</h1>
            <span className="app-header__subtitle">Broadcast control &amp; playout</span>
          </div>
        </div>
        <span className="app-header__badge">V0.8 · LIVE ASSIST &amp; REPORTS</span>
      </header>

      <nav className="tabs" aria-label="Main navigation">
        {TABS.map((tab) => (
          <button
            type="button"
            key={tab.key}
            className={`tab-button ${activeTab === tab.key ? "is-active" : ""}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "live" && <LiveMonitor />}
      {activeTab === "assist" && <LiveAssist />}
      {activeTab === "reports" && <ReportsPanel />}

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

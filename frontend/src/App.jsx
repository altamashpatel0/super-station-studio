import React from "react";
import MusicLibrary from "./components/MusicLibrary.jsx";

// V0.2 scope: just the Music Library screen. The full multi-panel
// dashboard (decks, clock wheel, scheduler) is a later milestone.
export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-header__mark">●</span>
        <h1>Super Station Studio</h1>
        <span className="app-header__badge">v0.2 — Music Library</span>
      </header>
      <MusicLibrary />
    </div>
  );
}

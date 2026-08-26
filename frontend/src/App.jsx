import { useState } from 'react';
import Sidebar from './components/layout/Sidebar';
import TopBar from './components/layout/TopBar';
import StatusBar from './components/layout/StatusBar';
import Dashboard from './pages/Dashboard';
import MusicLibrary from './pages/MusicLibrary';
import Playlists from './pages/Playlists';
import Jingles from './pages/Jingles';
import Advertisements from './pages/Advertisements';
import Scheduler from './pages/Scheduler';
import Logs from './pages/Logs';
import Settings from './pages/Settings';
import usePlayerState from './hooks/usePlayerState';
import './App.css';

const PAGES = {
  dashboard: Dashboard,
  library: MusicLibrary,
  playlists: Playlists,
  jingles: Jingles,
  advertisements: Advertisements,
  scheduler: Scheduler,
  logs: Logs,
  settings: Settings,
};

export default function App() {
  const [activePage, setActivePage] = useState('dashboard');
  const player = usePlayerState();
  const onAir = String(player.station?.mode || '').toUpperCase() === 'ON_AIR';

  const ActivePageComponent = PAGES[activePage] ?? Dashboard;

  return (
    <div className="app">
      <Sidebar activePage={activePage} onNavigate={setActivePage} />
      <div className="app__content">
        <TopBar onAir={onAir} onNavigate={setActivePage} />
        <main className="app__main">
          <ActivePageComponent player={player} />
        </main>
        <StatusBar player={player} />
      </div>
    </div>
  );
}

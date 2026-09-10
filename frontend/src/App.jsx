import React, { useEffect, useState } from 'react';
import Sidebar from './components/layout/Sidebar';
import TopBar from './components/layout/TopBar';
import StatusBar from './components/layout/StatusBar';
import Dashboard from './pages/Dashboard';
import MusicLibrary from './pages/MusicLibrary';
import Playlists from './pages/Playlists';
import Jingles from './pages/Jingles';
import Advertisements from './pages/Advertisements';
import Promos from './pages/Promos';
import Scheduler from './pages/Scheduler';
import Logs from './pages/Logs';
import ScheduleCenter from './pages/ScheduleCenter';
import Settings from './pages/Settings';
import usePlayerState from './hooks/usePlayerState';
import './App.css';

class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: '' };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, message: error?.message || 'Unexpected interface error.' };
  }
  componentDidCatch(error, info) {
    console.error('Super Station Studio UI error', error, info);
  }
  render() {
    if (this.state.hasError) {
      return <div className="app-error-screen"><h1>Super Station Studio</h1><p>The interface hit an unexpected error.</p><small>{this.state.message}</small><button type="button" onClick={() => window.location.reload()}>Reload Studio</button></div>;
    }
    return this.props.children;
  }
}

const PAGES = { dashboard: Dashboard, library: MusicLibrary, playlists: Playlists, jingles: Jingles, advertisements: Advertisements, promos: Promos, scheduler: Scheduler, logs: Logs, scheduleCenter: ScheduleCenter, settings: Settings };

export default function App() {
  const [activePage, setActivePage] = useState('dashboard');
  const [theme, setTheme] = useState(() => localStorage.getItem('sss-theme') || 'dark');
  const [stationName, setStationName] = useState(() => localStorage.getItem('sss-station') || '101.3 FM — The Coastline');
  const [refreshMs, setRefreshMs] = useState(() => Number(localStorage.getItem('sss-refresh-ms')) || 1000);
  const player = usePlayerState({ intervalMs: refreshMs });
  const onAir = String(player.station?.mode || '').toUpperCase() === 'ON_AIR';

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('sss-theme', theme);
  }, [theme]);

  const ActivePageComponent = PAGES[activePage] ?? Dashboard;

  return (
    <AppErrorBoundary>
    <div className="app" data-theme={theme}>
      <Sidebar activePage={activePage} onNavigate={setActivePage} />
      <div className="app__content">
        <TopBar onAir={onAir} onNavigate={setActivePage} theme={theme} onToggleTheme={() => setTheme((v) => v === 'dark' ? 'light' : 'dark')} />
        <main className="app__main"><ActivePageComponent player={player} stationName={stationName} onStationChange={setStationName} onRefreshChange={setRefreshMs} onNavigate={setActivePage} /></main>
        <StatusBar player={player} />
      </div>
    </div>
    </AppErrorBoundary>
  );
}

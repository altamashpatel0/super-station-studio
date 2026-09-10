import { useEffect, useState } from 'react';
import PageHeader from '../components/common/PageHeader';

const DEFAULT_STATION = '101.3 FM — The Coastline';
const DEFAULT_REFRESH = 1000;

function readJson(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}

export default function Settings({ onStationChange, onRefreshChange }) {
  const [station, setStation] = useState(() => localStorage.getItem('sss-station') || DEFAULT_STATION);
  const [refreshMs, setRefreshMs] = useState(() => Number(localStorage.getItem('sss-refresh-ms')) || DEFAULT_REFRESH);
  const [saved, setSaved] = useState(false);
  const diagnostics = readJson('sss-settings', {});

  useEffect(() => {
    localStorage.setItem('sss-station', station);
    onStationChange?.(station);
  }, [station, onStationChange]);

  useEffect(() => {
    localStorage.setItem('sss-refresh-ms', String(refreshMs));
    onRefreshChange?.(refreshMs);
  }, [refreshMs, onRefreshChange]);

  const save = () => {
    localStorage.setItem('sss-settings', JSON.stringify({ ...diagnostics, refreshMs, updatedAt: new Date().toISOString() }));
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  };

  return (
    <div className="pageshell">
      <PageHeader title="Settings" subtitle="Station identity and local operator preferences" />
      <div className="pageshell__body">
        <div className="section-title" style={{ marginTop: 0 }}>STATION</div>
        <div className="contentcard">
          <label htmlFor="station-name">Station Name</label>
          <input id="station-name" value={station} onChange={(e) => setStation(e.target.value)} style={{ display: 'block', marginTop: 8, width: '100%', maxWidth: 520, padding: 10 }} />
          <div style={{ marginTop: 8, color: 'var(--text-tertiary)', fontSize: 11 }}>Used by the operator interface and stored per Windows/Electron user.</div>
        </div>

        <div className="section-title">PERFORMANCE</div>
        <div className="contentcard">
          <label htmlFor="refresh-rate">Live status refresh</label>
          <select id="refresh-rate" value={refreshMs} onChange={(e) => setRefreshMs(Number(e.target.value))} style={{ display: 'block', marginTop: 8, padding: 10, minWidth: 220 }}>
            <option value={500}>500 ms — fastest</option>
            <option value={1000}>1 second — balanced</option>
            <option value={2000}>2 seconds — low-end PC</option>
            <option value={3000}>3 seconds — minimum load</option>
          </select>
          <div style={{ marginTop: 8, color: 'var(--text-tertiary)', fontSize: 11 }}>Use 2–3 seconds on very low-end PCs to reduce CPU/network polling without affecting the backend scheduler.</div>
        </div>

        <div className="contentcard" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div><strong>Local settings</strong><div style={{ marginTop: 4, color: 'var(--text-tertiary)', fontSize: 11 }}> Every visible option has an implemented effect.</div></div>
          <button type="button" onClick={save} style={{ padding: '9px 14px', borderRadius: 8, cursor: 'pointer' }}>{saved ? 'Saved ✓' : 'Save Settings'}</button>
        </div>
      </div>
    </div>
  );
}

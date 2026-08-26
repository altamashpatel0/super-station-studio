import { useEffect, useMemo, useState } from 'react';
import {
  CalendarClock,
  Check,
  ChevronDown,
  Clock3,
  ListMusic,
  Megaphone,
  Mic2,
  Music2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import { api } from '../api';
import './Scheduler.css';

const DAYS = [
  ['Monday', 'Mon'],
  ['Tuesday', 'Tue'],
  ['Wednesday', 'Wed'],
  ['Thursday', 'Thu'],
  ['Friday', 'Fri'],
  ['Saturday', 'Sat'],
  ['Sunday', 'Sun'],
];

const TARGETS = [
  { key: 'SONG', label: 'Songs', icon: Music2 },
  { key: 'PLAYLIST', label: 'Playlists', icon: ListMusic },
  { key: 'ADVERTISEMENT', label: 'Advertisements', icon: Megaphone },
  { key: 'JINGLE', label: 'Jingles', icon: Mic2 },
];

function addMonths(dateString, months) {
  const d = new Date(`${dateString}T12:00:00`);
  const day = d.getDate();
  d.setMonth(d.getMonth() + months, 1);
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  d.setDate(Math.min(day, last));
  return d.toISOString().slice(0, 10);
}

function todayISO() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function displayDate(value) {
  if (!value) return 'No end date';
  return new Date(`${value}T12:00:00`).toLocaleDateString(undefined, {
    day: '2-digit', month: 'short', year: 'numeric',
  });
}

function targetLabel(type) {
  return TARGETS.find((x) => x.key === type)?.label || type;
}

function targetIcon(type) {
  return TARGETS.find((x) => x.key === type)?.icon || CalendarClock;
}

function targetName(item, type) {
  if (!item) return 'Unknown target';
  if (type === 'SONG') return item.title || item.name || `Song #${item.id}`;
  return item.name || item.title || `#${item.id}`;
}

export default function Scheduler() {
  const [schedules, setSchedules] = useState([]);
  const [songs, setSongs] = useState([]);
  const [playlists, setPlaylists] = useState([]);
  const [ads, setAds] = useState([]);
  const [jingles, setJingles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [type, setType] = useState('SONG');
  const [selectedId, setSelectedId] = useState(null);
  const [search, setSearch] = useState('');
  const [name, setName] = useState('');
  const [startTime, setStartTime] = useState('09:00');
  const [endTime, setEndTime] = useState('09:05');
  const [startDate, setStartDate] = useState(todayISO());
  const [endDate, setEndDate] = useState(addMonths(todayISO(), 6));
  const [days, setDays] = useState([0, 1, 2, 3, 4, 5, 6]);

  const selectedCollection = useMemo(() => {
    if (type === 'SONG') return songs;
    if (type === 'PLAYLIST') return playlists;
    if (type === 'ADVERTISEMENT') return ads;
    return jingles;
  }, [type, songs, playlists, ads, jingles]);

  const filteredCollection = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return selectedCollection;
    return selectedCollection.filter((item) => {
      const text = `${item.id} ${item.title || ''} ${item.name || ''} ${item.artist || ''} ${item.category || ''}`.toLowerCase();
      return text.includes(q);
    });
  }, [search, selectedCollection]);

  const selectedItem = selectedCollection.find((item) => Number(item.id) === Number(selectedId));

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [scheduleRows, songRows, playlistRows, adRows, jingleRows] = await Promise.all([
        api.listSchedules(),
        api.listSongs({ limit: 1000 }),
        api.listPlaylists(),
        api.listAssets({ asset_type: 'ADVERTISEMENT' }),
        api.listAssets({ asset_type: 'JINGLE' }),
      ]);
      setSchedules(scheduleRows || []);
      setSongs(songRows || []);
      setPlaylists(playlistRows || []);
      setAds(adRows || []);
      setJingles(jingleRows || []);
    } catch (e) {
      setError(e.message || 'Unable to load scheduler data.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function resetForm() {
    const start = todayISO();
    setEditing(null);
    setType('SONG');
    setSelectedId(null);
    setSearch('');
    setName('');
    setStartTime('09:00');
    setEndTime('09:05');
    setStartDate(start);
    setEndDate(addMonths(start, 6));
    setDays([0, 1, 2, 3, 4, 5, 6]);
  }

  function openCreate() {
    resetForm();
    setModalOpen(true);
  }

  function openEdit(schedule) {
    setEditing(schedule);
    setType(schedule.target_type);
    setSelectedId(schedule.target_id);
    setSearch('');
    setName(schedule.name || '');
    setStartTime(schedule.start_time);
    setEndTime(schedule.end_time);
    setStartDate(schedule.start_date || todayISO());
    setEndDate(schedule.end_date || addMonths(schedule.start_date || todayISO(), 6));
    setDays(schedule.days_of_week || []);
    setModalOpen(true);
  }

  function closeModal() {
    if (!saving) setModalOpen(false);
  }

  function switchType(next) {
    setType(next);
    setSelectedId(null);
    setSearch('');
  }

  function toggleDay(day) {
    setDays((current) => current.includes(day)
      ? current.filter((x) => x !== day)
      : [...current, day].sort((a, b) => a - b));
  }

  function applySixMonthEnd() {
    if (startDate) setEndDate(addMonths(startDate, 6));
  }

  async function saveSchedule(e) {
    e.preventDefault();
    if (!selectedId) return setError('Select a song, playlist, advertisement, or jingle first.');
    if (!days.length) return setError('Select at least one day.');
    if (endTime <= startTime) return setError('End time must be later than start time.');
    if (endDate < startDate) return setError('End date must be on or after start date.');
    if (endDate > addMonths(startDate, 6)) return setError('A schedule can run for a maximum of 6 calendar months.');

    setSaving(true);
    setError('');
    try {
      const payload = {
        name: name.trim() || `${targetLabel(type)} — ${targetName(selectedItem, type)}`,
        target_type: type,
        target_id: Number(selectedId),
        start_time: startTime,
        end_time: endTime,
        days_of_week: days,
        start_date: startDate,
        end_date: endDate,
        enabled: editing ? editing.enabled : true,
      };
      if (editing) await api.updateSchedule(editing.id, payload);
      else await api.createSchedule(payload);
      setModalOpen(false);
      await load();
    } catch (e) {
      setError(e.message || 'Unable to save schedule.');
    } finally {
      setSaving(false);
    }
  }

  async function toggleSchedule(schedule) {
    try {
      if (schedule.enabled) await api.disableSchedule(schedule.id);
      else await api.enableSchedule(schedule.id);
      await load();
    } catch (e) { setError(e.message || 'Unable to update schedule.'); }
  }

  async function removeSchedule(schedule) {
    if (!window.confirm(`Delete “${schedule.name}”?`)) return;
    try {
      await api.deleteSchedule(schedule.id);
      await load();
    } catch (e) { setError(e.message || 'Unable to delete schedule.'); }
  }

  return (
    <div className="pageshell scheduler-page">
      <PageHeader
        title="Scheduler"
        subtitle="Schedule songs, playlists, advertisements and jingles for up to 6 months"
        actions={(
          <div className="scheduler-actions">
            <Button variant="secondary" icon={RefreshCw} onClick={load}>Refresh</Button>
            <Button variant="primary" icon={Plus} onClick={openCreate}>Add Schedule</Button>
          </div>
        )}
      />

      <div className="pageshell__body scheduler-body">
        {error && <div className="scheduler-error">{error}<button onClick={() => setError('')}><X size={15} /></button></div>}

        <div className="scheduler-summary">
          <div><CalendarClock size={18} /><span><strong>{schedules.length}</strong> schedules</span></div>
          <div><Clock3 size={18} /><span><strong>{schedules.filter((x) => x.enabled).length}</strong> active</span></div>
          <div className="range-note"><span>Maximum range: <strong>6 calendar months</strong></span></div>
        </div>

        <div className="schedule-list">
          {loading ? <div className="scheduler-empty">Loading schedules…</div> : schedules.length === 0 ? (
            <div className="scheduler-empty"><CalendarClock size={30} /><strong>No schedules yet</strong><span>Add your first song, playlist, ad or jingle schedule.</span><button onClick={openCreate}><Plus size={16} /> Add Schedule</button></div>
          ) : schedules.map((schedule) => {
            const Icon = targetIcon(schedule.target_type);
            return (
              <div className={`schedule-row ${schedule.enabled ? '' : 'is-disabled'}`} key={schedule.id}>
                <div className="schedule-time"><span>{schedule.start_time}</span><small>to {schedule.end_time}</small></div>
                <div className="schedule-icon"><Icon size={17} /></div>
                <div className="schedule-main">
                  <div className="schedule-title"><strong>{schedule.name}</strong><span className="schedule-badge">{targetLabel(schedule.target_type)}</span></div>
                  <div className="schedule-meta">
                    <span>ID #{schedule.target_id}</span>
                    <span>{(schedule.days_of_week || []).map((d) => DAYS[d]?.[1]).join(' · ')}</span>
                    <span>{displayDate(schedule.start_date)} — {displayDate(schedule.end_date)}</span>
                  </div>
                </div>
                <button className={`schedule-toggle ${schedule.enabled ? 'on' : ''}`} onClick={() => toggleSchedule(schedule)}>{schedule.enabled ? 'ON' : 'OFF'}</button>
                <button className="icon-button" title="Edit" onClick={() => openEdit(schedule)}><Pencil size={16} /></button>
                <button className="icon-button danger" title="Delete" onClick={() => removeSchedule(schedule)}><Trash2 size={16} /></button>
              </div>
            );
          })}
        </div>
      </div>

      {modalOpen && (
        <div className="scheduler-overlay" onMouseDown={(e) => e.target === e.currentTarget && closeModal()}>
          <form className="scheduler-modal" onSubmit={saveSchedule}>
            <div className="modal-head">
              <div><h2>{editing ? 'Edit Schedule' : 'Add Schedule'}</h2><p>Select one content item and define when it should run.</p></div>
              <button type="button" className="icon-button" onClick={closeModal}><X size={18} /></button>
            </div>

            <div className="modal-grid">
              <section className="selector-section">
                <label>Content type</label>
                <div className="target-tabs">
                  {TARGETS.map(({ key, label, icon: Icon }) => (
                    <button type="button" key={key} className={type === key ? 'active' : ''} onClick={() => switchType(key)}><Icon size={16} />{label}</button>
                  ))}
                </div>
                <div className="content-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={`Search ${targetLabel(type).toLowerCase()}…`} /></div>
                <div className="content-picker">
                  {filteredCollection.length === 0 ? <div className="picker-empty">No matching {targetLabel(type).toLowerCase()} found.</div> : filteredCollection.map((item) => {
                    const active = Number(selectedId) === Number(item.id);
                    return <button type="button" key={item.id} className={`content-option ${active ? 'selected' : ''}`} onClick={() => setSelectedId(item.id)}>
                      <span className="radio">{active && <Check size={13} />}</span>
                      <span className="content-option-main"><strong>{targetName(item, type)}</strong><small>#{item.id}{item.artist ? ` · ${item.artist}` : ''}{item.category ? ` · ${item.category}` : ''}</small></span>
                      {item.duration ? <span className="duration">{Math.round(item.duration)}s</span> : null}
                    </button>;
                  })}
                </div>
              </section>

              <section className="settings-section">
                <label>Schedule name</label>
                <input className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Morning Drive Song" />

                <div className="field-row">
                  <div><label>Start time</label><input className="field" type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} /></div>
                  <div><label>End time</label><input className="field" type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} /></div>
                </div>

                <label>Repeat on</label>
                <div className="days-grid">
                  {DAYS.map(([full, short], i) => <button type="button" title={full} key={full} className={days.includes(i) ? 'active' : ''} onClick={() => toggleDay(i)}>{short}</button>)}
                </div>

                <div className="field-row">
                  <div><label>Start date</label><input className="field" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></div>
                  <div><label>End date</label><input className="field" type="date" value={endDate} max={startDate ? addMonths(startDate, 6) : undefined} onChange={(e) => setEndDate(e.target.value)} /></div>
                </div>
                <button type="button" className="six-month-button" onClick={applySixMonthEnd}><CalendarClock size={15} /> Set maximum 6 months</button>

                <div className="schedule-hint"><Check size={15} /><span>This schedule can repeat on the selected days until <strong>{displayDate(endDate)}</strong>.</span></div>
              </section>
            </div>

            <div className="modal-foot"><button type="button" className="cancel-button" onClick={closeModal}>Cancel</button><button className="save-button" disabled={saving || !selectedId}>{saving ? 'Saving…' : editing ? 'Save Changes' : 'Add Schedule'}</button></div>
          </form>
        </div>
      )}
    </div>
  );
}

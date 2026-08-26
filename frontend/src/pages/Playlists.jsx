import { useEffect, useMemo, useState } from 'react';
import { ListMusic, Plus, Trash2, Play, RefreshCw, X, Check, CheckSquare, Square, Search, ListPlus } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import { api } from '../api';
import './Playlists.css';

export default function Playlists() {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [songs, setSongs] = useState([]);
  const [selectedSongIds, setSelectedSongIds] = useState(new Set());
  const [trackSearch, setTrackSearch] = useState('');
  const [showTrackPicker, setShowTrackPicker] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      setError('');
      const [rows, library] = await Promise.all([
        api.listPlaylists(),
        api.listSongs({ limit: 500 }),
      ]);
      setItems(Array.isArray(rows) ? rows : rows?.items || []);
      setSongs(Array.isArray(library) ? library : library?.items || []);
      if (selected?.id) setSelected(await api.getPlaylist(selected.id));
    } catch (e) {
      setError(e.message || 'Unable to load playlists.');
    }
  };

  useEffect(() => { load(); }, []);

  const openPlaylist = async (id) => {
    try {
      setError('');
      setSelected(await api.getPlaylist(id));
      setSelectedSongIds(new Set());
      setTrackSearch('');
      setShowTrackPicker(false);
    } catch (e) { setError(e.message); }
  };

  const create = async () => {
    const name = window.prompt('Playlist name?');
    if (!name?.trim()) return;
    try { setBusy(true); await api.createPlaylist(name.trim()); await load(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const remove = async (id) => {
    if (!window.confirm('Delete this playlist?')) return;
    try { setBusy(true); await api.deletePlaylist(id); setSelected(null); await load(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const play = async (id) => {
    try { setBusy(true); setError(''); const rows = await api.addPlaylistToQueue(id); if (rows?.length) await api.playQueue(rows[0].id); await load(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const playlistSongIds = useMemo(() => new Set((selected?.tracks || []).map(t => Number(t.song_id))), [selected]);

  const availableSongs = useMemo(() => {
    const q = trackSearch.trim().toLowerCase();
    return songs
      .filter(s => s.enabled !== false && !playlistSongIds.has(Number(s.id)))
      .filter(s => !q || `${s.title || s.name || ''} ${s.artist || ''}`.toLowerCase().includes(q));
  }, [songs, playlistSongIds, trackSearch]);

  const toggleSong = (id) => {
    setSelectedSongIds(prev => {
      const next = new Set(prev);
      if (next.has(Number(id))) next.delete(Number(id));
      else next.add(Number(id));
      return next;
    });
  };

  const selectAllVisible = () => {
    setSelectedSongIds(prev => {
      const next = new Set(prev);
      availableSongs.forEach(s => next.add(Number(s.id)));
      return next;
    });
  };

  const clearSelection = () => setSelectedSongIds(new Set());

  const allVisibleSelected = availableSongs.length > 0 && availableSongs.every(s => selectedSongIds.has(Number(s.id)));

  const addSelectedTracks = async () => {
    if (!selected?.id || selectedSongIds.size === 0) return;
    try {
      setBusy(true);
      setError('');
      const ids = Array.from(selectedSongIds);
      let added = 0;
      for (const id of ids) {
        await api.addTrackToPlaylist(selected.id, id);
        added += 1;
      }
      setSelected(await api.getPlaylist(selected.id));
      setSelectedSongIds(new Set());
      setShowTrackPicker(false);
      await load();
      setInfo(`${added} track${added === 1 ? '' : 's'} added to playlist.`);
      setTimeout(() => setInfo(''), 2500);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const removeTrack = async (trackId) => {
    if (!selected?.id) return;
    try { setBusy(true); await api.removeTrackFromPlaylist(selected.id, trackId); setSelected(await api.getPlaylist(selected.id)); await load(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="pageshell">
      <PageHeader title="Playlists" subtitle={`${items.length} playlists`} actions={<>
        <Button variant="primary" icon={Plus} onClick={create} disabled={busy}>New Playlist</Button>
        <Button icon={RefreshCw} onClick={load} disabled={busy}>Refresh</Button>
      </>} />
      <div className="pageshell__body">
        {error && <div className="badge badge--error" style={{ marginBottom: 12 }}>{error}</div>}
        {info && <div className="playlist-info">{info}</div>}
        <div className="playlist-layout">
          <div className="playlist-list cardgrid">
            {items.map(p => (
              <button key={p.id} onClick={() => openPlaylist(p.id)} className={`playlist-list__item ${selected?.id === p.id ? 'is-selected' : ''}`}>
                <ListMusic size={15}/> <span>{p.name}</span> <span className="playlist-list__count">{p.track_count ?? 0}</span>
              </button>
            ))}
            {!items.length && <div style={{ padding: 20 }}>No playlists yet.</div>}
          </div>

          <div className="contentcard playlist-detail">
            {selected ? <>
              <div className="playlist-detail__header">
                <div><h2>{selected.name}</h2><p>{selected.description || 'No description'}</p></div>
                <div className="playlist-detail__actions">
                  <Button icon={Play} onClick={() => play(selected.id)} disabled={busy}>Play</Button>
                  <button onClick={() => remove(selected.id)} title="Delete" disabled={busy}><Trash2 size={15}/></button>
                </div>
              </div>

              <div className="playlist-track-toolbar">
                <div>
                  <strong>{selected.tracks?.length || 0} tracks</strong>
                  <span className="muted"> Add songs without leaving this playlist.</span>
                </div>
                <Button icon={ListPlus} onClick={() => setShowTrackPicker(v => !v)} disabled={busy}>
                  {showTrackPicker ? 'Close Track Selector' : 'Add Tracks'}
                </Button>
              </div>

              {showTrackPicker && (
                <div className="track-picker">
                  <div className="track-picker__top">
                    <div className="track-picker__title"><ListPlus size={17}/><div><strong>Select tracks</strong><small>Choose one, several, or all available tracks.</small></div></div>
                    <div className="track-picker__selection"><strong>{selectedSongIds.size}</strong> selected</div>
                  </div>

                  <div className="track-picker__controls">
                    <label className="track-search"><Search size={15}/><input value={trackSearch} onChange={e => setTrackSearch(e.target.value)} placeholder="Search title or artist..." /></label>
                    <button className="picker-action" onClick={allVisibleSelected ? clearSelection : selectAllVisible} disabled={!availableSongs.length}>
                      {allVisibleSelected ? <><CheckSquare size={15}/> Clear visible</> : <><Square size={15}/> Select all visible</>}
                    </button>
                    {selectedSongIds.size > 0 && <button className="picker-action picker-action--ghost" onClick={clearSelection}>Clear selection</button>}
                  </div>

                  <div className="track-picker__list">
                    {availableSongs.map(song => {
                      const checked = selectedSongIds.has(Number(song.id));
                      return (
                        <button key={song.id} className={`track-option ${checked ? 'is-selected' : ''}`} onClick={() => toggleSong(song.id)}>
                          <span className="track-option__check">{checked ? <Check size={15}/> : null}</span>
                          <span className="track-option__main"><strong>{song.title || song.name || `Song #${song.id}`}</strong><small>{song.artist || 'Unknown artist'}</small></span>
                          <span className="track-option__duration">{Math.round(song.duration || 0)}s</span>
                        </button>
                      );
                    })}
                    {!availableSongs.length && <div className="track-picker__empty">No available tracks match your search, or all library tracks are already in this playlist.</div>}
                  </div>

                  <div className="track-picker__footer">
                    <span>{selectedSongIds.size ? `${selectedSongIds.size} track${selectedSongIds.size === 1 ? '' : 's'} ready to add` : 'Select tracks above'}</span>
                    <Button icon={Plus} variant="primary" onClick={addSelectedTracks} disabled={!selectedSongIds.size || busy}>
                      Add {selectedSongIds.size || ''} Selected Track{selectedSongIds.size === 1 ? '' : 's'}
                    </Button>
                  </div>
                </div>
              )}

              <table className="datatable"><thead><tr><th>#</th><th>Title</th><th>Artist</th><th>Duration</th><th></th></tr></thead>
                <tbody>{(selected.tracks || []).map((t, i) => <tr key={t.id}>
                  <td>{i + 1}</td><td>{t.song?.title || `Song #${t.song_id}`}</td><td>{t.song?.artist || '—'}</td><td>{Math.round(t.song?.duration || 0)}s</td>
                  <td><button onClick={() => removeTrack(t.id)} title="Remove track" disabled={busy}><X size={14}/></button></td>
                </tr>)}
                {!selected.tracks?.length && <tr><td colSpan="5" style={{ textAlign: 'center', padding: 32 }}>No tracks in this playlist. Click <strong>Add Tracks</strong> to select songs.</td></tr>}
                </tbody>
              </table>
            </> : <div style={{ padding: 32, color: 'var(--text-tertiary)' }}>Select a playlist to view and manage its tracks.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

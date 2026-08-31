import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ListMusic, Plus, Trash2, Play, RefreshCw, X, Check, CheckSquare, Square, Search, ListPlus, MoreVertical, Pencil, Music } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import { api } from '../api';
import './Playlists.css';

function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.round(Number(totalSeconds) || 0));
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

export default function Playlists() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [songs, setSongs] = useState([]);
  const [selectedSongIds, setSelectedSongIds] = useState(new Set());
  const [trackSearch, setTrackSearch] = useState('');
  const [showTrackPicker, setShowTrackPicker] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [busy, setBusy] = useState(false);
  const [dragTrackId, setDragTrackId] = useState(null);
  const [dragOverTrackId, setDragOverTrackId] = useState(null);
  const [openMenuId, setOpenMenuId] = useState(null);

  // --- FLIP animation refs (visual-only; no reorder/API logic here) ---
  const trackRowRefs = useRef(new Map());
  const prevTrackRects = useRef(null);

  const prefersReducedMotion = () =>
    typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const captureTrackRowRects = () => {
    const rects = new Map();
    trackRowRefs.current.forEach((node, id) => {
      if (node) rects.set(id, node.getBoundingClientRect());
    });
    return rects;
  };

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
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  // Close any open sidebar menu when clicking elsewhere.
  useEffect(() => {
    if (!openMenuId) return;
    const closeMenu = () => setOpenMenuId(null);
    window.addEventListener('click', closeMenu);
    return () => window.removeEventListener('click', closeMenu);
  }, [openMenuId]);

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
    try {
      setBusy(true);
      await api.deletePlaylist(id);
      if (selected?.id === id) setSelected(null);
      await load();
    }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const rename = async (playlist) => {
    const name = window.prompt('Playlist name?', playlist.name || '');
    if (!name?.trim()) return;
    const description = window.prompt('Playlist description? (optional)', playlist.description || '');
    try {
      setBusy(true);
      setError('');
      await api.updatePlaylist(playlist.id, { name: name.trim(), description: description || '' });
      if (selected?.id === playlist.id) setSelected(await api.getPlaylist(playlist.id));
      await load();
    } catch (e) { setError(e.message); }
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

  // Invert + Play: after the track list re-renders in its new order,
  // work out how far each row visually moved and animate it back from
  // that offset to its resting position using a transform only.
  useLayoutEffect(() => {
    const prevRects = prevTrackRects.current;
    if (!prevRects) return;
    prevTrackRects.current = null;

    if (prefersReducedMotion()) return;

    trackRowRefs.current.forEach((node, id) => {
      if (!node) return;
      const prevRect = prevRects.get(id);
      if (!prevRect) return;
      const newRect = node.getBoundingClientRect();
      const deltaY = prevRect.top - newRect.top;
      if (!deltaY) return;

      node.style.transition = 'none';
      node.style.transform = `translateY(${deltaY}px)`;

      requestAnimationFrame(() => {
        node.style.transition = 'transform 220ms cubic-bezier(0.22, 1, 0.36, 1)';
        node.style.transform = '';
      });
    });
  }, [selected?.tracks]);

  const handleTrackDragStart = (trackId) => {
    setDragTrackId(trackId);
  };

  const handleTrackDragOver = (e, trackId) => {
    e.preventDefault();
    if (trackId !== dragOverTrackId) setDragOverTrackId(trackId);
  };

  const handleTrackDragEnd = () => {
    setDragTrackId(null);
    setDragOverTrackId(null);
  };

  const handleTrackDrop = async (e, targetTrackId) => {
    e.preventDefault();
    const draggedId = dragTrackId;
    setDragTrackId(null);
    setDragOverTrackId(null);
    if (!selected?.id || draggedId == null || draggedId === targetTrackId) return;

    const currentTracks = selected.tracks || [];
    const fromIndex = currentTracks.findIndex(t => t.id === draggedId);
    const toIndex = currentTracks.findIndex(t => t.id === targetTrackId);
    if (fromIndex === -1 || toIndex === -1) return;

    const reordered = [...currentTracks];
    const [moved] = reordered.splice(fromIndex, 1);
    reordered.splice(toIndex, 0, moved);

    const previousTracks = currentTracks;
    if (!prefersReducedMotion()) prevTrackRects.current = captureTrackRowRects();
    setSelected(prev => ({ ...prev, tracks: reordered }));

    try {
      setError('');
      await api.reorderPlaylistTracks(selected.id, reordered.map(t => t.id));
      await load();
    } catch (e) {
      setSelected(prev => ({ ...prev, tracks: previousTracks }));
      setError(e.message || 'Unable to save new track order.');
    }
  };

  const totalDurationSeconds = useMemo(
    () => (selected?.tracks || []).reduce((sum, t) => sum + (Number(t.song?.duration) || 0), 0),
    [selected]
  );

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
          <div className="playlist-list">
            {items.map(p => (
              <div
                key={p.id}
                className={`playlist-list__item ${selected?.id === p.id ? 'is-selected' : ''}`}
                onClick={() => openPlaylist(p.id)}
              >
                <span className="playlist-list__icon"><ListMusic size={16}/></span>
                <span className="playlist-list__text">
                  <strong className="playlist-list__name">{p.name}</strong>
                  <span className="playlist-list__count">{p.track_count ?? 0} tracks</span>
                </span>
                <span className="playlist-list__menu">
                  <button
                    type="button"
                    className="playlist-list__menu-btn"
                    title="Playlist actions"
                    onClick={(e) => { e.stopPropagation(); setOpenMenuId(openMenuId === p.id ? null : p.id); }}
                  >
                    <MoreVertical size={15}/>
                  </button>
                  {openMenuId === p.id && (
                    <div className="playlist-list__dropdown" onClick={(e) => e.stopPropagation()}>
                      <button onClick={() => { setOpenMenuId(null); rename(p); }} disabled={busy}>
                        <Pencil size={13}/> Rename
                      </button>
                      <button className="is-danger" onClick={() => { setOpenMenuId(null); remove(p.id); }} disabled={busy}>
                        <Trash2 size={13}/> Delete
                      </button>
                    </div>
                  )}
                </span>
              </div>
            ))}
            {!items.length && loading && <div className="playlist-list__loading">Loading playlists…</div>}
            {!items.length && !loading && <div className="playlist-list__empty">No playlists yet.</div>}
          </div>

          <div className="contentcard playlist-detail">
            {selected ? <>
              <div className="playlist-detail__header">
                <div><h2>{selected.name}</h2><p>{selected.description || 'No description'}</p></div>
                <div className="playlist-detail__actions">
                  <Button icon={Play} onClick={() => play(selected.id)} disabled={busy}>Play</Button>
                  <button className="iconbtn" onClick={() => rename(selected)} title="Edit playlist" disabled={busy}><Pencil size={15}/></button>
                  <button className="iconbtn iconbtn--danger" onClick={() => remove(selected.id)} title="Delete playlist" disabled={busy}><Trash2 size={15}/></button>
                </div>
              </div>

              <div className="playlist-track-toolbar">
                <div className="playlist-track-toolbar__stats">
                  <strong className="playlist-track-toolbar__count">{selected.tracks?.length || 0} tracks</strong>
                  <span className="muted">Total duration: {formatDuration(totalDurationSeconds)}</span>
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

              <div className="track-list">
                <div className="track-list__header">
                  <span className="track-list__header-handle" aria-hidden="true"></span>
                  <span className="track-list__header-num">#</span>
                  <span className="track-list__header-art" aria-hidden="true"></span>
                  <span className="track-list__header-track">Track</span>
                  <span className="track-list__header-badge"></span>
                  <span className="track-list__header-duration">Duration</span>
                  <span className="track-list__header-remove" aria-hidden="true"></span>
                </div>

                {(selected.tracks || []).map((t, i) => (
                  <div
                    key={t.id}
                    ref={(node) => {
                      if (node) trackRowRefs.current.set(t.id, node);
                      else trackRowRefs.current.delete(t.id);
                    }}
                    draggable
                    onDragStart={() => handleTrackDragStart(t.id)}
                    onDragOver={(e) => handleTrackDragOver(e, t.id)}
                    onDrop={(e) => handleTrackDrop(e, t.id)}
                    onDragEnd={handleTrackDragEnd}
                    className={`track-row ${dragTrackId === t.id ? 'is-dragging' : ''} ${dragOverTrackId === t.id && dragTrackId !== t.id ? 'is-drag-over' : ''}`}
                  >
                    <span className="track-row__handle" title="Drag to reorder">⋮⋮</span>
                    <span className="track-row__num">{String(i + 1).padStart(2, '0')}</span>
                    <span className="track-row__art">
                      {t.song?.id ? (
                        <img
                          src={api.getSongArtworkUrl(t.song.id)}
                          alt=""
                          onError={(e) => { e.currentTarget.style.display = 'none'; e.currentTarget.nextSibling.style.display = 'flex'; }}
                        />
                      ) : null}
                      <span className="track-row__art-fallback" style={{ display: t.song?.id ? 'none' : 'flex' }}>
                        <Music size={16}/>
                      </span>
                    </span>
                    <span className="track-row__main">
                      <strong className="track-row__title" title={t.song?.title || `Song #${t.song_id}`}>{t.song?.title || `Song #${t.song_id}`}</strong>
                      <small className="track-row__artist">{t.song?.artist || '—'}</small>
                    </span>
                    <span className="track-row__badge">SONG</span>
                    <span className="track-row__duration">{formatDuration(t.song?.duration)}</span>
                    <button className="track-row__remove" onClick={() => removeTrack(t.id)} title="Remove track" disabled={busy}><X size={14}/></button>
                  </div>
                ))}
                {!selected.tracks?.length && (
                  <div className="track-list__empty">No tracks in this playlist. Click <strong>Add Tracks</strong> to select songs.</div>
                )}
              </div>
            </> : (
              <div className="playlist-detail__empty">
                <ListMusic size={28}/>
                <span>Select a playlist to view and manage its tracks.</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

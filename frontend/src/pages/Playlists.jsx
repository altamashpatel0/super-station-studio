import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ListMusic, Plus, Trash2, Play, RefreshCw, X, Check, CheckSquare, Square, Search, ListPlus, MoreVertical, Pencil, Music, Megaphone } from 'lucide-react';
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
  const [promos, setPromos] = useState([]);
  const [selectedSongIds, setSelectedSongIds] = useState(new Map());
  const [selectedPromoIds, setSelectedPromoIds] = useState(new Map());
  const [pickerMode, setPickerMode] = useState(null);
  const [trackSearch, setTrackSearch] = useState('');
  const [showTrackPicker, setShowTrackPicker] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [busy, setBusy] = useState(false);
  const [dragTrackId, setDragTrackId] = useState(null);
  const [dragOverTrackId, setDragOverTrackId] = useState(null);
  const [openMenuId, setOpenMenuId] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newPlaylistName, setNewPlaylistName] = useState('');
  const [newPlaylistDescription, setNewPlaylistDescription] = useState('');

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
      const [rows, library, promoRows] = await Promise.all([
        api.listPlaylists(),
        api.listSongs({ limit: 500 }),
        api.listAssets({ asset_type: 'PROMO', enabled_only: false }),
      ]);
      setItems(Array.isArray(rows) ? rows : rows?.items || []);
      setSongs(Array.isArray(library) ? library : library?.items || []);
      setPromos(Array.isArray(promoRows) ? promoRows : promoRows?.items || []);
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
      setSelectedSongIds(new Map());
      setSelectedPromoIds(new Map());
      setTrackSearch('');
      setPickerMode(null);
      setShowTrackPicker(false);
    } catch (e) { setError(e.message); }
  };

  const openCreateModal = () => {
    setError('');
    setNewPlaylistName('');
    setNewPlaylistDescription('');
    setShowCreateModal(true);
  };

  const closeCreateModal = () => {
    if (busy) return;
    setShowCreateModal(false);
    setNewPlaylistName('');
    setNewPlaylistDescription('');
  };

  const create = async (e) => {
    e?.preventDefault();
    const name = newPlaylistName.trim();
    const description = newPlaylistDescription.trim();

    if (!name) {
      setError('Please enter a playlist name.');
      return;
    }

    try {
      setBusy(true);
      setError('');
      setInfo('');

      const created = await api.createPlaylist(name, description);
      const rows = await api.listPlaylists();
      const nextItems = Array.isArray(rows) ? rows : rows?.items || [];
      setItems(nextItems);

      const createdId = created?.id ?? created?.playlist?.id;
      const newId = createdId ?? nextItems.find(
        (p) => String(p.name).toLowerCase() === name.toLowerCase()
      )?.id;

      if (newId != null) {
        setSelected(await api.getPlaylist(newId));
      }

      setShowCreateModal(false);
      setNewPlaylistName('');
      setNewPlaylistDescription('');
      setInfo(`Playlist "${name}" created successfully.`);
      setTimeout(() => setInfo(''), 2500);
    } catch (e) {
      setError(e?.message || 'Unable to create playlist.');
    } finally {
      setBusy(false);
    }
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

  // Map stores songId -> number of occurrences to add.
  const availableSongs = useMemo(() => {
    const q = trackSearch.trim().toLowerCase();
    return songs
      .filter(s => s.enabled !== false)
      .filter(s => !q || `${s.title || s.name || ''} ${s.artist || ''}`.toLowerCase().includes(q));
  }, [songs, trackSearch]);

  const availablePromos = useMemo(() => {
    const q = trackSearch.trim().toLowerCase();
    return promos
      .filter(p => p.enabled !== false)
      .filter(p => !q || `${p.name || ''} ${p.category || ''} ${p.description || ''}`.toLowerCase().includes(q));
  }, [promos, trackSearch]);

  const getSelectedCount = (id) => selectedSongIds.get(Number(id)) || 0;

  const getSelectedPromoCount = (id) => selectedPromoIds.get(Number(id)) || 0;

  const toggleSong = (id) => {
    setSelectedSongIds(prev => {
      const next = new Map(prev);
      const songId = Number(id);
      next.set(songId, (next.get(songId) || 0) + 1);
      return next;
    });
  };

  const decrementSong = (id) => {
    setSelectedSongIds(prev => {
      const next = new Map(prev);
      const songId = Number(id);
      const count = next.get(songId) || 0;
      if (count <= 1) next.delete(songId);
      else next.set(songId, count - 1);
      return next;
    });
  };

  const togglePromo = (id) => {
    setSelectedPromoIds(prev => {
      const next = new Map(prev);
      const promoId = Number(id);
      next.set(promoId, (next.get(promoId) || 0) + 1);
      return next;
    });
  };

  const decrementPromo = (id) => {
    setSelectedPromoIds(prev => {
      const next = new Map(prev);
      const promoId = Number(id);
      const count = next.get(promoId) || 0;
      if (count <= 1) next.delete(promoId);
      else next.set(promoId, count - 1);
      return next;
    });
  };

  const selectAllVisible = () => {
    if (pickerMode === 'promos') {
      setSelectedPromoIds(prev => {
        const next = new Map(prev);
        availablePromos.forEach(p => { if (!next.has(Number(p.id))) next.set(Number(p.id), 1); });
        return next;
      });
    } else {
      setSelectedSongIds(prev => {
        const next = new Map(prev);
        availableSongs.forEach(s => { if (!next.has(Number(s.id))) next.set(Number(s.id), 1); });
        return next;
      });
    }
  };

  const clearSelection = () => { setSelectedSongIds(new Map()); setSelectedPromoIds(new Map()); };

  const selectedTrackCount = useMemo(
    () => pickerMode === 'promos'
      ? Array.from(selectedPromoIds.values()).reduce((sum, count) => sum + count, 0)
      : Array.from(selectedSongIds.values()).reduce((sum, count) => sum + count, 0),
    [selectedSongIds, selectedPromoIds, pickerMode]
  );

  const activePickerItems = pickerMode === 'promos' ? availablePromos : availableSongs;
  const activeSelectionMap = pickerMode === 'promos' ? selectedPromoIds : selectedSongIds;
  const allVisibleSelected = activePickerItems.length > 0 &&
    activePickerItems.every(item => activeSelectionMap.has(Number(item.id)));

  const addSelectedTracks = async () => {
    if (!selected?.id || selectedTrackCount === 0) return;
    try {
      setBusy(true);
      setError('');
      let added = 0;
      if (pickerMode === 'promos') {
        for (const [id, count] of selectedPromoIds.entries()) {
          for (let i = 0; i < count; i += 1) {
            await api.addAssetToPlaylist(selected.id, id);
            added += 1;
          }
        }
      } else {
        for (const [id, count] of selectedSongIds.entries()) {
          for (let i = 0; i < count; i += 1) {
            await api.addTrackToPlaylist(selected.id, id);
            added += 1;
          }
        }
      }
      setSelected(await api.getPlaylist(selected.id));
      clearSelection();
      setPickerMode(null);
      setShowTrackPicker(false);
      await load();
      setInfo(`${added} ${pickerMode === 'promos' ? 'promo' : 'track'}${added === 1 ? '' : 's'} added to playlist.`);
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
    () => (selected?.tracks || []).reduce((sum, t) => sum + (Number(t.song?.duration ?? t.asset?.duration) || 0), 0),
    [selected]
  );

  return (
    <div className="pageshell">
      <PageHeader title="Playlists" subtitle={`${items.length} playlists`} actions={<>
        <Button type="button" variant="primary" icon={Plus} onClick={(e) => { e.preventDefault(); e.stopPropagation(); openCreateModal(); }} disabled={busy}>New Playlist</Button>
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
                <div className="playlist-track-toolbar__actions">
                  <Button icon={ListPlus} onClick={() => { setPickerMode(v => v === 'songs' ? null : 'songs'); setShowTrackPicker(true); setTrackSearch(''); }} disabled={busy}>
                    {pickerMode === 'songs' ? 'Close Track Selector' : 'Add Tracks'}
                  </Button>
                  <Button icon={Megaphone} onClick={() => { setPickerMode(v => v === 'promos' ? null : 'promos'); setShowTrackPicker(true); setTrackSearch(''); }} disabled={busy}>
                    {pickerMode === 'promos' ? 'Close Promo Selector' : 'Add Promo'}
                  </Button>
                </div>
              </div>

              {showTrackPicker && pickerMode && (
                <div className={`track-picker track-picker--${pickerMode}`}>
                  <div className="track-picker__top">
                    <div className="track-picker__title">
                      {pickerMode === 'promos' ? <Megaphone size={17}/> : <ListPlus size={17}/>}
                      <div><strong>{pickerMode === 'promos' ? 'Select promos' : 'Select tracks'}</strong><small>{pickerMode === 'promos' ? 'Choose promos to insert into the playlist.' : 'Choose one, several, or all available tracks.'}</small></div>
                    </div>
                    <div className="track-picker__selection"><strong>{selectedTrackCount}</strong> occurrence{selectedTrackCount === 1 ? '' : 's'} selected</div>
                  </div>

                  <div className="track-picker__controls">
                    <label className="track-search"><Search size={15}/><input value={trackSearch} onChange={e => setTrackSearch(e.target.value)} placeholder={pickerMode === 'promos' ? 'Search promo name or category...' : 'Search title or artist...'} /></label>
                    <button className="picker-action" onClick={allVisibleSelected ? clearSelection : selectAllVisible} disabled={!activePickerItems.length}>
                      {allVisibleSelected ? <><CheckSquare size={15}/> Clear visible</> : <><Square size={15}/> Select all visible</>}
                    </button>
                    {selectedTrackCount > 0 && <button className="picker-action picker-action--ghost" onClick={clearSelection}>Clear selection</button>}
                  </div>

                  <div className="track-picker__list">
                    {pickerMode === 'promos' ? availablePromos.map(promo => {
                      const count = getSelectedPromoCount(promo.id);
                      return (
                        <div key={promo.id} className={`track-option track-option--promo ${count > 0 ? 'is-selected' : ''}`}>
                          <span className="track-option__check">{count > 0 ? <Check size={15}/> : <Megaphone size={13}/>}</span>
                          <span className="track-option__main" onClick={() => togglePromo(promo.id)} style={{ cursor: 'pointer' }}>
                            <strong>{promo.name || `Promo #${promo.id}`}</strong>
                            <small>{promo.category || 'Promo'}</small>
                          </span>
                          <span className="track-option__duration">{formatDuration(promo.duration)}</span>
                          <button type="button" className="picker-action" onClick={() => decrementPromo(promo.id)} disabled={count === 0 || busy}>−</button>
                          <span style={{ minWidth: 24, textAlign: 'center', fontWeight: 700 }}>{count}</span>
                          <button type="button" className="picker-action" onClick={() => togglePromo(promo.id)} disabled={busy}>+</button>
                        </div>
                      );
                    }) : availableSongs.map(song => {
                      const count = getSelectedCount(song.id);
                      return (
                        <div key={song.id} className={`track-option ${count > 0 ? 'is-selected' : ''}`}>
                          <span className="track-option__check">{count > 0 ? <Check size={15}/> : null}</span>
                          <span className="track-option__main" onClick={() => toggleSong(song.id)} style={{ cursor: 'pointer' }}>
                            <strong>{song.title || song.name || `Song #${song.id}`}</strong>
                            <small>{song.artist || 'Unknown artist'}</small>
                          </span>
                          <span className="track-option__duration">{formatDuration(song.duration)}</span>
                          <button type="button" className="picker-action" onClick={() => decrementSong(song.id)} disabled={count === 0 || busy}>−</button>
                          <span style={{ minWidth: 24, textAlign: 'center', fontWeight: 700 }}>{count}</span>
                          <button type="button" className="picker-action" onClick={() => toggleSong(song.id)} disabled={busy}>+</button>
                        </div>
                      );
                    })}
                    {!activePickerItems.length && <div className="track-picker__empty">{pickerMode === 'promos' ? 'No promos available. Import promos from the Promos page first.' : 'No available tracks match your search.'}</div>}
                  </div>

                  <div className="track-picker__footer">
                    <span>{selectedTrackCount ? `${selectedTrackCount} ${pickerMode === 'promos' ? 'promo' : 'track'}${selectedTrackCount === 1 ? '' : 's'} ready to add` : `Select ${pickerMode === 'promos' ? 'promos' : 'tracks'} above`}</span>
                    <Button icon={Plus} variant="primary" onClick={addSelectedTracks} disabled={!selectedTrackCount || busy}>
                      Add {selectedTrackCount || ''} {pickerMode === 'promos' ? 'Promo' : 'Selected Track'}{selectedTrackCount === 1 ? '' : 's'}
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

                {(selected.tracks || []).map((t, i) => {
                  const isPromo = t.track_type === 'PROMO' || t.asset_id != null || t.asset;
                  return (
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
                    className={`track-row ${isPromo ? 'track-row--promo' : ''} ${dragTrackId === t.id ? 'is-dragging' : ''} ${dragOverTrackId === t.id && dragTrackId !== t.id ? 'is-drag-over' : ''}`}
                  >
                    <span className="track-row__handle" title="Drag to reorder">⋮⋮</span>
                    <span className="track-row__num">{String(i + 1).padStart(2, '0')}</span>
                    <span className="track-row__art">
                      {isPromo ? (
                        <span className="track-row__art-fallback track-row__art-fallback--promo"><Megaphone size={16}/></span>
                      ) : (
                        <>
                          {t.song?.id ? <img src={api.getSongArtworkUrl(t.song.id)} alt="" onError={(e) => { e.currentTarget.style.display = 'none'; e.currentTarget.nextSibling.style.display = 'flex'; }} /> : null}
                          <span className="track-row__art-fallback" style={{ display: t.song?.id ? 'none' : 'flex' }}><Music size={16}/></span>
                        </>
                      )}
                    </span>
                    <span className="track-row__main">
                      <strong className="track-row__title" title={isPromo ? t.asset?.name : (t.song?.title || `Song #${t.song_id}`)}>{isPromo ? (t.asset?.name || `Promo #${t.asset_id}`) : (t.song?.title || `Song #${t.song_id}`)}</strong>
                      <small className="track-row__artist">{isPromo ? (t.asset?.category || 'Promo') : (t.song?.artist || '—')}</small>
                    </span>
                    <span className={`track-row__badge ${isPromo ? 'track-row__badge--promo' : ''}`}>{isPromo ? 'PROMO' : 'SONG'}</span>
                    <span className="track-row__duration">{formatDuration(isPromo ? t.asset?.duration : t.song?.duration)}</span>
                    <button className="track-row__remove" onClick={() => removeTrack(t.id)} title="Remove track" disabled={busy}><X size={14}/></button>
                  </div>
                  );
                })}
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
      {showCreateModal && (
        <div className="playlist-modal__backdrop" role="presentation"
          onMouseDown={(e) => { if (e.target === e.currentTarget) closeCreateModal(); }}>
          <form className="playlist-modal" onSubmit={create} role="dialog" aria-modal="true" aria-labelledby="create-playlist-title">
            <div className="playlist-modal__header">
              <div>
                <h2 id="create-playlist-title">Create playlist</h2>
                <p>Add a name and optional description for your new playlist.</p>
              </div>
              <button type="button" className="iconbtn" onClick={closeCreateModal} disabled={busy} aria-label="Close">
                <X size={18} />
              </button>
            </div>
            <div className="playlist-modal__body">
              <label className="playlist-modal__field">
                <span>Playlist name <b>*</b></span>
                <input autoFocus value={newPlaylistName}
                  onChange={(e) => setNewPlaylistName(e.target.value)}
                  placeholder="e.g. Morning Drive" maxLength={120} disabled={busy} />
              </label>
              <label className="playlist-modal__field">
                <span>Description <em>Optional</em></span>
                <textarea value={newPlaylistDescription}
                  onChange={(e) => setNewPlaylistDescription(e.target.value)}
                  placeholder="What's this playlist for?" maxLength={500} rows={3} disabled={busy} />
              </label>
            </div>
            <div className="playlist-modal__footer">
              <Button type="button" onClick={closeCreateModal} disabled={busy}>Cancel</Button>
              <Button type="submit" variant="primary" icon={Plus} disabled={busy || !newPlaylistName.trim()}>
                {busy ? 'Creating…' : 'Create Playlist'}
              </Button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

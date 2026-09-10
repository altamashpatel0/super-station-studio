import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FolderOpen, Play, RefreshCw, Search, Trash2, Power, Megaphone } from 'lucide-react';
import { api } from '../api';
import './Promos.css';

const toArray = (value) => {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.items)) return value.items;
  if (Array.isArray(value?.data)) return value.data;
  return [];
};

const formatDuration = (value) => {
  const total = Math.max(0, Math.round(Number(value) || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
};

export default function Promos() {
  const [promos, setPromos] = useState([]);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('ALL');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const inputRef = useRef(null);
  const mountedRef = useRef(true);

  const showMessage = (text) => {
    if (!mountedRef.current) return;
    setMessage(text);
    window.clearTimeout(showMessage.timer);
    showMessage.timer = window.setTimeout(() => {
      if (mountedRef.current) setMessage('');
    }, 3500);
  };

  const loadPromos = async () => {
    try {
      setError('');
      const result = await api.listAssets({ asset_type: 'PROMO', enabled_only: false });
      if (mountedRef.current) setPromos(toArray(result));
    } catch (err) {
      if (mountedRef.current) {
        setPromos([]);
        setError(err?.message || 'Unable to load promos.');
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    loadPromos();
    return () => {
      mountedRef.current = false;
      window.clearTimeout(showMessage.timer);
    };
  }, []);

  const categories = useMemo(() => {
    const values = promos
      .map((item) => String(item?.category || '').trim())
      .filter(Boolean);
    return ['ALL', ...Array.from(new Set(values)).sort((a, b) => a.localeCompare(b))];
  }, [promos]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return promos.filter((item) => {
      const haystack = [item?.name, item?.category, item?.description, item?.id]
        .filter((v) => v !== undefined && v !== null)
        .join(' ')
        .toLowerCase();
      return (!q || haystack.includes(q)) &&
        (category === 'ALL' || String(item?.category || '') === category);
    });
  }, [promos, search, category]);

  const importFolder = async (event) => {
    const files = Array.from(event.target.files || []).filter((file) => /\.(mp3|wav)$/i.test(file.name));
    event.target.value = '';

    if (!files.length) {
      setError('No MP3/WAV files were found in the selected folder.');
      return;
    }

    setBusy(true);
    setError('');
    let imported = 0;
    let failed = 0;

    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      setMessage(`Importing ${index + 1}/${files.length}: ${file.name}`);
      try {
        await api.uploadAsset(file, {
          name: file.name.replace(/\.[^.]+$/, ''),
          asset_type: 'PROMO',
          category: 'Promo',
          description: '',
          priority: 0,
          cooldown_seconds: 0,
        });
        imported += 1;
      } catch (err) {
        failed += 1;
        setError(`${file.name}: ${err?.message || 'Import failed.'}`);
      }
    }

    await loadPromos();
    setBusy(false);
    showMessage(`${imported} promo${imported === 1 ? '' : 's'} imported${failed ? ` · ${failed} failed` : ''}.`);
  };

  const playPromo = async (promo) => {
    try {
      setError('');
      await api.playAsset(promo.id);
      showMessage(`Playing: ${promo.name}`);
    } catch (err) {
      setError(err?.message || 'Unable to play promo.');
    }
  };

  const togglePromo = async (promo) => {
    try {
      setBusy(true);
      setError('');
      if (promo.enabled) await api.disableAsset(promo.id);
      else await api.enableAsset(promo.id);
      await loadPromos();
      showMessage(`${promo.name} is now ${promo.enabled ? 'OFF' : 'ON'}.`);
    } catch (err) {
      setError(err?.message || 'Unable to change promo status.');
    } finally {
      setBusy(false);
    }
  };

  const deletePromo = async (promo) => {
    if (!window.confirm(`Delete promo “${promo.name}”?\n\nThis removes it from the Promo library.`)) return;
    try {
      setBusy(true);
      setError('');
      await api.deleteAsset(promo.id);
      await loadPromos();
      showMessage('Promo deleted.');
    } catch (err) {
      setError(err?.message || 'Unable to delete promo.');
    } finally {
      setBusy(false);
    }
  };

  const deleteAllPromos = async () => {
    if (!promos.length || busy) return;
    if (!window.confirm(`Delete all ${promos.length} promos?\n\nThis removes every promo from the Promo library.`)) return;
    try {
      setBusy(true);
      setError('');
      let failed = 0;
      for (const promo of promos) {
        try { await api.deleteAsset(promo.id); } catch { failed += 1; }
      }
      const deleted = promos.length - failed;
      await loadPromos();
      showMessage(failed ? `Deleted ${deleted} promo${deleted === 1 ? '' : 's'} · ${failed} failed.` : 'All promos deleted.');
    } catch (err) {
      setError(err?.message || 'Unable to delete all promos.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="promos-page">
      <header className="promos-header">
        <div>
          <h1>Promos</h1>
          <p>{promos.length} promo{promos.length === 1 ? '' : 's'} in station library</p>
        </div>
        <div className="promos-header-actions">
          <input
            ref={inputRef}
            className="promos-hidden-input"
            type="file"
            accept=".mp3,.wav,audio/mpeg,audio/wav"
            webkitdirectory=""
            directory=""
            multiple
            onChange={importFolder}
          />
          <button type="button" className="promo-btn promo-btn-primary" onClick={() => inputRef.current?.click()} disabled={busy}>
            <FolderOpen size={16} /> {busy ? 'Working…' : 'Import Promo Folder'}
          </button>
          <button type="button" className="promo-btn" onClick={loadPromos} disabled={busy || loading}>
            <RefreshCw size={16} className={loading ? 'promo-spin' : ''} /> Refresh
          </button>
           {promos.length > 0 && (
             <button type="button" className="promo-btn promo-btn-danger" onClick={deleteAllPromos} disabled={busy || loading} title="Delete all promos">
               <Trash2 size={16} /> Delete All
             </button>
           )}
        </div>
      </header>

      {error && <div className="promo-alert promo-alert-error">{error}</div>}
      {message && <div className="promo-alert promo-alert-info">{message}</div>}

      <div className="promo-toolbar">
        <label className="promo-search-box">
          <Search size={16} />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search promos…" />
        </label>
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="promo-category">
          {categories.map((item) => <option key={item} value={item}>{item === 'ALL' ? 'All categories' : item}</option>)}
        </select>
      </div>

      <div className="promo-count-row">
        <strong>{filtered.length}</strong> {filtered.length === 1 ? 'promo' : 'promos'}
        <span>TYPE: PROMO</span>
      </div>

      {loading ? (
        <div className="promo-empty"><RefreshCw size={28} className="promo-spin" /><strong>Loading promos…</strong></div>
      ) : filtered.length === 0 ? (
        <div className="promo-empty">
          <Megaphone size={34} />
          <strong>{promos.length ? 'No promos match your search.' : 'No promos yet.'}</strong>
          <span>Use <b>Import Promo Folder</b> to add MP3/WAV promo files.</span>
        </div>
      ) : (
        <div className="promo-grid">
          {filtered.map((promo) => {
            const enabled = promo.enabled !== false;
            return (
              <article className={`promo-card${enabled ? '' : ' promo-card-disabled'}`} key={promo.id}>
                <div className="promo-icon"><Megaphone size={21} /><small>PROMO</small></div>
                <div className="promo-main">
                  <strong title={promo.name}>{promo.name || `Promo #${promo.id}`}</strong>
                  <span>{promo.category || 'Promo'}{promo.description ? ` · ${promo.description}` : ''}</span>
                </div>
                <div className="promo-meta">
                  <span>{formatDuration(promo.duration)}</span>
                  <b className={enabled ? 'promo-ready' : 'promo-off'}>{enabled ? 'READY' : 'OFF'}</b>
                </div>
                <div className="promo-actions">
                  <button type="button" className="promo-small promo-play" onClick={() => playPromo(promo)} disabled={!enabled || busy}>
                    <Play size={13} fill="currentColor" /> Play
                  </button>
                  <button type="button" className="promo-small" onClick={() => togglePromo(promo)} disabled={busy}>
                    <Power size={13} /> {enabled ? 'Off' : 'On'}
                  </button>
                  <button type="button" className="promo-small promo-delete" onClick={() => deletePromo(promo)} disabled={busy} title="Delete promo">
                    <Trash2 size={13} />
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

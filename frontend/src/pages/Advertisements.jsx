import { useEffect, useMemo, useState } from 'react';
import { Megaphone, Plus, Play, RefreshCw, Search, Trash2, Power, X } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import { api } from '../api';
import './Assets.css';

const fmt = (s) => { const n = Math.max(0, Math.round(Number(s || 0))); return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`; };
const arr = (v) => Array.isArray(v) ? v : (Array.isArray(v?.items) ? v.items : []);

export default function Advertisements({ player }) {
  const [items, setItems] = useState([]), [query, setQuery] = useState(''), [category, setCategory] = useState('ALL'), [idQuery, setIdQuery] = useState('');
  const [file, setFile] = useState(null), [showForm, setShowForm] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [form, setForm] = useState({ name:'', category:'', description:'', priority:0, cooldown_seconds:0 });

  const load = async () => { try { setError(''); setItems(arr(await api.listAssets({ asset_type:'ADVERTISEMENT' }))); } catch(e) { setError(e.message || 'Unable to load advertisements.'); } };
  useEffect(() => { load(); }, []);

  const categories = useMemo(() => ['ALL', ...Array.from(new Set(items.map(x => x.category).filter(Boolean))).sort()], [items]);
  const filtered = useMemo(() => { const q=query.trim().toLowerCase(); const id=idQuery.trim(); return items.filter(a => (!q || `${a.name} ${a.category||''} ${a.description||''} ${a.id}`.toLowerCase().includes(q)) && (category==='ALL' || a.category===category) && (!id || String(a.id)===id)); }, [items,query,category,idQuery]);
  const nowAsset = player?.nowPlaying?.type === 'ADVERTISEMENT' ? player.nowPlaying : null;

  const chooseFile = (e) => { const f=e.target.files?.[0] || null; e.target.value=''; setFile(f); if(f && !form.name) setForm(v=>({...v,name:f.name.replace(/\.[^.]+$/,'')})); setShowForm(Boolean(f)); };
  const upload = async (e) => { e.preventDefault(); if(!file) return; try { setBusy(true); setError(''); await api.uploadAsset(file,{...form,asset_type:'ADVERTISEMENT'}); setFile(null); setShowForm(false); setForm({name:'',category:'',description:'',priority:0,cooldown_seconds:0}); await load(); } catch(e){ setError(e.message || 'Advertisement upload failed.'); } finally{setBusy(false);} };
  const play = async (id) => { try { setError(''); if(player?.playAsset) await player.playAsset(id); else await api.playAsset(id); } catch(e){setError(e.message || 'Unable to play advertisement.');} };
  const toggle = async (a) => { try { setBusy(true); await (a.enabled ? api.disableAsset(a.id) : api.enableAsset(a.id)); await load(); } catch(e){setError(e.message);} finally{setBusy(false);} };
  const remove = async (id) => { if(!window.confirm('Delete this advertisement?')) return; try{setBusy(true);await api.deleteAsset(id);await load();}catch(e){setError(e.message);}finally{setBusy(false);} };

  return <div className="pageshell">
    <PageHeader title="Advertisements" subtitle={`${items.length} real assets in station library`} actions={<>
      <input id="ad-file" type="file" accept=".mp3,.wav,audio/mpeg,audio/wav" hidden onChange={chooseFile}/>
      <Button variant="primary" icon={Plus} onClick={()=>document.getElementById('ad-file')?.click()} disabled={busy}>New Advertisement</Button>
      <Button icon={RefreshCw} onClick={load} disabled={busy}>Refresh</Button>
    </>}/>
    <div className="pageshell__body">
      {error && <div className="asset-error">{error}</div>}
      {nowAsset && <div className="asset-now-playing"><span className="asset-now-playing__dot"/><span>ON AIR · Advertisement</span><strong>{nowAsset.title}</strong><span className="mono">Asset #{nowAsset.id}</span></div>}
      {showForm && <form className="asset-form" onSubmit={upload}>
        <div className="asset-field"><label>Audio file</label><div className="asset-chip asset-chip--id"><Megaphone size={12}/>{file?.name}</div></div>
        <div className="asset-field"><label>Name</label><input required value={form.name} onChange={e=>setForm(v=>({...v,name:e.target.value}))}/></div>
        <div className="asset-field"><label>Category</label><input value={form.category} placeholder="e.g. Commercial, Sponsor" onChange={e=>setForm(v=>({...v,category:e.target.value}))}/></div>
        <div className="asset-field"><label>Priority</label><input type="number" min="0" value={form.priority} onChange={e=>setForm(v=>({...v,priority:Number(e.target.value)||0}))}/></div>
        <div className="asset-field"><label>Cooldown (seconds)</label><input type="number" min="0" value={form.cooldown_seconds} onChange={e=>setForm(v=>({...v,cooldown_seconds:Number(e.target.value)||0}))}/></div>
        <div className="asset-field asset-form__full"><label>Description</label><textarea value={form.description} onChange={e=>setForm(v=>({...v,description:e.target.value}))}/></div>
        <div className="asset-form__actions"><Button icon={X} type="button" onClick={()=>{setShowForm(false);setFile(null)}}>Cancel</Button><Button variant="primary" type="submit" disabled={busy}>{busy?'Uploading…':'Upload Advertisement'}</Button></div>
      </form>}
      <div className="asset-page__toolbar">
        <div className="asset-search"><Search size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search name, category, description or asset ID…"/></div>
        <input className="asset-filter" value={idQuery} onChange={e=>setIdQuery(e.target.value.replace(/\D/g,''))} placeholder="Asset ID" inputMode="numeric"/>
        <select className="asset-filter" value={category} onChange={e=>setCategory(e.target.value)}>{categories.map(c=><option key={c} value={c}>{c==='ALL'?'All categories':c}</option>)}</select>
      </div>
      <div className="asset-summary"><span className="asset-summary__count">Showing <strong>{filtered.length}</strong> of {items.length}</span><span className="asset-chip">SEARCH: {query || '—'}</span><span className="asset-chip asset-chip--priority">PRIORITY: sorted by backend</span></div>
      <div className="asset-table-wrap"><table className="datatable asset-table"><thead><tr><th>Advertisement</th><th>Metadata</th><th>Duration</th><th>Status</th><th>Actions</th></tr></thead><tbody>
        {filtered.map(a=><tr key={a.id}><td><div className="asset-name"><div className="asset-icon asset-icon--ad"><Megaphone size={15}/></div><div><div className="asset-name__title">{a.name}</div><div className="asset-name__sub">{a.description || 'No description'}</div></div></div></td><td><div className="asset-meta"><span className="asset-chip asset-chip--id">ID #{a.id}</span><span className="asset-chip asset-chip--priority">PRI {a.priority ?? 0}</span><span className="asset-chip">{a.category || 'Uncategorised'}</span><span className="asset-chip">CD {a.cooldown_seconds ?? 0}s</span></div></td><td className="mono">{fmt(a.duration)}</td><td><span className={`badge ${a.enabled?'badge--active':'badge--error'}`}>{a.enabled?'ENABLED':'DISABLED'}</span></td><td><div className="asset-actions"><button className="asset-action asset-action--primary" onClick={()=>play(a.id)} disabled={!a.enabled}><Play size={13} fill="currentColor"/>Play</button><button className="asset-action" onClick={()=>toggle(a)} disabled={busy}><Power size={13}/>{a.enabled?'Off':'On'}</button><button className="asset-action asset-action--danger" onClick={()=>remove(a.id)} disabled={busy}><Trash2 size={13}/></button></div></td></tr>)}
        {!filtered.length && <tr><td colSpan="5"><div className="asset-empty"><strong>{items.length ? 'No advertisements match your filters.' : 'No advertisements yet.'}</strong>{!items.length && 'Upload an MP3/WAV advertisement to add a real station asset.'}</div></td></tr>}
      </tbody></table></div>
    </div>
  </div>;
}

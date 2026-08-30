import { useEffect, useState } from 'react';
import { Radio, Settings, ChevronDown, Moon, Sun, Bell } from 'lucide-react';
import './TopBar.css';
function useClock(){const [now,setNow]=useState(new Date());useEffect(()=>{const id=setInterval(()=>setNow(new Date()),1000);return()=>clearInterval(id)},[]);return now}
export default function TopBar({onAir,onNavigate,theme,onToggleTheme}){
 const now=useClock();
 const time=now.toLocaleTimeString('en-US',{hour12:true,hour:'2-digit',minute:'2-digit',second:'2-digit'});
 const date=now.toLocaleDateString('en-US',{weekday:'long',month:'short',day:'numeric',year:'numeric'});
 return <header className="topbar">
  <div className="topbar__centerclock"><div className="topbar__watch">◷</div><div><div className="topbar__clock-time mono">{time}</div><div className="topbar__clock-date">{date}</div></div></div>
  <div className="topbar__right">
   <button className={`onair ${onAir?'onair--live':'onair--off'}`}><span className="onair__dot"/>{onAir?'ON AIR':'STANDBY'}</button>
   <button className="topbar__icon-btn" title={theme==='dark'?'Light theme':'Dark theme'} onClick={onToggleTheme}>{theme==='dark'?<Sun size={18}/>:<Moon size={18}/>}</button>
   <button className="topbar__icon-btn topbar__notify" title="Notifications"><Bell size={18}/><span>3</span></button>
   <button className="topbar__icon-btn" title="Broadcast output"><Radio size={18}/></button>
   <button className="topbar__icon-btn" title="Settings" onClick={()=>onNavigate('settings')}><Settings size={18}/></button>
   <button className="topbar__user"><span className="topbar__user-avatar">OP</span><span className="topbar__user-copy"><b>Operator</b><small>Station Admin</small></span><ChevronDown size={14}/></button>
  </div>
 </header>
}

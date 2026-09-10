import { useEffect, useMemo, useState } from "react";
import { CalendarClock, CheckCircle2, Clock3, History, ListChecks, Plus, RefreshCw, ScrollText } from "lucide-react";
import Scheduler from "./Scheduler";
import Logs from "./Logs";
import { api } from "../api";
import Button from "../components/common/Button";
import "./ScheduleCenter.css";

function parseClock(value) {
  if (!value) return null;
  const m = String(value).trim().match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?$/i);
  if (!m) return null;
  let hour = Number(m[1]);
  const minute = Number(m[2]);
  const second = Number(m[3] || 0);
  if (m[4]) { if (hour === 12) hour = 0; if (m[4].toUpperCase() === "PM") hour += 12; }
  if (hour > 23 || minute > 59 || second > 59) return null;
  return { hour, minute, second };
}

function dateKey(date) { const d = new Date(date); return [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),String(d.getDate()).padStart(2,"0")].join("-"); }
function occurrenceFor(schedule, day) {
  if (!schedule) return null;
  const startClock=parseClock(schedule.start_time), endClock=parseClock(schedule.end_time);
  if (!startClock || !endClock) return null;
  const key=dateKey(day);
  if (schedule.start_date && key<String(schedule.start_date).slice(0,10)) return null;
  if (schedule.end_date && key>String(schedule.end_date).slice(0,10)) return null;
  const schedulerDay=(day.getDay()+6)%7;
  const days=Array.isArray(schedule.days_of_week)?schedule.days_of_week.map(Number):[];
  if (days.length && !days.includes(schedulerDay)) return null;
  const start=new Date(day); start.setHours(startClock.hour,startClock.minute,startClock.second,0);
  const end=new Date(day); end.setHours(endClock.hour,endClock.minute,endClock.second,0);
  if (end<=start) return null;
  return {schedule,start,end};
}
function formatTime(date){return date.toLocaleTimeString([], {hour:"numeric",minute:"2-digit"});}
function formatDate(date){return date.toLocaleDateString([], {weekday:"long",day:"2-digit",month:"long",year:"numeric"});}
function formatCountdown(ms){const s=Math.max(0,Math.ceil(ms/1000));const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;return h?`${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`:`${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;}
function targetLabel(type){return ({SONG:"Song",PLAYLIST:"Playlist",ADVERTISEMENT:"Advertisement",JINGLE:"Jingle",PROMO:"Promo"}[type]||type||"Schedule");}

export default function ScheduleCenter({ onNavigate }) {
  const [tab,setTab]=useState("scheduler");
  const [day,setDay]=useState("today");
  const [schedules,setSchedules]=useState([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [clock,setClock]=useState(()=>new Date());
  const [createRequest,setCreateRequest]=useState(0);

  const load=async()=>{setLoading(true);setError("");try{const rows=await api.listSchedules();setSchedules(Array.isArray(rows)?rows:[]);}catch(e){setError(e?.message||"Could not load schedules.");}finally{setLoading(false);}};
  useEffect(()=>{load();},[]);
  useEffect(()=>{const t=setInterval(()=>setClock(new Date()),1000);return()=>clearInterval(t);},[]);
  useEffect(()=>{const handler=()=>{setTab("scheduler");load();};window.addEventListener("sss-scheduler-created",handler);return()=>window.removeEventListener("sss-scheduler-created",handler);},[]);

  const selectedDay=useMemo(()=>{const d=new Date(clock);d.setHours(0,0,0,0);if(day==="tomorrow")d.setDate(d.getDate()+1);return d;},[clock,day]);
  const agenda=useMemo(()=>{
    if(day === "all") return schedules.map(schedule=>{
      const c=parseClock(schedule.start_time);
      const e=parseClock(schedule.end_time);
      const start=c?new Date(2000,0,1,c.hour,c.minute,c.second):new Date(8640000000000000);
      const end=e?new Date(2000,0,1,e.hour,e.minute,e.second):start;
      return {schedule,start,end,all:true};
    }).sort((a,b)=>a.start-b.start);
    return schedules.map(s=>occurrenceFor(s,selectedDay)).filter(Boolean).sort((a,b)=>a.start-b.start);
  },[schedules,selectedDay,day]);
  const stats=useMemo(()=>({enabled:schedules.filter(s=>s.enabled).length,total:schedules.length,today:agenda.length}),[schedules,agenda]);
  const selectedId=Number(sessionStorage.getItem("sss-open-schedule-id")||0);
  const allSchedules = day === "all";

  const openNew=()=>{setTab("scheduler");sessionStorage.removeItem("sss-open-schedule-id");setCreateRequest((value)=>value+1);};
  const focusSchedule=(id)=>{sessionStorage.setItem("sss-open-schedule-id",String(id));setTab("scheduler");window.scrollTo({top:document.body.scrollHeight,behavior:"smooth"});};

  return <div className="pageshell schedule-center-page">
    <header className="schedule-center-head">
      <div><div className="schedule-center-kicker">RADIO AUTOMATION WORKSPACE</div><h1>Scheduler &amp; Logs</h1><p>Program the station, review upcoming broadcasts, and audit playback history without leaving the control room.</p></div>
      <div className="schedule-center-head-actions"><Button variant="secondary" icon={RefreshCw} onClick={load}>Refresh</Button><Button variant="primary" icon={Plus} onClick={openNew}>New Schedule</Button></div>
    </header>

    <section className="schedule-center-metrics">
      <div><CalendarClock size={17}/><span><small>CONFIGURED</small><b>{stats.total}</b></span></div>
      <div><CheckCircle2 size={17}/><span><small>ENABLED</small><b>{stats.enabled}</b></span></div>
      <div><Clock3 size={17}/><span><small>{day==="today"?"TODAY":"TOMORROW"}</small><b>{stats.today} EVENTS</b></span></div>
    </section>

    <nav className="schedule-center-tabs" aria-label="Scheduler workspace">
      <button type="button" className={tab==="scheduler"?"active":""} onClick={()=>setTab("scheduler")}><CalendarClock size={16}/>Schedule Board</button>
      <button type="button" className={tab==="logs"?"active":""} onClick={()=>setTab("logs")}><ScrollText size={16}/>Playback Logs</button>
    </nav>

    {tab==="scheduler" ? <>
      <section className="schedule-board">
        <div className="schedule-board-head"><div><span className="schedule-center-kicker">PROGRAMMING CALENDAR</span><h2>{day==="today"?"Today":day==="tomorrow"?"Tomorrow":"All Schedules"}</h2><p>{day==="all"?"Every configured schedule, including disabled and recurring items.":formatDate(selectedDay)}</p></div><div className="schedule-day-tabs"><button type="button" className={day==="today"?"active":""} onClick={()=>setDay("today")}>Today</button><button type="button" className={day==="tomorrow"?"active":""} onClick={()=>setDay("tomorrow")}>Tomorrow</button><button type="button" className={day==="all"?"active":""} onClick={()=>setDay("all")}>All Schedules</button></div></div>
        {error&&<div className="schedule-center-error">{error}</div>}
        <div className="schedule-agenda-list">{loading?<div className="schedule-center-empty">Loading schedule board…</div>:agenda.length===0?<div className="schedule-center-empty"><CalendarClock size={24}/><strong>No scheduled events</strong><span>There are no configured events for this day.</span><button type="button" onClick={openNew}>Create the first schedule</button></div>:agenda.map(({schedule,start,end})=>{const live=!allSchedules&&clock>=start&&clock<end;const focused=selectedId===Number(schedule.id);return <button type="button" key={`${schedule.id}-${dateKey(start)}`} className={`schedule-agenda-row ${live?"live":""} ${focused?"focused":""}`} onClick={()=>focusSchedule(schedule.id)}>
          <span className="schedule-agenda-time"><b>{formatTime(start)}</b><small>{formatTime(end)}</small></span><span className="schedule-agenda-state">{allSchedules?<i>{schedule.enabled?"ENABLED":"DISABLED"}</i>:live?<i>ON AIR</i>:start>clock?<i>UP NEXT</i>:<i>ENDED</i>}</span><span className="schedule-agenda-main"><strong>{schedule.name||"Untitled schedule"}</strong><small>{targetLabel(schedule.target_type)} · #{schedule.target_id??"—"}</small></span><span className="schedule-agenda-countdown">{allSchedules?<small>{schedule.start_date||"No start date"} → {schedule.end_date||"No end date"}</small>:live?<><small>ENDS IN</small><b>{formatCountdown(end-clock)}</b></>:start>clock?<><small>STARTS IN</small><b>{formatCountdown(start-clock)}</b></>:<small>COMPLETED</small>}</span>
        </button>;})}</div>
      </section>

      <section className="schedule-center-editor"><div className="schedule-center-editor-head"><div><span className="schedule-center-kicker">SCHEDULE MANAGER</span><h2>Create &amp; Manage</h2></div><span className="schedule-center-note"><ListChecks size={15}/>{stats.total} configured</span></div><Scheduler onNavigate={onNavigate} createRequest={createRequest}/></section>
    </> : <section className="schedule-center-logs"><div className="schedule-center-logs-head"><div><span className="schedule-center-kicker">STATION HISTORY</span><h2>Playback Logs</h2><p>Review what actually played, skipped, failed, or was interrupted.</p></div><span className="schedule-center-note"><History size={15}/> Playback history</span></div><Logs/></section>}
  </div>;
}

import { useEffect, useState } from "react";
import { Music4, Repeat } from "lucide-react";
import { api } from "../../api";
import { formatTime } from "../../utils/format";
import "./NowPlaying.css";

function artworkOf(track) {
  const direct = track?.artwork || track?.artwork_url || track?.cover_url || track?.cover_art_url || track?.album_art_url;
  if (direct) return direct;
  const type = String(track?.type || "SONG").toUpperCase();
  const songId = track?.song_id ?? track?.id;
  return type === "SONG" && songId != null ? api.getSongArtworkUrl(songId) : null;
}

export default function NowPlaying({ track, elapsed = 0, isPlaying, crossfading, crossfadeProgress = 0, activeDeck = null, crossfadeSourceDeck = null, crossfadeTargetDeck = null }) {
  const [failed, setFailed] = useState(false);
  const artwork = artworkOf(track);
  useEffect(() => setFailed(false), [artwork, track?.id]);
  const image = artwork && !failed ? artwork : null;
  const duration = Math.max(0, Number(track?.duration ?? 0));
  const safeElapsed = Math.max(0, Number(elapsed ?? 0));
  const progress = duration ? Math.min(100, Math.max(0, safeElapsed / duration * 100)) : 0;
  const lit = Math.round(progress / 100 * 40);
  const title = track?.title || "Nothing playing";
  const artist = track?.artist || (track?.type && track.type !== "SONG" ? `Asset #${track.id}` : "Unknown artist");

  return (
    <div className={`nowplaying${image ? " nowplaying--has-art" : ""}`}>
      <div className="nowplaying__banner" aria-hidden="true">
        {image ? <img className="nowplaying__banner-image" src={image} alt="" onError={() => setFailed(true)} /> : <div className="nowplaying__banner-fallback"><span className="banner-orb banner-orb--one"/><span className="banner-orb banner-orb--two"/><Music4 size={64} strokeWidth={1.1}/></div>}
        <div className="nowplaying__banner-shade" />
      </div>
      <div className="nowplaying__content">
        <div className="nowplaying__art-wrap">
          <div className={`nowplaying__art${isPlaying ? " nowplaying__art--spinning" : ""}`}>
            {image ? <img src={image} alt="" onError={() => setFailed(true)} /> : <Music4 size={42} strokeWidth={1.4}/>} 
          </div>
          {isPlaying && <div className="nowplaying__art-ring" />}
        </div>
        <div className="nowplaying__meta">
          <div className="nowplaying__eyebrow-row"><span className="nowplaying__eyebrow">{track ? (isPlaying ? "NOW PLAYING" : "PAUSED") : "NO TRACK"}</span>{track?.type && track.type !== "SONG" && <span className="nowplaying__type">{track.type}</span>}</div>
          <h1 className="nowplaying__title" title={title}>{title}</h1>
          <span className="nowplaying__artist">{track ? artist : "Select a track to start playback"}</span>
          {track?.album && <span className="nowplaying__album">{track.album}</span>}
        </div>
        <div className="nowplaying__progress-block">
          <div className="nowplaying__segments" role="progressbar" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}>{Array.from({length:40},(_,i)=><span key={i} className={`nowplaying__segment${i < lit ? " nowplaying__segment--lit" : ""}`}/>)}</div>
          <div className="nowplaying__time-row"><span className="mono">{formatTime(safeElapsed)}</span><div className={`nowplaying__crossfade${crossfading ? " nowplaying__crossfade--active" : ""}`}><Repeat size={11}/><span>{crossfading ? `DECK ${crossfadeSourceDeck || activeDeck || "?"} → ${crossfadeTargetDeck || "?"} · ${Math.round(crossfadeProgress * 100)}%` : `DECK ${activeDeck || "A"} · READY`}</span></div><span className="mono">{formatTime(duration)}</span></div>
        </div>
      </div>
    </div>
  );
}

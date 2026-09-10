import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { useLiveStation } from "./useLiveStation";

function firstDefined(...values) {
  return values.find((v) => v !== undefined && v !== null);
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.items)) return value.items;
  return [];
}

function normalizeNowPlaying(data) {
  const item = firstDefined(
    data?.now_playing,
    data?.current_item,
    data?.current,
    data?.station?.now_playing,
    data?.playback?.now_playing
  );
  if (!item) return null;

  return {
    id: firstDefined(item.id, item.song_id, item.asset_id),
    title: firstDefined(item.title, item.name, "Unknown"),
    artist: firstDefined(item.artist, item.artist_name, ""),
    album: firstDefined(item.album, ""),
    duration: Number(firstDefined(item.duration_seconds, item.duration, 0)),
    position: Number(firstDefined(item.position_seconds, item.elapsed_seconds, 0)),
    type: firstDefined(item.kind, item.content_type, item.asset_type, "SONG"),
    raw: item,
  };
}

function isBackendPlaying(data) {
  const state = String(firstDefined(data?.station?.player_state, data?.state, data?.playback?.state, "")).toUpperCase();
  return state === "PLAYING" || data?.is_playing === true || data?.playing === true;
}

function normalizeVolume(data) {
  const value = firstDefined(data?.volume, data?.master_volume, data?.live_assist?.volume, data?.playback?.volume);
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 100;
  // Backend volume is normally 0..1; the UI uses a 0..100 slider.
  return Math.max(0, Math.min(100, numeric <= 1 ? numeric * 100 : numeric));
}

export function usePlayerState({ intervalMs = 1000 } = {}) {
  const live = useLiveStation({ intervalMs });
  const [actionError, setActionError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [volume, setVolumeState] = useState(100);
  const volumePendingRef = useRef(false);
  const volumeRequestRef = useRef(0);
  const volumeRef = useRef(100);
  const confirmedVolumeRef = useRef(100);

  // The live endpoint is the source of truth for the current track.
  // Derive it here before any effect/callback uses it.
  const nowPlaying = useMemo(
    () => normalizeNowPlaying(live.data),
    [live.data]
  );

  const libraryArtwork = useMemo(() => {
    const songId = nowPlaying?.id;
    if (!songId || String(nowPlaying?.type || "SONG").toUpperCase() !== "SONG") {
      return null;
    }
    return api.getSongArtworkUrl(songId);
  }, [nowPlaying?.id, nowPlaying?.type]);

  const queue = useMemo(() => asArray(live.data?.next_up).map((item) => ({
    ...item,
    id: item.id ?? item.song_id ?? item.asset_id,
    queue_item_id: item.queue_item_id,
    title: item.title ?? item.name ?? item.song_title ?? `Queue item #${item.id ?? item.queue_item_id ?? "?"}`,
    type: String(item.item_type || item.kind || item.content_type || item.asset_type || (item.asset_id != null ? "PROMO" : "SONG")).toLowerCase(),
    duration: Number(item.duration_seconds ?? item.duration ?? 0),
    artist: item.artist ?? item.artist_name ?? item.asset?.category ?? (String(item.item_type || item.kind || "").toUpperCase() === "PROMO" ? "Promo" : ""),
  })), [live.data]);

  const run = useCallback(async (operation) => {
    setBusy(true);
    setActionError(null);
    try {
      const result = await operation();
      await live.refresh();
      return result;
    } catch (err) {
      setActionError(err);
      throw err;
    } finally {
      setBusy(false);
    }
  }, [live.refresh]);

  useEffect(() => {
    if (volumePendingRef.current) return;
    const serverVolume = normalizeVolume(live.data);
    volumeRef.current = serverVolume;
    confirmedVolumeRef.current = serverVolume;
    setVolumeState(serverVolume);
  }, [live.data]);

  const setVolume = useCallback(async (nextVolume) => {
    const percent = Math.max(0, Math.min(100, Number(nextVolume)));
    if (!Number.isFinite(percent)) return;

    // Keep the slider optimistic while the request is in flight. The live
    // status poll can arrive out of order, so it must not overwrite a newer
    // operator value with an older snapshot.
    const requestId = ++volumeRequestRef.current;
    volumePendingRef.current = true;
    volumeRef.current = percent;
    setVolumeState(percent);

    try {
      const result = await api.setLiveAssistVolume(percent / 100);
      if (requestId !== volumeRequestRef.current) return;

      const serverVolume = normalizeVolume(result);
      volumeRef.current = serverVolume;
      confirmedVolumeRef.current = serverVolume;
      setVolumeState(serverVolume);
      volumePendingRef.current = false;
      await live.refresh();
    } catch (err) {
      if (requestId === volumeRequestRef.current) {
        volumePendingRef.current = false;
        volumeRef.current = confirmedVolumeRef.current;
        setVolumeState(confirmedVolumeRef.current);
      }
      setActionError(err);
      throw err;
    }
  }, [live.refresh]);

  const playFromQueue = useCallback((item) => {
    const queueItemId = firstDefined(item?.queue_item_id, item?.queueItemId);
    const songId = firstDefined(item?.id, item?.song_id, item?.asset_id);
    if (queueItemId) return run(() => api.playQueue(queueItemId));
    if (songId) return run(() => api.playSong(songId));
    return Promise.resolve();
  }, [run]);

  const play = useCallback(async () => {
    const state = String(live.data?.station?.player_state || live.data?.state || '').toUpperCase();
    if (state === 'PAUSED') return run(() => api.resume());
    if (state === 'PLAYING') return Promise.resolve();
    if (state === 'STOPPED' && nowPlaying?.id) return run(() => api.playSong(nowPlaying.id));
    if (queue[0]) return playFromQueue(queue[0]);
    return Promise.resolve();
  }, [live.data, nowPlaying, queue, playFromQueue, run]);

  const pause = useCallback(() => run(() => api.pause()), [run]);
  const stop = useCallback(() => run(() => api.stop()), [run]);
  const next = useCallback(() => run(() => api.playQueue()), [run]);
  const previous = useCallback(() => {
    setActionError(new Error("Previous playback is not exposed by the current backend API."));
  }, []);

  const clearQueue = useCallback(() => run(() => api.clearQueue()), [run]);

  const enrichedTrack = nowPlaying ? { ...nowPlaying, artwork: nowPlaying.artwork || libraryArtwork } : null;

  return {
    raw: live.data,
    station: live.data?.station || {},
    nowPlaying,
    track: enrichedTrack,
    queue,
    nextUp: queue,
    isPlaying: isBackendPlaying(live.data),
    elapsed: enrichedTrack?.position ?? 0,
    volume,
    crossfading: Boolean(live.data?.crossfading),
    crossfadeProgress: Number(live.data?.crossfade_progress ?? 0),
    crossfadeRemaining: Number(live.data?.crossfade_remaining_seconds ?? 0),
    activeDeck: live.data?.active_deck ?? null,
    crossfadeSourceDeck: live.data?.crossfade_source_deck ?? null,
    crossfadeTargetDeck: live.data?.crossfade_target_deck ?? null,
    loading: live.loading,
    error: live.error || actionError,
    connected: live.connected,
    busy,
    refresh: live.refresh,
    play,
    pause,
    stop,
    next,
    previous,
    playFromQueue,
    clearQueue,
    setVolume,
    playSong: (songId) => run(() => api.playSong(songId)),
    playAsset: (assetId) => run(() => api.playAsset(assetId)),
    resume: () => run(() => api.resume()),
  };
}

export default usePlayerState;

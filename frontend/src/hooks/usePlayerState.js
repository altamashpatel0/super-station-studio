import { useCallback, useEffect, useMemo, useState } from "react";
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
  return Number.isFinite(Number(value)) ? Number(value) : 1;
}

export function usePlayerState({ intervalMs = 1000 } = {}) {
  const live = useLiveStation({ intervalMs });
  const [actionError, setActionError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [volume, setVolumeState] = useState(1);

  const nowPlaying = useMemo(() => normalizeNowPlaying(live.data), [live.data]);
  const queue = useMemo(() => asArray(live.data?.next_up).map((item) => ({
    ...item,
    id: item.id ?? item.song_id ?? item.asset_id,
    type: String(item.kind || item.content_type || item.asset_type || "SONG").toLowerCase(),
    duration: Number(item.duration_seconds ?? item.duration ?? 0),
    artist: item.artist || "",
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
    setVolumeState(normalizeVolume(live.data));
  }, [live.data]);

  const setVolume = useCallback(async (nextVolume) => {
    const numeric = Math.max(0, Math.min(1, Number(nextVolume)));
    setVolumeState(numeric);
    await run(() => api.setLiveAssistVolume(numeric));
  }, [run]);

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

  return {
    raw: live.data,
    station: live.data?.station || {},
    nowPlaying,
    track: nowPlaying,
    queue,
    nextUp: queue,
    isPlaying: isBackendPlaying(live.data),
    elapsed: nowPlaying?.position ?? 0,
    volume,
    crossfading: Boolean(live.data?.crossfading),
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
    setVolume,
    playSong: (songId) => run(() => api.playSong(songId)),
    playAsset: (assetId) => run(() => api.playAsset(assetId)),
    resume: () => run(() => api.resume()),
  };
}

export default usePlayerState;

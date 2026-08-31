import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

export function useQueue({ enabled = true } = {}) {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    try {
      const data = await api.getQueue();
      setQueue(Array.isArray(data) ? data : data?.items || []);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const mutate = useCallback(async (operation) => {
    await operation();
    await refresh();
  }, [refresh]);

  return {
    queue,
    loading,
    error,
    refresh,
    addTrack: (songId, playNext = false) =>
      mutate(() => api.addTrackToQueue(songId, playNext)),
    addPlaylist: (playlistId) =>
      mutate(() => api.addPlaylistToQueue(playlistId)),
    remove: (id) =>
      mutate(() => api.removeQueueItem(id)),
    clear: () =>
      mutate(() => api.clearQueue()),
    moveUp: (id) =>
      mutate(() => api.moveQueueItemUp(id)),
    moveDown: (id) =>
      mutate(() => api.moveQueueItemDown(id)),
    play: (queueItemId = null) =>
      mutate(() => api.playQueue(queueItemId)),
  };
}

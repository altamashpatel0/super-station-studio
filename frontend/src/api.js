/**
 * frontend/src/api.js
 * ====================
 * Thin fetch wrapper around the backend API.
 */

const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* response had no JSON body */
    }
    throw new Error(detail);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  listSongs: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/library/songs${qs ? `?${qs}` : ""}`);
  },
  searchSongs: (q) => request(`/library/search?q=${encodeURIComponent(q)}`),
  getStats: () => request("/library/stats"),
  deleteSong: (id) => request(`/library/songs/${id}`, { method: "DELETE" }),
  startScan: (folderPath) =>
    request("/library/scan", {
      method: "POST",
      body: JSON.stringify({ folder_path: folderPath }),
    }),
  getScanStatus: (jobId) => request(`/library/scan/${jobId}`),
  refreshLibrary: () => request("/library/refresh", { method: "POST" }),

  playSong: (songId) =>
    request("/playback/play-song", {
      method: "POST",
      body: JSON.stringify({ song_id: songId }),
    }),
  pause: () => request("/playback/pause", { method: "POST" }),
  resume: () => request("/playback/resume", { method: "POST" }),
  stop: () => request("/playback/stop", { method: "POST" }),
  getPlaybackStatus: () => request("/playback/status"),

  // V0.8 Part 1 — read-only live station snapshot.
  getLiveStatus: (options = {}) => request("/live/status", options),
  getLiveAssistStatus: (options = {}) => request("/live-assist/status", options),
  setLiveAssistVolume: (volume) =>
    request("/live-assist/volume", {
      method: "POST",
      body: JSON.stringify({ volume }),
    }),
  listAssets: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/assets${qs ? `?${qs}` : ""}`);
  },
  playAsset: (assetId) => request(`/assets/${assetId}/play`, { method: "POST" }),
  getPlaybackReport: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/reports/playback${qs ? `?${qs}` : ""}`);
  },
  getReportSummary: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/reports/summary${qs ? `?${qs}` : ""}`);
  },

  // -- Playlists (V0.3) ---------------------------------------------
  listPlaylists: () => request("/playlists"),
  getPlaylist: (id) => request(`/playlists/${id}`),
  createPlaylist: (name, description = "") =>
    request("/playlists", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),
  updatePlaylist: (id, { name, description } = {}) =>
    request(`/playlists/${id}`, {
      method: "PUT",
      body: JSON.stringify({ name, description }),
    }),
  deletePlaylist: (id) => request(`/playlists/${id}`, { method: "DELETE" }),
  addTrackToPlaylist: (playlistId, songId, position) =>
    request(`/playlists/${playlistId}/tracks`, {
      method: "POST",
      body: JSON.stringify({ song_id: songId, position: position ?? null }),
    }),
  removeTrackFromPlaylist: (playlistId, trackId) =>
    request(`/playlists/${playlistId}/tracks/${trackId}`, { method: "DELETE" }),
  reorderPlaylistTracks: (playlistId, trackIds) =>
    request(`/playlists/${playlistId}/tracks/reorder`, {
      method: "PUT",
      body: JSON.stringify({ track_ids: trackIds }),
    }),
  clearPlaylistTracks: (playlistId) =>
    request(`/playlists/${playlistId}/tracks`, { method: "DELETE" }),

  // -- Queue (V0.3) ---------------------------------------------------
  getQueue: () => request("/queue"),
  addTrackToQueue: (songId, playNext = false) =>
    request("/queue", {
      method: "POST",
      body: JSON.stringify({ song_id: songId, play_next: playNext }),
    }),
  addPlaylistToQueue: (playlistId) =>
    request(`/queue/playlist/${playlistId}`, { method: "POST" }),
  removeQueueItem: (queueItemId) =>
    request(`/queue/${queueItemId}`, { method: "DELETE" }),
  clearQueue: () => request("/queue", { method: "DELETE" }),
  moveQueueItemUp: (queueItemId) =>
    request(`/queue/${queueItemId}/move-up`, { method: "POST" }),
  moveQueueItemDown: (queueItemId) =>
    request(`/queue/${queueItemId}/move-down`, { method: "POST" }),
  reorderQueue: (queueItemIds) =>
    request("/queue/reorder", {
      method: "PUT",
      body: JSON.stringify({ queue_item_ids: queueItemIds }),
    }),
};

/** Poll a scan job until it's completed/failed, calling onProgress along the way. */
export async function pollScanJob(jobId, { onProgress, intervalMs = 400 } = {}) {
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const job = await api.getScanStatus(jobId);
    onProgress?.(job);
    if (job.status === "completed" || job.status === "failed") return job;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

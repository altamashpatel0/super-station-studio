/**
 * frontend/src/api.js
 * ====================
 * API client for Super Station Studio.
 *
 * Important:
 * - JSON requests automatically receive Content-Type: application/json.
 * - FormData requests DO NOT set Content-Type manually. The browser adds
 *   multipart/form-data with the required boundary.
 */

const BASE = "/api";

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});

  // Never force application/json onto FormData.
  if (
    !(options.body instanceof FormData) &&
    options.body !== undefined &&
    options.body !== null &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;

    try {
      const body = await res.json();
      detail = body?.detail || body?.message || detail;
    } catch {
      // Response did not contain JSON.
    }

    const error = new Error(detail);
    error.status = res.status;
    throw error;
  }

  if (res.status === 204) return null;

  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return null;
  }

  return res.json();
}

export const api = {
  // -----------------------------------------------------------------------
  // Music Library
  // -----------------------------------------------------------------------

  listSongs: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/library/songs${qs ? `?${qs}` : ""}`);
  },

  searchSongs: (q) =>
    request(`/library/search?q=${encodeURIComponent(q)}`),

  getStats: () => request("/library/stats"),

  getSongArtworkUrl: (songId) => `${BASE}/library/songs/${encodeURIComponent(songId)}/artwork`,

  deleteSong: (id) =>
    request(`/library/songs/${id}`, { method: "DELETE" }),

  startScan: (folderPath) =>
    request("/library/scan", {
      method: "POST",
      body: JSON.stringify({ folder_path: folderPath }),
    }),

  getScanStatus: (jobId) =>
    request(`/library/scan/${jobId}`),

  refreshLibrary: () =>
    request("/library/refresh", { method: "POST" }),

  /**
   * Import MP3/WAV files selected through the browser folder picker.
   *
   * Do NOT set Content-Type here. fetch() must generate the multipart
   * boundary automatically.
   */
  importMusicFiles: async (files) => {
    const selectedFiles = Array.from(files || []);

    const audioFiles = selectedFiles.filter((file) =>
      /\.(mp3|wav)$/i.test(file.name)
    );

    if (!audioFiles.length) {
      throw new Error("No MP3 or WAV files found in the selected folder.");
    }

    const form = new FormData();

    for (const file of audioFiles) {
      form.append("files", file, file.name);
      form.append(
        "relative_paths",
        file.webkitRelativePath || file.name
      );
    }

    return request("/library/import-files", {
      method: "POST",
      body: form,
    });
  },

  // -----------------------------------------------------------------------
  // Playback
  // -----------------------------------------------------------------------

  playSong: (songId) =>
    request("/playback/play-song", {
      method: "POST",
      body: JSON.stringify({ song_id: songId }),
    }),

  pause: () =>
    request("/playback/pause", { method: "POST" }),

  resume: () =>
    request("/playback/resume", { method: "POST" }),

  stop: () =>
    request("/playback/stop", { method: "POST" }),

  getPlaybackStatus: () =>
    request("/playback/status"),

  // -----------------------------------------------------------------------
  // Playlists
  // -----------------------------------------------------------------------

  listPlaylists: () =>
    request("/playlists"),

  getPlaylist: (id) =>
    request(`/playlists/${id}`),

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

  deletePlaylist: (id) =>
    request(`/playlists/${id}`, { method: "DELETE" }),

  addTrackToPlaylist: (playlistId, songId, position) =>
    request(`/playlists/${playlistId}/tracks`, {
      method: "POST",
      body: JSON.stringify({
        song_id: songId,
        position: position ?? null,
      }),
    }),

  removeTrackFromPlaylist: (playlistId, trackId) =>
    request(`/playlists/${playlistId}/tracks/${trackId}`, {
      method: "DELETE",
    }),

  reorderPlaylistTracks: (playlistId, trackIds) =>
    request(`/playlists/${playlistId}/tracks/reorder`, {
      method: "PUT",
      body: JSON.stringify({ track_ids: trackIds }),
    }),

  clearPlaylistTracks: (playlistId) =>
    request(`/playlists/${playlistId}/tracks`, {
      method: "DELETE",
    }),


  // -----------------------------------------------------------------------
  // Live station / operator controls
  // -----------------------------------------------------------------------

  getLiveStatus: () => request("/live/status"),

  getLiveAssistStatus: () => request("/live-assist/status"),

  setLiveAssistVolume: (volume) =>
    request("/live-assist/volume", {
      method: "POST",
      body: JSON.stringify({ volume }),
    }),

  playQueue: (queueItemId = null) =>
    request(`/queue/play${queueItemId != null ? `?queue_item_id=${encodeURIComponent(queueItemId)}` : ""}`, {
      method: "POST",
    }),

  // -----------------------------------------------------------------------
  // Jingles / Advertisements
  // -----------------------------------------------------------------------

  listAssets: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/assets${qs ? `?${qs}` : ""}`);
  },

  getAsset: (id) => request(`/assets/${id}`),

  uploadAsset: async (file, { name, asset_type, category = "", description = "", priority = 0, cooldown_seconds = 0 } = {}) => {
    if (!file) throw new Error("No audio file selected.");
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("name", name || file.name.replace(/\.[^.]+$/, ""));
    form.append("asset_type", asset_type);
    form.append("category", category);
    form.append("description", description);
    form.append("priority", String(priority));
    form.append("cooldown_seconds", String(cooldown_seconds));
    return request("/assets/upload", { method: "POST", body: form });
  },

  playAsset: (id) =>
    request(`/assets/${id}/play`, { method: "POST" }),

  getAssetPlaybackStatus: (id) =>
    request(`/assets/${id}/playback-status`),

  updateAsset: (id, payload) =>
    request(`/assets/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  deleteAsset: (id) =>
    request(`/assets/${id}`, { method: "DELETE" }),

  enableAsset: (id) =>
    request(`/assets/${id}/enable`, { method: "POST" }),

  disableAsset: (id) =>
    request(`/assets/${id}/disable`, { method: "POST" }),

  // -----------------------------------------------------------------------
  // Scheduler
  // -----------------------------------------------------------------------

  listSchedules: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/schedules${qs ? `?${qs}` : ""}`);
  },

  getSchedule: (id) => request(`/schedules/${id}`),

  createSchedule: (payload) =>
    request("/schedules", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateSchedule: (id, payload) =>
    request(`/schedules/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  deleteSchedule: (id) =>
    request(`/schedules/${id}`, { method: "DELETE" }),

  enableSchedule: (id) =>
    request(`/schedules/${id}/enable`, { method: "POST" }),

  disableSchedule: (id) =>
    request(`/schedules/${id}/disable`, { method: "POST" }),

  getCurrentSchedule: (at) =>
    request(`/schedules/clock/current${at ? `?at=${encodeURIComponent(at)}` : ""}`),

  getNextSchedule: (at) =>
    request(`/schedules/clock/next${at ? `?at=${encodeURIComponent(at)}` : ""}`),

  selectScheduleTarget: (id, at) =>
    request(`/schedules/${id}/select${at ? `?at=${encodeURIComponent(at)}` : ""}`),

  getSchedulerRuntimeStatus: () =>
    request("/schedules/runtime/status"),

  runSchedulerTick: () =>
    request("/schedules/runtime/tick", { method: "POST" }),

  // -----------------------------------------------------------------------
  // Reports / logs
  // -----------------------------------------------------------------------

  getPlaybackReport: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/reports/playback${qs ? `?${qs}` : ""}`);
  },

  getReportSummary: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/reports/summary${qs ? `?${qs}` : ""}`);
  },

  getRecentlyPlayed: (limit = 6) =>
    request(`/reports/recently-played?limit=${encodeURIComponent(limit)}`),

  // -----------------------------------------------------------------------
  // Queue
  // -----------------------------------------------------------------------

  getQueue: () =>
    request("/queue"),

  addTrackToQueue: (songId, playNext = false) =>
    request("/queue", {
      method: "POST",
      body: JSON.stringify({
        song_id: songId,
        play_next: playNext,
      }),
    }),

  addPlaylistToQueue: (playlistId) =>
    request(`/queue/playlist/${playlistId}`, {
      method: "POST",
    }),

  removeQueueItem: (queueItemId) =>
    request(`/queue/${queueItemId}`, {
      method: "DELETE",
    }),

  clearQueue: () =>
    request("/queue", { method: "DELETE" }),

  moveQueueItemUp: (queueItemId) =>
    request(`/queue/${queueItemId}/move-up`, {
      method: "POST",
    }),

  moveQueueItemDown: (queueItemId) =>
    request(`/queue/${queueItemId}/move-down`, {
      method: "POST",
    }),

  reorderQueue: (queueItemIds) =>
    request("/queue/reorder", {
      method: "PUT",
      body: JSON.stringify({
        queue_item_ids: queueItemIds,
      }),
    }),
};

/**
 * Poll a scan job until it is completed or failed.
 */
export async function pollScanJob(
  jobId,
  { onProgress, intervalMs = 400 } = {}
) {
  while (true) {
    const job = await api.getScanStatus(jobId);

    onProgress?.(job);

    if (
      job.status === "completed" ||
      job.status === "failed"
    ) {
      return job;
    }

    await new Promise((resolve) =>
      setTimeout(resolve, intervalMs)
    );
  }
}

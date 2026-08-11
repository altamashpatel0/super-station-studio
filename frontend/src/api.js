/**
 * frontend/src/api.js
 * ====================
 * Thin fetch wrapper around the V0.2 Music Library + Playback API.
 * Every call goes through `request()` so error handling is consistent
 * and components don't repeat fetch/json boilerplate.
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

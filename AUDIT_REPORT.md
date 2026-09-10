# Super Station Studio — Full Project Audit & Fix Report

## Scope

Audited the supplied source bundle across Electron, React frontend, FastAPI backend, SQLite persistence, scheduler/runtime, queue, playback controller, history, library import, asset upload, and packaging paths.

## Critical fixes applied

1. **Manual/Scheduler/Queue/Asset playback ownership**
   - Removed source-priority blocking from `PlaybackController`.
   - The station now follows **last valid playback request wins**.
   - A new manual, scheduled, queue, or asset request can replace the current source.
   - Previous playback is notified/persisted before replacement.

2. **Scheduler recovery bug**
   - Selection failures occurred outside the scheduler runtime recovery wrapper.
   - This could bypass the retry/suppression policy.
   - Selection and playback errors are now handled by one runtime error path.

3. **Playback controller transport API**
   - Added controller-owned `pause()` and `resume()` methods.
   - Playback API now routes pause/resume through the same central controller.

4. **Per-Windows-user database isolation**
   - Electron already generated a per-user DB path, but the backend ignored `MUSIC_LIBRARY_DB_PATH`.
   - Backend now honors the path.
   - SQLite is initialized with WAL, NORMAL synchronous mode, foreign keys, and a 10-second busy timeout.

5. **Per-user uploaded/imported media storage**
   - Browser-imported music and uploaded jingles/advertisements previously used paths derived from the packaged backend location.
   - Storage is now rooted at `MUSIC_LIBRARY_DATA_DIR`, which Electron maps to that Windows user's app-data directory.

6. **Electron backend identity check**
   - Electron launches a per-instance backend token.
   - `/api/health` now returns that token so one desktop instance cannot accidentally attach to another instance's backend.

7. **Dynamic local ports**
   - Backend/frontend ports are allocated dynamically by Electron to avoid collisions between simultaneous Windows users/instances.

8. **Scheduler date/time controls**
   - Native time/date inputs now explicitly invoke Chromium's picker where supported.
   - End date has a minimum and six-month maximum.
   - Start-date changes prevent an invalid end-date window.
   - Removed a duplicate state assignment in scheduler form reset.

9. **Frontend branding**
   - Integrated the supplied Super Station Studio logo into the React sidebar and favicon.
   - Existing Electron splash/app icon assets remain in place.

10. **Frontend resilience**
    - Added a React error boundary so an unexpected page/component error no longer produces an unrecoverable blank interface.
    - Added a root `frontend:dev` script.

11. **Settings honesty/functionality**
    - Removed misleading switches whose backend effects were not implemented.
    - Station name and live polling interval are now functional local operator settings.
    - The low-end-PC refresh options are 2s/3s to reduce UI polling overhead.

12. **Fake top-bar controls**
    - Notification button now routes to Logs.
    - Broadcast-output button routes to Settings instead of being a dead control.

## Important architecture findings retained for later V1 work

- The audio decoder currently decodes a complete track into RAM. This is simple and testable but is not the ideal architecture for very long WAV files or extremely memory-constrained PCs. A future streaming decoder would reduce peak memory.
- The project contains both `backend/src` and `audio-engine/src` copies of the audio engine. Runtime currently uses `backend/src`; the duplicate should eventually be removed or made a separately versioned package to prevent drift.
- Production Electron wiring intentionally uses the single-deck controller. The two-deck/crossfade implementation exists but is not enabled in the production provider. This avoids opening two independent sound-card outputs on low-end machines.
- Overlapping schedules are resolved deterministically to one active occurrence. The UI should eventually warn users before creating overlapping windows rather than silently letting one win.
- Artwork is derived from embedded tags on demand. Tracks without embedded artwork return 404 and the UI falls back to an icon; this is cosmetic, not a playback failure.

## Verification performed

- Python syntax compilation: PASS.
- Electron Node syntax check: PASS.
- Database initialization and schedule date persistence smoke test: PASS.
- `/api/health` instance-token and dynamic localhost CORS smoke test: PASS.
- Manual -> Schedule overwrite smoke test: PASS.
- Schedule -> Manual overwrite smoke test: PASS.
- Focused scheduler/recovery/controller tests after fixes: **19 passed**.
- Additional repository/scheduler test runs reached **94 passing tests** before the long-running integration set exceeded the local execution timeout.

## Environment limitation

The audit container did not have PyAV (`av`) or `sounddevice`, and external package installation was unavailable. Therefore real Windows audio-device playback and PyAV decoding were not claimed as container-verified. The supplied Windows project should be tested in development mode before the final EXE build.

## Recommended final acceptance test on Windows

1. Start one backend and one frontend.
2. Play a manual song.
3. Trigger a schedule while the manual song is playing — scheduled content must replace it without backend restart.
4. Start manual playback while scheduled content is playing — manual content must replace it.
5. Restart backend — scheduler must resume automatically without needing another restart.
6. Create/edit schedules and verify times/dates survive page reload.
7. Import music/upload assets and restart the app — files and DB data must remain.
8. Test two separate Windows users and verify that songs, assets, schedules, queue, playback history and logs do not cross over.
9. Only after these pass, build the packaged installer.
## Latest requirement update — Dashboard schedule deletion + hard schedule end

- Dashboard Scheduler card now has a delete button for every displayed enabled schedule, with confirmation before deletion and immediate UI refresh after successful deletion.
- Scheduler playback is now strictly bounded by its configured time window. If scheduled content is still playing when the schedule reaches `end_time`, the current scheduled playback is paused, scheduler ownership is released, scheduled-playlist queue items are finalized/skipped, and the active playback-history row is closed as `SKIPPED`.
- A scheduled playlist longer than its window therefore cannot continue past the configured end time. For example, a 10-minute playlist scheduled from 23:50 to 23:55 is paused at approximately 23:55 (worker tick resolution is 250 ms).
- If another schedule begins at the boundary, the new scheduled request can immediately replace the previous scheduled source through the existing last-request-wins playback controller.


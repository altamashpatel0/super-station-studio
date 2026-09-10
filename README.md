# Super Station Studio

Professional Windows radio playout and automation software.

## Current implemented areas

- React + Electron desktop interface
- FastAPI backend
- SQLite per-user persistence in Electron
- Music library scanning/import
- Playlist management
- Queue management
- Manual playback controls
- Jingles and advertisements
- Schedule management with repeat days and calendar date range
- 24/7 scheduler worker with recovery/watchdog lifecycle
- Playback history and reports
- Live station status
- Local operator settings
- Supplied Super Station Studio branding/logo

## Playback rule

Super Station Studio uses a **last valid playback request wins** model:

- Manual playback can replace scheduled playback.
- Scheduled playback can replace manual playback.
- Queue playback can replace the current source when explicitly requested.
- Asset playback can replace the current source.

The previous item is recorded as skipped/replaced where applicable; playback history is not deleted.

## Development

### Backend

```bat
cd /d "E:\internship project\super-station-studio"
cd backend
python run_backend.py
```

### Frontend

```bat
cd /d "E:\internship project\super-station-studio"
npm run frontend:dev
```

Or:

```bat
cd frontend
npm run dev
```

## Production build

Do not package until development-mode playback, scheduler, storage and multi-user isolation tests pass.

```bat
npm run desktop:build
```

## Notes

The supplied audio engine currently decodes one complete track into memory. This keeps the V1 playback state machine simple, but very long uncompressed WAV files can consume substantial RAM. Streaming decode is a future performance upgrade.

See `AUDIT_REPORT.md` for the project audit, fixes, verification results, and remaining V1 architecture work.

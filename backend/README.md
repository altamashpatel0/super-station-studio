# Super Station Studio

Professional radio automation & playout system.

## Status

- **V0.1 — Core Audio Engine**: complete (see `src/`). Not modified in V0.2.
- **V0.2 — Music Library**: complete (see `app/`, `frontend/`). This is the current milestone.

## Project layout

```
src/                  V0.1 audio engine (untouched) - AudioEngine, Player, Decoder, AudioOutput
app/                  V0.2 backend (FastAPI)
  main.py             App entry point / router wiring
  api/
    library.py        Music Library HTTP endpoints
    playback.py        Thin wrapper that calls the existing V0.1 AudioEngine
    engine_provider.py  Shared AudioEngine singleton
  database/
    models.py          SQLAlchemy models (Song, ScannedFolder)
    database.py         Engine/session setup
    repositories/
      song_repository.py  All SQL for the songs table
  services/
    metadata_service.py   Mutagen-based tag extraction + filename fallback
    library_scanner.py    Recursive folder walk, format filtering
    library_service.py    Orchestration: scan jobs, refresh, rescan
  schemas/
    library.py           Pydantic request/response models
tests/                 V0.2 test suite (pytest)
frontend/              React + Vite Music Library screen
data/                  SQLite database file lives here (git-ignored)
```

## Running the backend

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
uvicorn app.main:app --reload --port 8000
```

The API is then at `http://localhost:8000`, docs at `http://localhost:8000/docs`.

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173` and proxies `/api/*` to the backend on port 8000.

## Scanning a music folder

Either through the UI ("Import Folder" button) or directly:

```bash
curl -X POST http://localhost:8000/api/library/scan \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "/path/to/your/music"}'
```

This returns a job immediately (`202 Accepted`); poll
`GET /api/library/scan/{job_id}` until `status` is `completed`.

## Running tests

```bash
pip install -r requirements.txt --break-system-packages
pytest
```

## API summary (V0.2)

| Method | Path                          | Purpose                                   |
|--------|-------------------------------|--------------------------------------------|
| POST   | `/api/library/scan`           | Start a background folder scan (returns a job) |
| GET    | `/api/library/scan/{job_id}`  | Poll scan job status                       |
| POST   | `/api/library/refresh`        | Soft-disable songs whose files are missing |
| POST   | `/api/library/rescan`         | Re-scan every previously-scanned folder    |
| GET    | `/api/library/songs`          | List songs (sort/paginate/enabled-only)    |
| GET    | `/api/library/songs/{id}`     | Get one song                               |
| DELETE | `/api/library/songs/{id}`     | Delete a song record                       |
| GET    | `/api/library/search?q=`      | Search title/artist/album/genre            |
| GET    | `/api/library/filter`         | Filter by artist/album/genre                |
| GET    | `/api/library/stats`          | Library-wide statistics                    |
| POST   | `/api/playback/play-song`     | Load + play a song via the V0.1 engine     |
| POST   | `/api/playback/pause`         | Pause                                       |
| POST   | `/api/playback/resume`        | Resume                                     |
| POST   | `/api/playback/stop`          | Stop                                       |
| GET    | `/api/playback/status`        | Current playback status                    |

## Git workflow

```bash
git checkout -b feature/v0.2-music-library
git add app/ frontend/ tests/ requirements.txt pytest.ini .gitignore README.md
git commit -m "feat(database): add music library schema"
git commit -m "feat(scanner): add recursive audio folder scanner"
git commit -m "feat(metadata): add audio metadata extraction"
git commit -m "feat(api): add music library endpoints"
git commit -m "feat(ui): add music library screen"
git commit -m "test(library): add music library tests"
git push -u origin feature/v0.2-music-library
```
(Commit in logical chunks as you go rather than one giant commit — the
message groups above map roughly to the files listed in the report below.)

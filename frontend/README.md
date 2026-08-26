# Super Station Studio — Frontend (V0.1 Milestone)

Professional Windows radio automation and playout console UI. **Frontend only** —
the audio engine, backend, and database are separate and untouched by this milestone.

## Stack
- React 19 + Vite
- JavaScript (no TypeScript)
- Plain CSS (component-scoped stylesheets, CSS custom-property design tokens)
- lucide-react for icons

## Getting started
```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # production build to /dist
npm run lint     # oxlint
```

## Structure
```
src/
├── components/
│   ├── layout/     Sidebar, TopBar, StatusBar
│   ├── player/      NowPlaying, PlayerControls, VolumeControl
│   ├── queue/       NextUpPanel, QueueItem
│   └── common/      PageHeader, Button, StatCard, Switch
├── pages/           Dashboard, MusicLibrary, Playlists, Jingles,
│                     Advertisements, Scheduler, Logs, Settings
├── hooks/
│   └── usePlayerState.js   Mock playback engine (state only, no real audio)
├── data/
│   └── mockData.js  All mock/demo data for this milestone
├── styles/          Design tokens, base styles, shared page-shell styles
├── App.jsx          Page routing (local state, no router dependency)
└── main.jsx
```

## What's implemented (V0.1 frontend milestone)
- Full navigation across all 8 pages
- Now Playing panel with simulated progress, crossfade indicator
- Working transport controls (play/pause/stop/next/previous) against mock state
- Volume slider with live mute toggle
- Live clock (updates every second)
- Interactive ON AIR / OFF AIR toggle
- Clickable Next Up queue (selecting an item promotes it to Now Playing)
- Bottom status bar with animated mock CPU/RAM figures
- Mock data only — no FastAPI, no SQLite, no real audio playback, no Electron

## Explicitly out of scope for this milestone
- Backend/API integration
- Persistence
- Electron packaging
- Real audio playback via the audio engine

## Design notes
Dark broadcast-console aesthetic. Palette, type (Space Grotesk / Inter / JetBrains Mono),
and the segmented LED-style progress meter are original to this project — see
`src/styles/tokens.css` for the full token set.

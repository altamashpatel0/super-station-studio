// Mock data only — no backend, no persistence. Milestone V0.1 frontend.

export const nowPlayingTrack = {
  id: 't-4471',
  title: 'Midnight Frequency',
  artist: 'The Signal Drift',
  album: 'Static & Stars',
  duration: 214, // seconds
  type: 'song',
};

export const queueItems = [
  { id: 'q-1', type: 'song', title: 'Neon Horizon', artist: 'Vela Coast', duration: '3:41' },
  { id: 'q-2', type: 'jingle', title: 'Station ID — Short Sweep', artist: 'Jingle Pack A', duration: '0:08' },
  { id: 'q-3', type: 'ad', title: 'Riverside Motors — Summer Sale', artist: 'Ad Break 14B', duration: '0:30' },
  { id: 'q-4', type: 'song', title: 'Paper Boats', artist: 'Halden & Wren', duration: '4:02' },
  { id: 'q-5', type: 'station-id', title: 'You Are Listening To 101.3 FM', artist: 'Station ID', duration: '0:06' },
  { id: 'q-6', type: 'song', title: 'Low Tide Radio', artist: 'Coastal Static', duration: '3:15' },
  { id: 'q-7', type: 'jingle', title: 'Weather Bumper', artist: 'Jingle Pack C', duration: '0:12' },
];

export const musicLibrary = [
  { id: 'm-1', title: 'Midnight Frequency', artist: 'The Signal Drift', album: 'Static & Stars', genre: 'Synthwave', duration: '3:34', bpm: 108 },
  { id: 'm-2', title: 'Neon Horizon', artist: 'Vela Coast', album: 'Coastline', genre: 'Chillwave', duration: '3:41', bpm: 96 },
  { id: 'm-3', title: 'Paper Boats', artist: 'Halden & Wren', album: 'Quiet Rooms', genre: 'Indie Folk', duration: '4:02', bpm: 84 },
  { id: 'm-4', title: 'Low Tide Radio', artist: 'Coastal Static', album: 'AM/FM', genre: 'Dream Pop', duration: '3:15', bpm: 102 },
  { id: 'm-5', title: 'Departure Lounge', artist: 'Atlas Grey', album: 'Terminal', genre: 'Ambient', duration: '5:12', bpm: 70 },
  { id: 'm-6', title: 'Circuit City', artist: 'Kilo Static', album: 'Voltage', genre: 'Synthwave', duration: '3:58', bpm: 118 },
  { id: 'm-7', title: 'Rearview', artist: 'The Long Drive', album: 'Overnight', genre: 'Indie Rock', duration: '3:22', bpm: 124 },
  { id: 'm-8', title: 'Analog Heart', artist: 'Vela Coast', album: 'Coastline', genre: 'Chillwave', duration: '4:11', bpm: 92 },
];

export const playlists = [
  { id: 'p-1', name: 'Morning Drive', trackCount: 42, duration: '2h 18m', updated: 'Today, 06:00' },
  { id: 'p-2', name: 'Late Night Chill', trackCount: 28, duration: '1h 46m', updated: 'Yesterday' },
  { id: 'p-3', name: 'Weekend Top 40', trackCount: 51, duration: '2h 55m', updated: '2 days ago' },
  { id: 'p-4', name: 'Indie Discovery', trackCount: 33, duration: '2h 04m', updated: '4 days ago' },
  { id: 'p-5', name: 'Overnight Ambient', trackCount: 19, duration: '2h 31m', updated: '1 week ago' },
];

export const jingles = [
  { id: 'j-1', name: 'Station ID — Short Sweep', category: 'ID', duration: '0:08' },
  { id: 'j-2', name: 'Top of Hour Stinger', category: 'Stinger', duration: '0:05' },
  { id: 'j-3', name: 'Weather Bumper', category: 'Bumper', duration: '0:12' },
  { id: 'j-4', name: 'News Intro', category: 'Intro', duration: '0:15' },
  { id: 'j-5', name: 'Traffic Sweeper', category: 'Sweeper', duration: '0:09' },
  { id: 'j-6', name: 'Station ID — Long Version', category: 'ID', duration: '0:22' },
];

export const advertisements = [
  { id: 'a-1', client: 'Riverside Motors', campaign: 'Summer Sale', duration: '0:30', plays: 142, status: 'active' },
  { id: 'a-2', client: 'Harbor Coffee Co.', campaign: 'New Roast Launch', duration: '0:15', plays: 88, status: 'active' },
  { id: 'a-3', client: 'Blue Ridge Realty', campaign: 'Open House Weekend', duration: '0:30', plays: 61, status: 'paused' },
  { id: 'a-4', client: 'Northgate Dental', campaign: 'Fall Checkup Promo', duration: '0:20', plays: 34, status: 'active' },
  { id: 'a-5', client: 'Union Hardware', campaign: 'Tool Rental Special', duration: '0:15', plays: 12, status: 'scheduled' },
];

export const scheduleBlocks = [
  { id: 's-1', time: '06:00', label: 'Morning Drive', type: 'playlist' },
  { id: 's-2', time: '09:00', label: 'Music Sweep — Mixed', type: 'auto' },
  { id: 's-3', time: '12:00', label: 'Midday News Break', type: 'live' },
  { id: 's-4', time: '12:15', label: 'Music Sweep — Mixed', type: 'auto' },
  { id: 's-5', time: '17:00', label: 'Drive Home', type: 'playlist' },
  { id: 's-6', time: '20:00', label: 'Late Night Chill', type: 'playlist' },
  { id: 's-7', time: '00:00', label: 'Overnight Ambient', type: 'auto' },
];

export const logEntries = [
  { id: 'l-1', time: '14:32:08', level: 'info', message: 'Track started: "Midnight Frequency" — The Signal Drift' },
  { id: 'l-2', time: '14:29:41', level: 'info', message: 'Crossfade completed (2.4s)' },
  { id: 'l-3', time: '14:29:38', level: 'info', message: 'Track ended: "Analog Heart" — Vela Coast' },
  { id: 'l-4', time: '14:12:03', level: 'warning', message: 'Ad break 14B ran 2s over scheduled duration' },
  { id: 'l-5', time: '13:58:55', level: 'info', message: 'Playlist "Morning Drive" queued for 06:00 block' },
  { id: 'l-6', time: '13:40:12', level: 'error', message: 'Audio device buffer underrun recovered automatically' },
  { id: 'l-7', time: '13:15:00', level: 'info', message: 'Scheduler executed block: Midday News Break' },
  { id: 'l-8', time: '12:59:44', level: 'info', message: 'System check passed — all outputs nominal' },
];

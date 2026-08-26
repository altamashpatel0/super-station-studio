import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Download,
  Filter,
  ListFilter,
  Megaphone,
  Music2,
  Radio,
  RefreshCw,
  Search,
  TriangleAlert,
  Volume2,
  XCircle,
} from "lucide-react";
import PageHeader from "../components/common/PageHeader";
import Button from "../components/common/Button";
import { api } from "../api";
import "./Logs.css";

const TYPES = [
  { value: "ALL", label: "All types" },
  { value: "SONG", label: "Song" },
  { value: "JINGLE", label: "Jingle" },
  { value: "ADVERTISEMENT", label: "Advertisement" },
  { value: "PLAYLIST", label: "Playlist" },
];

const STATUSES = [
  { value: "ALL", label: "All statuses" },
  { value: "PLAYING", label: "Playing" },
  { value: "COMPLETED", label: "Completed" },
  { value: "SKIPPED", label: "Skipped" },
  { value: "FAILED", label: "Failed" },
  { value: "STOPPED", label: "Stopped" },
  { value: "ERROR", label: "Error" },
];

function pick(obj, keys, fallback = "") {
  for (const key of keys) {
    const value = obj?.[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return fallback;
}

function extractRows(payload) {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== "object") return [];
  for (const key of ["items", "events", "history", "rows", "results", "data"]) {
    if (Array.isArray(payload[key])) return payload[key];
  }
  return [];
}

function normalizeType(value, row) {
  const raw = String(
    value ??
      pick(row, ["kind", "content_type", "media_type", "target_type"], "")
  )
    .trim()
    .toUpperCase();

  if (raw.includes("ADVERTISEMENT") || raw === "AD" || raw === "ADS") {
    return "ADVERTISEMENT";
  }
  if (raw.includes("JINGLE")) return "JINGLE";
  if (raw.includes("PLAYLIST")) return "PLAYLIST";
  if (raw.includes("SONG") || raw === "MUSIC" || raw === "TRACK") return "SONG";

  const text = String(
    pick(row, ["name", "title", "content", "message", "selected_name"], "")
  ).toLowerCase();

  if (text.includes("advert")) return "ADVERTISEMENT";
  if (text.includes("jingle")) return "JINGLE";
  if (text.includes("playlist")) return "PLAYLIST";
  return "SONG";
}

function normalizeStatus(value, row) {
  const raw = String(
    value ?? pick(row, ["state", "result", "outcome"], "COMPLETED")
  )
    .trim()
    .toUpperCase();

  if (raw.includes("FAIL") || raw.includes("ERROR")) return "FAILED";
  if (raw.includes("SKIP")) return "SKIPPED";
  if (raw.includes("STOP")) return "STOPPED";
  if (raw.includes("PLAY")) return "PLAYING";
  if (raw.includes("COMPLETE") || raw === "DONE" || raw === "SUCCESS") {
    return "COMPLETED";
  }
  return raw || "COMPLETED";
}

function toNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function formatDuration(seconds) {
  const n = toNumber(seconds);
  if (n === null || n < 0) return "—";
  const total = Math.round(n);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function parseBackendTimestamp(value) {
  if (value === undefined || value === null || value === "") return null;
  if (value instanceof Date) return new Date(value.getTime());

  const raw = String(value).trim();
  if (!raw) return null;

  // The backend stores UTC as a naive ISO datetime (for SQLite compatibility).
  // A browser otherwise interprets "2026-08-25T13:05:08" as local time, which
  // shifts the displayed Indian time by -5:30. Treat timezone-less backend
  // timestamps as UTC; explicit Z/offset timestamps are already unambiguous.
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw);
  const parsed = new Date(hasTimezone ? raw : `${raw}Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function localDateKey(date) {
  if (!date) return "";
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function normalizeRow(row, index) {
  const timestamp = pick(row, [
    "started_at",
    "start_time",
    "played_at",
    "timestamp",
    "created_at",
    "time",
    "date",
  ]);

  const date = parseBackendTimestamp(timestamp);
  const validDate = Boolean(date);

  const type = normalizeType(
    pick(row, ["type", "event_type", "item_type", "content_type"]),
    row
  );

  const status = normalizeStatus(
    pick(row, ["status", "state", "playback_state"]),
    row
  );

  const title = pick(row, [
    "content",
    "name",
    "title",
    "selected_name",
    "song_title",
    "asset_name",
    "message",
    "content_name",
    "contentName",
  ], "Unknown");

  const artist = pick(row, ["artist", "song_artist", "artist_name"], "");
  const content = artist && type === "SONG" ? `${title} — ${artist}` : String(title);

  const duration = toNumber(
    pick(row, [
      "duration_seconds",
      "duration",
      "played_seconds",
      "elapsed_seconds",
      "duration_s",
    ], null)
  );

  const rawId = pick(row, ["id", "event_id", "history_id", "playback_id"], "");
  return {
    id: rawId || `${timestamp || "event"}-${index}`,
    date: validDate ? date : null,
    dateText: validDate
      ? date.toLocaleDateString("en-IN", {
          day: "2-digit",
          month: "short",
          year: "numeric",
        })
      : "—",
    timeText: validDate
      ? date.toLocaleTimeString("en-IN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })
      : String(timestamp || "—"),
    isoDate: validDate ? localDateKey(date) : "",
    type,
    content,
    duration,
    durationText: formatDuration(duration),
    status,
    raw: row,
  };
}

function typeIcon(type) {
  if (type === "ADVERTISEMENT") return <Megaphone size={15} />;
  if (type === "JINGLE") return <Volume2 size={15} />;
  if (type === "PLAYLIST") return <ListFilter size={15} />;
  return <Music2 size={15} />;
}

function typeLabel(type) {
  if (type === "ADVERTISEMENT") return "Advertisement";
  if (type === "JINGLE") return "Jingle";
  if (type === "PLAYLIST") return "Playlist";
  return "Song";
}

/*
 * Small dependency-free XLSX writer.
 * It creates a real Office Open XML workbook in the browser, so no
 * additional npm package is required just for exporting Logs.
 */
const encoder = new TextEncoder();

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let i = 0; i < 8; i += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function u16(n) {
  return new Uint8Array([n & 255, (n >>> 8) & 255]);
}

function u32(n) {
  return new Uint8Array([
    n & 255,
    (n >>> 8) & 255,
    (n >>> 16) & 255,
    (n >>> 24) & 255,
  ]);
}

function concatBytes(...arrays) {
  const total = arrays.reduce((sum, a) => sum + a.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const array of arrays) {
    out.set(array, offset);
    offset += array.length;
  }
  return out;
}

function zipStored(files) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;

  for (const file of files) {
    const name = encoder.encode(file.name);
    const data = typeof file.data === "string" ? encoder.encode(file.data) : file.data;
    const crc = crc32(data);

    const local = concatBytes(
      new Uint8Array([0x50, 0x4b, 0x03, 0x04]),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(name.length),
      u16(0),
      name,
      data
    );
    localParts.push(local);

    const central = concatBytes(
      new Uint8Array([0x50, 0x4b, 0x01, 0x02]),
      u16(20),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(name.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0),
      u32(offset),
      name
    );
    centralParts.push(central);
    offset += local.length;
  }

  const central = concatBytes(...centralParts);
  const locals = concatBytes(...localParts);
  const end = concatBytes(
    new Uint8Array([0x50, 0x4b, 0x05, 0x06]),
    u16(0),
    u16(0),
    u16(files.length),
    u16(files.length),
    u32(central.length),
    u32(locals.length),
    u16(0)
  );
  return concatBytes(locals, central, end);
}

function xmlEscape(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function sheetXml(rows) {
  const xmlRows = rows
    .map((row, r) => {
      const cells = row
        .map((value, c) => {
          const ref = `${String.fromCharCode(65 + c)}${r + 1}`;
          const text = String(value ?? "");
          return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${xmlEscape(text)}</t></is></c>`;
        })
        .join("");
      return `<row r="${r + 1}">${cells}</row>`;
    })
    .join("");

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>${xmlRows}</sheetData>
</worksheet>`;
}

function buildXlsx(rows) {
  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>`;

  const rels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`;

  const workbook = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Playback Logs" sheetId="1" r:id="rId1"/></sheets>
</workbook>`;

  const workbookRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>`;

  return zipStored([
    { name: "[Content_Types].xml", data: contentTypes },
    { name: "_rels/.rels", data: rels },
    { name: "xl/workbook.xml", data: workbook },
    { name: "xl/_rels/workbook.xml.rels", data: workbookRels },
    { name: "xl/worksheets/sheet1.xml", data: sheetXml(rows) },
  ]);
}

function downloadXlsx(rows, filename) {
  const bytes = buildXlsx(rows);
  const blob = new Blob([bytes], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Logs() {
  const [rows, setRows] = useState([]);
  const [date, setDate] = useState("");
  const [type, setType] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const loadLogs = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    setError("");

    try {
      // Backend playback-report endpoint accepts a maximum page size of 500.
      // Using 5000 causes FastAPI validation to return HTTP 422.
      const params = { limit: 500 };
      if (date) params.date = date;
      // Backend names the type query parameter content_type. PLAYLIST is a
      // UI/container type and is filtered client-side because the history
      // recorder stores the actual item (song/jingle/ad) that played.
      if (type !== "ALL" && type !== "PLAYLIST") params.content_type = type;
      // Backend supports PLAYING/COMPLETED/SKIPPED/FAILED. STOPPED/ERROR are
      // kept as UI compatibility filters and are applied client-side.
      if (status !== "ALL" && !["STOPPED", "ERROR"].includes(status)) {
        params.status = status;
      }

      const report = await api.getPlaybackReport(params);

      setRows(
        extractRows(report)
          .map(normalizeRow)
          .sort((a, b) => {
            const ta = a.date?.getTime() ?? 0;
            const tb = b.date?.getTime() ?? 0;
            return tb - ta;
          })
      );

    } catch (err) {
      setError(err?.message || "Could not load playback history.");
      setRows([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [date, type, status]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();

    return rows.filter((row) => {
      if (date && row.isoDate !== date) return false;
      if (type !== "ALL" && row.type !== type) return false;
      if (status !== "ALL" && row.status !== status) return false;
      if (!q) return true;

      return [row.content, row.type, typeLabel(row.type), row.status, row.dateText, row.timeText]
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
  }, [rows, search, date, type, status]);

  const counts = useMemo(() => {
    const completed = filteredRows.filter((r) => r.status === "COMPLETED").length;
    const playing = filteredRows.filter((r) => r.status === "PLAYING").length;
    const failed = filteredRows.filter((r) => r.status === "FAILED").length;
    const totalSeconds = filteredRows.reduce(
      (sum, r) => sum + (r.duration || 0),
      0
    );
    return {
      total: filteredRows.length,
      completed,
      playing,
      failed,
      totalSeconds,
    };
  }, [filteredRows]);

  const exportLogs = () => {
    const exportRows = [
      [
        "Date",
        "Time",
        "Type",
        "Content",
        "Duration",
        "Status",
        "Event ID",
        "Content ID",
        "Source",
      ],
      ...filteredRows.map((row) => [
        row.dateText,
        row.timeText,
        typeLabel(row.type),
        row.content,
        row.durationText,
        row.status,
        row.id,
        pick(row.raw, ["content_id", "asset_id", "song_id"], ""),
        pick(row.raw, ["source", "operator", "origin"], "ENGINE"),
      ]),
    ];

    const stamp = date || new Date().toISOString().slice(0, 10);
    downloadXlsx(exportRows, `super-station-playback-logs-${stamp}.xlsx`);
  };

  const statCards = [
    { label: "Total events", value: counts.total, icon: Activity },
    { label: "Completed", value: counts.completed, icon: CheckCircle2 },
    { label: "Playing", value: counts.playing, icon: Radio },
    { label: "Failures", value: counts.failed, icon: TriangleAlert },
  ];

  return (
    <div className="pageshell logs-page">
      <PageHeader
        title="Logs"
        subtitle="Real playback activity from the station backend"
        actions={
          <div className="logs-page__actions">
            <Button
              variant="secondary"
              icon={RefreshCw}
              onClick={() => loadLogs(true)}
              disabled={loading || refreshing}
            >
              {refreshing ? "Refreshing…" : "Refresh"}
            </Button>
            <Button
              variant="secondary"
              icon={Download}
              onClick={exportLogs}
              disabled={!filteredRows.length}
            >
              Export Excel
            </Button>
          </div>
        }
      />

      <div className="pageshell__body logs-page__body">
        <div className="logs-stats">
          {statCards.map(({ label, value, icon: Icon }) => (
            <div className="logs-stat" key={label}>
              <div className="logs-stat__icon"><Icon size={17} /></div>
              <div>
                <div className="logs-stat__value">{value}</div>
                <div className="logs-stat__label">{label}</div>
              </div>
            </div>
          ))}
          <div className="logs-stat">
            <div className="logs-stat__icon"><Clock3 size={17} /></div>
            <div>
              <div className="logs-stat__value">{formatDuration(counts.totalSeconds)}</div>
              <div className="logs-stat__label">Played time</div>
            </div>
          </div>
        </div>

        <div className="logs-filters">
          <div className="logs-search">
            <Search size={16} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search song, ad, jingle, playlist…"
            />
          </div>

          <label className="logs-filter">
            <CalendarDays size={15} />
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              aria-label="Filter by date"
            />
          </label>

          <label className="logs-filter">
            <Filter size={15} />
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>

          <label className="logs-filter">
            <ListFilter size={15} />
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>

          {(date || type !== "ALL" || status !== "ALL" || search) && (
            <button
              type="button"
              className="logs-clear"
              onClick={() => {
                setDate("");
                setType("ALL");
                setStatus("ALL");
                setSearch("");
              }}
            >
              <XCircle size={15} />
              Clear
            </button>
          )}
        </div>

        {error && (
          <div className="logs-error">
            <TriangleAlert size={17} />
            <span>{error}</span>
            <button type="button" onClick={() => loadLogs()}>Retry</button>
          </div>
        )}

        <div className="logs-table-wrap">
          <table className="datatable logs-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Time</th>
                <th>Type</th>
                <th>Content</th>
                <th>Duration</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="logs-empty">Loading playback history…</td>
                </tr>
              ) : filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="logs-empty">
                    <div className="logs-empty__icon"><Radio size={20} /></div>
                    <div>No playback activity found.</div>
                    <span>Play a song, jingle, advertisement or playlist, then refresh.</span>
                  </td>
                </tr>
              ) : (
                filteredRows.map((row) => (
                  <tr key={row.id}>
                    <td className="mono logs-date">{row.dateText}</td>
                    <td className="mono logs-time">{row.timeText}</td>
                    <td>
                      <span className={`logs-type logs-type--${row.type.toLowerCase()}`}>
                        {typeIcon(row.type)}
                        {typeLabel(row.type)}
                      </span>
                    </td>
                    <td className="logs-content" title={row.content}>{row.content}</td>
                    <td className="mono logs-duration">{row.durationText}</td>
                    <td>
                      <span className={`logs-status logs-status--${row.status.toLowerCase()}`}>
                        {row.status === "COMPLETED" && <CheckCircle2 size={14} />}
                        {row.status === "PLAYING" && <Radio size={14} />}
                        {row.status === "FAILED" && <TriangleAlert size={14} />}
                        {row.status === "SKIPPED" && <XCircle size={14} />}
                        {row.status === "STOPPED" && <XCircle size={14} />}
                        {row.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

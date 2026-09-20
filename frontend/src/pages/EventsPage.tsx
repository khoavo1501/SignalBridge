import { ChevronLeft, ChevronRight, Inbox, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiGet } from "../api/client";
import type { EventsResponse } from "../api/types";
import { useLive, type SessionEvent } from "../state/LiveContext";
import { fmtClock } from "../state/format";

const RANGES = [
  { label: "5m", s: 300 },
  { label: "15m", s: 900 },
  { label: "1h", s: 3600 },
  { label: "6h", s: 21600 },
  { label: "24h", s: 86400 },
  { label: "7d", s: 604800 },
];
const SEVERITIES = ["all", "critical", "warning", "info"] as const;
const PAGE_SIZE = 25;

function sevClass(sev: string | null): string {
  if (sev === "critical") return "bad";
  if (sev === "warning") return "amber";
  return "dim";
}

export default function EventsPage() {
  const { sessionEvents, refresh: refreshLive } = useLive();
  const [rest, setRest] = useState<SessionEvent[]>([]);
  const [rangeIx, setRangeIx] = useState(4);
  const [sev, setSev] = useState<(typeof SEVERITIES)[number]>("all");
  const [device, setDevice] = useState("all");
  const [codes, setCodes] = useState<string[]>([]);
  const [page, setPage] = useState(0);

  const load = useCallback(async () => {
    try {
      const list = await apiGet<{ gateways: { gateway_id: string }[] }>("/gateways");
      const resps = await Promise.all(
        list.gateways.map((g) =>
          apiGet<EventsResponse>(`/gateways/${g.gateway_id}/events?limit=200`)
            .then((r) => ({ gw: g.gateway_id, r }))
            .catch(() => null),
        ),
      );
      setRest(
        resps.filter(Boolean).flatMap((x) => x!.r.events.map((e) => ({ ...e, gateway_id: x!.gw }))),
      );
    } catch {
      setRest([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const all = useMemo(() => {
    const seen = new Set<string>();
    return [...sessionEvents, ...rest]
      .filter((e) => {
        const k = `${e.gateway_id}|${e.received_at}|${e.code}|${e.message ?? ""}`;
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      })
      .sort((a, b) => Date.parse(b.received_at) - Date.parse(a.received_at));
  }, [sessionEvents, rest]);

  const codeUniverse = useMemo(() => [...new Set(all.map((e) => e.code))].sort(), [all]);
  const devices = useMemo(() => [...new Set(all.map((e) => e.gateway_id))].sort(), [all]);

  const filtered = useMemo(() => {
    const cutoff = Date.now() - RANGES[rangeIx].s * 1000;
    return all.filter(
      (e) =>
        Date.parse(e.received_at) >= cutoff &&
        (sev === "all" || (e.severity ?? "info") === sev) &&
        (device === "all" || e.gateway_id === device) &&
        (codes.length === 0 || codes.includes(e.code)),
    );
  }, [all, rangeIx, sev, device, codes]);

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const toggleCode = (c: string) => {
    setPage(0);
    setCodes((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  };

  return (
    <div className="main-inner">
      <div className="page-head">
        <div>
          <h1 className="page-title">Sự kiện</h1>
          <p className="page-sub">
            {filtered.length} sự kiện đang lọc · {RANGES[rangeIx].label} gần nhất
          </p>
        </div>
        <button
          className="btn"
          onClick={() => {
            void load();
            refreshLive();
          }}
        >
          <RefreshCw size={14} aria-hidden="true" /> Làm mới
        </button>
      </div>

      <div className="panel" style={{ padding: "16px 18px" }}>
        <div
          style={{ display: "grid", gap: 16, gridTemplateColumns: "auto 1fr", alignItems: "start" }}
        >
          <div>
            <p className="filter-label">Severity</p>
            <div className="pill-row">
              {SEVERITIES.map((s) => (
                <button
                  key={s}
                  className={`pill${sev === s ? " pill-on" : ""}`}
                  onClick={() => {
                    setSev(s);
                    setPage(0);
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="filter-label">Device</p>
            <select
              className="pill"
              value={device}
              onChange={(e) => {
                setDevice(e.target.value);
                setPage(0);
              }}
              style={{ background: "var(--panel-2)", color: "var(--text)" }}
            >
              <option value="all">All devices</option>
              {devices.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div style={{ marginTop: 16 }}>
          <p className="filter-label">Codes</p>
          <div className="pill-row">
            {codeUniverse.map((c) => (
              <button
                key={c}
                className={`pill pill-mono${codes.includes(c) ? " pill-on" : ""}`}
                onClick={() => toggleCode(c)}
              >
                {c}
              </button>
            ))}
            {!codeUniverse.length ? <span className="dim">chưa có code nào</span> : null}
          </div>
        </div>
      </div>

      <div className="pill-row" style={{ justifyContent: "flex-end", marginBottom: 14 }}>
        {RANGES.map((r, i) => (
          <button
            key={r.label}
            className={`pill pill-mono${i === rangeIx ? " pill-on" : ""}`}
            onClick={() => {
              setRangeIx(i);
              setPage(0);
            }}
          >
            {r.label}
          </button>
        ))}
      </div>

      <div className="panel" style={{ paddingBottom: 6 }}>
        <table className="table">
          <thead>
            <tr>
              <th>time</th>
              <th>severity</th>
              <th>code</th>
              <th>device</th>
              <th>message</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((e, i) => (
              <tr key={i}>
                <td className="num dim">{fmtClock(e.received_at)}</td>
                <td className={sevClass(e.severity)}>{e.severity ?? "info"}</td>
                <td className="mono">{e.code}</td>
                <td className="mono dim">{e.gateway_id}</td>
                <td>{e.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!pageRows.length ? (
          <div className="empty-box">
            <Inbox size={26} aria-hidden="true" />
            <p>
              <strong>Không có sự kiện khớp bộ lọc hiện tại</strong>
            </p>
            <p>Thử mở rộng khoảng thời gian, đổi severity, hoặc bỏ chọn code.</p>
          </div>
        ) : null}
      </div>

      <div className="page-head" style={{ margin: "4px 0 0", alignItems: "center" }}>
        <span className="dim">
          Trang {page + 1} / {pages}
        </span>
        <div className="pill-row">
          <button className="btn" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            <ChevronLeft size={14} aria-hidden="true" /> Trước
          </button>
          <button
            className="btn"
            disabled={page >= pages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            Sau <ChevronRight size={14} aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}

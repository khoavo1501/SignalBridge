import { Gauge, RefreshCw, Thermometer, Zap } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { apiGet } from "../api/client";
import type { HistoryResponse, LatestSlave } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import { useLive } from "../state/LiveContext";
import { fmtAgo, fmtNum } from "../state/format";

// cách 1 chống lag: mọi cửa sổ đều agg phía backend (raw 1h = ~10k điểm SVG → giật)
const RANGES = [
  { label: "15m", s: 900, agg: "2s", aggMs: 2_000 },
  { label: "1h", s: 3_600, agg: "5s", aggMs: 5_000 },
  { label: "6h", s: 21_600, agg: "10s", aggMs: 10_000 },
  { label: "24h", s: 86_400, agg: "1m", aggMs: 60_000 },
];

const ICONS = [Thermometer, Gauge, Zap];
const TAIL_CAP = 2400; // trần ô cửa sổ trượt (6h/10s = 2160)

interface TailPoint {
  t: number; // mốc đã bucket theo ô agg — khớp lưới cửa sổ trượt
  raw: number; // tsMs thật của tick cuối trong ô — giữ độ tươi chính xác cho badge
  values: Record<string, number>;
}

interface ChartRow {
  t: number;
  [signal: string]: number | null;
}

export default function SlaveDetailPage() {
  const { id = "", addr = "1" } = useParams();
  const slaveAddr = Number(addr);
  const { nowMs, badge, subscribeTelemetry } = useLive();
  const [rangeIx, setRangeIx] = useState(1);
  const [latest, setLatest] = useState<LatestSlave | null>(null);
  const [hist, setHist] = useState<HistoryResponse | null>(null);
  const [universe, setUniverse] = useState<string[]>([]);
  const [selKeys, setSelKeys] = useState<string[] | null>(null); // null = mặc định từ latest
  const [tail, setTail] = useState<TailPoint[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const selKeyStr = (selKeys ?? universe).join(",");
  const selRef = useRef<string[] | null>(selKeys);
  selRef.current = selKeys;

  const load = useCallback(async () => {
    setErr(null);
    try {
      const l = await apiGet<{ slaves: LatestSlave[] }>(`/gateways/${id}/latest`);
      const s = l.slaves.find((x) => x.slave_addr === slaveAddr) ?? null;
      setLatest(s);
      const numeric = s?.signals
        ? Object.entries(s.signals)
            .filter(([k, v]) => typeof v === "number" && !k.startsWith("di_"))
            .map(([k]) => k)
        : [];
      setUniverse(numeric);
      const keys = selKeyStr ? selKeyStr.split(",") : [];
      const from = new Date(Date.now() - RANGES[rangeIx].s * 1000).toISOString();
      const h = await apiGet<HistoryResponse>(
        `/gateways/${id}/history?slave=${slaveAddr}&signals=${(keys.length ? keys : ["ai_raw"]).join(",")}&agg=${RANGES[rangeIx].agg}&from=${from}&limit=20000`,
      );
      setHist(h);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [id, slaveAddr, rangeIx, selKeyStr]);

  useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(t);
  }, [load]);

  const interval = RANGES[rangeIx].aggMs;

  // M7 DoD: "WS cập nhật chart đang hiển thị" — telemetry frame nối vào đuôi chart, latest-wins trong ô agg hiện tại
  useEffect(
    () =>
      subscribeTelemetry((tick) => {
        if (tick.gateway_id !== id || tick.slave_addr !== slaveAddr) return;
        const keys = selRef.current ?? universe;
        const values: Record<string, number> = {};
        for (const [k, v] of Object.entries(tick.signals)) {
          if (typeof v === "number" && (keys.length === 0 || keys.includes(k))) values[k] = v;
        }
        if (!Object.keys(values).length) return;
        const bucket = Math.floor(tick.tsMs / interval) * interval;
        setTail((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.t > bucket) return prev; // tick muộn hơn tới trước — bỏ
          if (last && last.t === bucket)
            return [...prev.slice(0, -1), { t: bucket, raw: tick.tsMs, values }];
          return [...prev, { t: bucket, raw: tick.tsMs, values }].slice(-TAIL_CAP);
        });
      }),
    [subscribeTelemetry, id, slaveAddr, universe, interval],
  );

  // Cửa sổ trượt: lưới thời gian cố định [start, anchor] — anchor nhảy đúng 1 lần mỗi ô agg (không mỗi giây)
  const anchor = Math.floor(nowMs / interval) * interval;
  const nSlots = Math.min(Math.floor((RANGES[rangeIx].s * 1000) / interval), TAIL_CAP);
  const gridStart = anchor - (nSlots - 1) * interval;

  // Signal đã có data: các ô trước điểm đầu = 0 (user yêu cầu); gap giữa chừng vẫn null để đứt đoạn (hc0)
  const { rows, counts, nulls } = useMemo(() => {
    const byT = new Map<number, Record<string, number>>();
    for (const s of hist?.series ?? []) {
      for (const p of s.points) {
        const t = Math.floor(Date.parse(p.t) / interval) * interval;
        if (t < gridStart || t > anchor) continue;
        const row = byT.get(t) ?? {};
        row[s.signal] = p.v;
        byT.set(t, row);
      }
    }
    for (const tp of tail) {
      if (tp.t < gridStart || tp.t > anchor) continue;
      const row = byT.get(tp.t) ?? {};
      for (const [k, v] of Object.entries(tp.values)) row[k] = v;
      byT.set(tp.t, row);
    }
    const firstT = new Map<string, number>();
    const cnt = new Map<string, number>();
    for (const [t, vals] of byT) {
      for (const [k, v] of Object.entries(vals)) {
        if (!Number.isFinite(v)) continue;
        cnt.set(k, (cnt.get(k) ?? 0) + 1);
        const cur = firstT.get(k);
        if (cur === undefined || t < cur) firstT.set(k, t);
      }
    }
    const grid: ChartRow[] = [];
    const nulls = new Map<string, number>();
    for (let i = 0; i < nSlots; i++) {
      const t = gridStart + i * interval;
      const vals = byT.get(t);
      const row: ChartRow = { t };
      for (const [sig, fb] of firstT) {
        const v = vals?.[sig];
        if (v == null && t >= fb) nulls.set(sig, (nulls.get(sig) ?? 0) + 1);
        row[sig] = v ?? (t < fb ? 0 : null);
      }
      grid.push(row);
    }
    return { rows: grid, counts: cnt, nulls };
  }, [hist, tail, interval, anchor, gridStart, nSlots]);

  const shownSignals = useMemo(() => {
    const fromHist = (hist?.series ?? []).filter((s) => s.points.length > 0).map((s) => s.signal);
    const fromTail = new Set(tail.flatMap((tp) => Object.keys(tp.values)));
    return [...new Set([...(selKeys ?? universe), ...fromHist, ...fromTail])];
  }, [hist, tail, selKeys, universe]);

  const liveValue = useCallback(
    (signal: string): number | null => {
      for (let i = tail.length - 1; i >= 0; i--) {
        const v = tail[i].values[signal];
        if (v !== undefined) return v;
      }
      const lv = latest?.signals?.[signal];
      return typeof lv === "number" ? lv : null;
    },
    [tail, latest],
  );

  const gwBadge = badge(id) ?? "offline";
  // lastSeen = max(Redis /latest, mốc tail WS gần nhất) — badge không nhấp "trễ" giữa hai lần REST 15 s khi WS vẫn streaming
  const lastSeenMs = Math.max(
    latest?.received_at ? Date.parse(latest.received_at) : 0,
    tail.length ? tail[tail.length - 1].raw : 0,
  );
  const slaveFresh = lastSeenMs > 0 && nowMs - lastSeenMs < 10_000;
  const shownBadge = gwBadge === "offline" ? "offline" : slaveFresh ? "online" : "stale";
  const name = `${id}::${latest?.name ?? `slave${slaveAddr}`}`;

  const toggleSignal = (k: string) => {
    const cur = selKeys ?? universe;
    const next = cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k];
    if (next.length) setSelKeys(next);
  };

  return (
    <div className="main-inner">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/">Bảng điều khiển</Link>
        <span aria-hidden="true">›</span>
        <Link to={`/gateways/${id}`}>{id}</Link>
        <span aria-hidden="true">›</span>
        <span className="mono">{name.split("::")[1]}</span>
      </nav>
      <div className="page-head">
        <div>
          <h1 className="page-title mono">{name}</h1>
          <p className="page-sub">
            slave {slaveAddr} · REST 15 s + WS realtime · {rows.length} mốc thời gian
          </p>
        </div>
        <button className="btn" onClick={() => void load()}>
          <RefreshCw size={14} aria-hidden="true" /> Làm mới
        </button>
      </div>

      {err ? (
        <div className="error-box">
          <span>Không tải được dữ liệu: {err}</span>
        </div>
      ) : null}

      <div className="panel">
        <div className="panel-head">
          <h2 className="panel-title" style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {name.split("::")[1]}
            <StatusBadge badge={shownBadge} />
          </h2>
          <span className="panel-note">
            last seen {fmtAgo(lastSeenMs ? new Date(lastSeenMs).toISOString() : null, nowMs)}
          </span>
        </div>
        <div className="gw-stats" style={{ borderTop: "none" }}>
          {(selKeys ?? universe).slice(0, 3).map((k) => (
            <div key={k}>
              <span className="gw-stat-label">{k}</span>
              <span className="gw-stat-value mono">
                {fmtNum(liveValue(k))}
                <span className="raw-tag">(raw)</span>
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="pill-row" role="group" aria-label="Khoảng thời gian">
        {RANGES.map((r, i) => (
          <button
            key={r.label}
            className={`pill pill-mono${i === rangeIx ? " pill-on" : ""}`}
            onClick={() => {
              setRangeIx(i);
              setTail([]);
            }}
          >
            {r.label}
          </button>
        ))}
      </div>

      {universe.length > 0 ? (
        <div className="pill-row" role="group" aria-label="Chọn signal">
          <span className="filter-label">signal</span>
          {universe.map((k) => (
            <button
              key={k}
              className={`pill pill-mono${(selKeys ?? universe).includes(k) ? " pill-on" : ""}`}
              onClick={() => toggleSignal(k)}
            >
              {k}
            </button>
          ))}
        </div>
      ) : null}

      <div className="chart-grid">
        {shownSignals.map((signal, i) => {
          const Icon = ICONS[i % ICONS.length];
          const nPoints = counts.get(signal) ?? 0;
          const nGaps = nulls.get(signal) ?? 0;
          return (
            <div key={signal} className="chart-card">
              <div className="chart-head">
                <span className="chart-name">
                  <Icon size={15} className="amber" aria-hidden="true" />
                  {signal}
                </span>
                <span className="chart-value">
                  {fmtNum(liveValue(signal))}
                  <span className="raw-tag">raw</span>
                </span>
              </div>
              <p className="chart-sub">
                {nPoints} điểm · {RANGES[rangeIx].label}
                {nGaps ? ` · ${nGaps} mốc đứt gãy` : ""}
              </p>
              {nPoints >= 2 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -14 }}>
                    <CartesianGrid stroke="var(--line-soft)" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="t"
                      type="number"
                      scale="time"
                      domain={[gridStart, anchor]}
                      allowDataOverflow
                      tickFormatter={(t: number) =>
                        new Date(t).toLocaleTimeString("vi-VN", {
                          hour: "2-digit",
                          minute: "2-digit",
                          hour12: false,
                        })
                      }
                      stroke="var(--dim)"
                      tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
                      minTickGap={40}
                    />
                    <YAxis
                      stroke="var(--dim)"
                      tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
                      domain={["auto", "auto"]}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "var(--panel-2)",
                        border: "1px solid var(--line)",
                        borderRadius: 8,
                        fontFamily: "var(--font-mono)",
                        fontSize: 12,
                      }}
                      labelFormatter={(t) => new Date(Number(t)).toLocaleString("vi-VN")}
                      formatter={(v) => [`${String(v)} (raw)`, signal]}
                    />
                    <Line
                      type="monotone"
                      dataKey={signal}
                      stroke="var(--amber)"
                      strokeWidth={1.6}
                      dot={false}
                      isAnimationActive={false}
                      connectNulls={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="empty-box" style={{ padding: "48px 0" }}>
                  <p>Không có dữ liệu trong khoảng này.</p>
                </div>
              )}
            </div>
          );
        })}
        {!hist && !err ? <div className="skeleton" style={{ minHeight: 260 }} /> : null}
      </div>
    </div>
  );
}

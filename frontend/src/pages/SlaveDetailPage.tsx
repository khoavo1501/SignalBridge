import { Gauge, RefreshCw, Thermometer, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
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

const RANGES = [
  { label: "15m", s: 900, agg: "raw" },
  { label: "1h", s: 3600, agg: "raw" },
  { label: "6h", s: 21600, agg: "10s" },
  { label: "24h", s: 86400, agg: "1m" },
];

const ICONS = [Thermometer, Gauge, Zap];

export default function SlaveDetailPage() {
  const { id = "", addr = "1" } = useParams();
  const slaveAddr = Number(addr);
  const { nowMs, badge } = useLive();
  const [rangeIx, setRangeIx] = useState(1);
  const [latest, setLatest] = useState<LatestSlave | null>(null);
  const [hist, setHist] = useState<HistoryResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const l = await apiGet<{ slaves: LatestSlave[] }>(`/gateways/${id}/latest`);
      const s = l.slaves.find((x) => x.slave_addr === slaveAddr) ?? null;
      setLatest(s);
      const keys = s?.signals
        ? Object.entries(s.signals)
            .filter(([k, v]) => typeof v === "number" && !k.startsWith("di_"))
            .map(([k]) => k)
        : ["ai_raw"];
      if (!keys.length) keys.push("ai_raw");
      const from = new Date(Date.now() - RANGES[rangeIx].s * 1000).toISOString();
      setHist(
        await apiGet<HistoryResponse>(
          `/gateways/${id}/history?slave=${slaveAddr}&signals=${keys.join(",")}&agg=${RANGES[rangeIx].agg}&from=${from}`,
        ),
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [id, slaveAddr, rangeIx]);

  useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(t);
  }, [load]);

  const gwBadge = badge(id) ?? "offline";
  const slaveFresh =
    latest?.received_at !== null &&
    latest?.received_at !== undefined &&
    nowMs - Date.parse(latest.received_at) < 10_000;
  const shownBadge = gwBadge === "offline" ? "offline" : slaveFresh ? "online" : "stale";
  const name = `${id}::${latest?.name ?? `slave${slaveAddr}`}`;

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
          <p className="page-sub">slave {slaveAddr} · cập nhật tự động 15 s</p>
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
          <span className="panel-note">last seen {fmtAgo(latest?.received_at, nowMs)}</span>
        </div>
        <div className="gw-stats" style={{ borderTop: "none" }}>
          {(hist?.series ?? []).slice(0, 3).map((s) => (
            <div key={s.signal}>
              <span className="gw-stat-label">{s.signal}</span>
              <span className="gw-stat-value mono">
                {fmtNum(
                  typeof latest?.signals?.[s.signal] === "number"
                    ? (latest.signals[s.signal] as number)
                    : null,
                )}
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
            onClick={() => setRangeIx(i)}
          >
            {r.label}
          </button>
        ))}
      </div>

      <div className="chart-grid">
        {(hist?.series ?? []).map((s, i) => {
          const Icon = ICONS[i % ICONS.length];
          const data = s.points.map((p) => ({ t: Date.parse(p.t), v: p.v }));
          return (
            <div key={s.signal} className="chart-card">
              <div className="chart-head">
                <span className="chart-name">
                  <Icon size={15} className="amber" aria-hidden="true" />
                  {s.signal}
                </span>
                <span className="chart-value">
                  {typeof latest?.signals?.[s.signal] === "number"
                    ? fmtNum(latest.signals[s.signal] as number)
                    : "—"}
                  <span className="raw-tag">raw</span>
                </span>
              </div>
              <p className="chart-sub">
                {s.points.length} điểm · {RANGES[rangeIx].label}
              </p>
              {data.length >= 2 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -14 }}>
                    <CartesianGrid stroke="var(--line-soft)" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="t"
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
                      formatter={(v) => [`${String(v)} (raw)`, s.signal]}
                    />
                    <Line
                      type="monotone"
                      dataKey="v"
                      stroke="var(--amber)"
                      strokeWidth={1.6}
                      dot={false}
                      isAnimationActive={false}
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

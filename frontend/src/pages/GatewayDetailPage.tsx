import { ArrowLeft, ChevronRight, Cpu, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiGet, ApiError } from "../api/client";
import type { EventsResponse, GatewayRow, LatestSlave } from "../api/types";
import StatCard from "../components/StatCard";
import StatusBadge from "../components/StatusBadge";
import { useLive } from "../state/LiveContext";
import { fmtAgo, fmtClock, fmtNum } from "../state/format";

interface Detail {
  gw: GatewayRow;
  slaves: LatestSlave[];
  events: EventsResponse["events"];
}

const SIGNAL_COLS = ["ai_raw", "di_word", "hc0", "c0"];

export default function GatewayDetailPage() {
  const { id = "" } = useParams();
  const { live, nowMs, thresholdS, badge } = useLive();
  const [data, setData] = useState<Detail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [gw, latest, ev] = await Promise.all([
        apiGet<GatewayRow>(`/gateways/${id}`),
        apiGet<{ gateway_id: string; slaves: LatestSlave[] }>(`/gateways/${id}/latest`),
        apiGet<EventsResponse>(`/gateways/${id}/events?limit=100`),
      ]);
      setData({ gw, slaves: latest.slaves, events: ev.events });
    } catch (e) {
      setErr(
        e instanceof ApiError && e.code === "gateway_not_found"
          ? "gateway chưa đăng ký"
          : String(e instanceof Error ? e.message : e),
      );
    }
  }, [id]);

  useEffect(() => {
    void load();
    // latest/events là snapshot REST — tự refresh để badge slave khớp độ tươi thật qua WS
    const t = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(t);
  }, [load]);

  const g = live[id];
  const gwBadge = badge(id) ?? "offline";
  const cutoff = Date.now() - 3600_000;
  const warnings = (data?.events ?? []).filter(
    (e) =>
      (e.severity === "warning" || e.severity === "critical") &&
      Date.parse(e.received_at) >= cutoff,
  );
  const lastSyncMs = g?.lastSeenMs ?? null;
  const slavesOnline = (data?.slaves ?? []).filter(
    (s) => s.received_at && nowMs - Date.parse(s.received_at) < thresholdS * 1000,
  ).length;

  return (
    <div className="main-inner">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/">Bảng điều khiển</Link>
        <span aria-hidden="true">›</span>
        <span className="mono">{id}</span>
      </nav>
      <div className="page-head">
        <div>
          <h1 className="page-title">{data?.gw.display_name ?? id}</h1>
          <p className="page-sub">
            {slavesOnline} / {data?.gw.slaves.length ?? 0} PLC trực tuyến
          </p>
        </div>
        <button className="btn" onClick={() => void load()}>
          <RefreshCw size={14} aria-hidden="true" /> Làm mới
        </button>
      </div>

      {err ? (
        <div className="error-box">
          <span>Lỗi tải gateway: {err}</span>
          <Link to="/" className="btn">
            <ArrowLeft size={14} aria-hidden="true" /> Về dashboard
          </Link>
        </div>
      ) : null}

      <div className="panel">
        <div className="panel-head">
          <h2 className="panel-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Cpu size={16} className="amber" aria-hidden="true" />
            {id}
          </h2>
          <div className="pill-row">
            {warnings.length > 0 ? (
              <span className="badge badge-stale">
                <i className="badge-dot" aria-hidden="true" />
                {warnings.length} cảnh báo
              </span>
            ) : null}
            <StatusBadge badge={gwBadge} />
          </div>
        </div>
        <div className="meta-strip" style={{ padding: "10px 0 4px" }}>
          <span>
            fw <span className="mono">{data?.gw.meta.fw_version ?? g?.fw_version ?? "—"}</span>
          </span>
          <span>
            hw <span className="mono">{data?.gw.meta.hw_version ?? "—"}</span>
          </span>
          <span>
            ip <span className="mono">{data?.gw.meta.ip ?? "—"}</span>
          </span>
          <span>
            mac <span className="mono">{data?.gw.meta.mac ?? "—"}</span>
          </span>
          <span>
            adapter <span className="mono">{data?.gw.adapter_key ?? "—"}</span>
          </span>
        </div>
      </div>

      <div className="stat-row">
        <StatCard
          label="Gateway"
          value={
            <span
              className={gwBadge === "online" ? "ok" : gwBadge === "stale" ? "amber" : "bad"}
              style={{ fontSize: 26 }}
            >
              {gwBadge === "online" ? "trực tuyến" : gwBadge === "stale" ? "dữ liệu trễ" : "ngắt"}
            </span>
          }
          tone={gwBadge === "online" ? "ok" : gwBadge === "stale" ? "amber" : "bad"}
        />
        <StatCard
          label="PLC trực tuyến"
          value={`${slavesOnline} / ${data?.gw.slaves.length ?? 0}`}
          tone="ok"
        />
        <StatCard
          label="Cảnh báo 1 giờ"
          value={warnings.length}
          tone={warnings.length ? "bad" : "ok"}
        />
        <StatCard
          label="Đồng bộ cuối"
          value={
            <span style={{ fontSize: 24 }}>
              {lastSyncMs ? fmtClock(new Date(lastSyncMs).toISOString()) : "—"}
            </span>
          }
          sub={fmtAgo(lastSyncMs ? new Date(lastSyncMs).toISOString() : null, nowMs)}
        />
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2 className="panel-title">Danh sách PLC</h2>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>plc</th>
              <th>trạng thái</th>
              <th>seq</th>
              {SIGNAL_COLS.map((c) => (
                <th key={c}>{c} (raw)</th>
              ))}
              <th>last seen</th>
              <th aria-label="chi tiết" />
            </tr>
          </thead>
          <tbody>
            {(data?.slaves ?? []).map((s) => {
              const fresh = s.received_at && nowMs - Date.parse(s.received_at) < thresholdS * 1000;
              const slaveBadge = gwBadge === "offline" ? "offline" : fresh ? "online" : "stale";
              return (
                <tr key={s.slave_addr}>
                  <td>
                    <Link className="mono" to={`/gateways/${id}/slaves/${s.slave_addr}`}>
                      {id}::{s.name ?? `slave${s.slave_addr}`}
                    </Link>
                  </td>
                  <td>
                    <StatusBadge badge={slaveBadge} />
                  </td>
                  <td className="num dim">{fmtNum(s.seq)}</td>
                  {SIGNAL_COLS.map((c) => (
                    <td key={c} className="num">
                      {typeof s.signals?.[c] === "number" ? fmtNum(s.signals[c] as number) : "—"}
                    </td>
                  ))}
                  <td className="num dim">{fmtAgo(s.received_at, nowMs)}</td>
                  <td>
                    <Link
                      to={`/gateways/${id}/slaves/${s.slave_addr}`}
                      aria-label="mở chi tiết PLC"
                    >
                      <ChevronRight size={15} className="dim" aria-hidden="true" />
                    </Link>
                  </td>
                </tr>
              );
            })}
            {!data?.slaves.length ? (
              <tr>
                <td colSpan={SIGNAL_COLS.length + 5} className="dim">
                  Chưa có slave nào được khai báo (gateway gửi payload `info` để tự đăng ký slave).
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {warnings.length > 0 ? (
        <div className="panel panel-accent">
          <div className="panel-head">
            <h2 className="panel-title">{warnings.length} cảnh báo gần đây</h2>
            <span className="panel-note">{warnings[0]?.severity ?? "warning"}</span>
          </div>
          <table className="table">
            <tbody>
              {warnings.slice(0, 5).map((e, i) => (
                <tr key={i}>
                  <td className="mono bad" style={{ width: 220 }}>
                    {e.code}
                  </td>
                  <td>{e.message}</td>
                  <td className="num dim" style={{ textAlign: "right" }}>
                    {fmtClock(e.received_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ margin: "10px 0 4px" }}>
            <Link className="amber" to="/events">
              Xem tất cả sự kiện ↗
            </Link>
          </p>
        </div>
      ) : null}
    </div>
  );
}

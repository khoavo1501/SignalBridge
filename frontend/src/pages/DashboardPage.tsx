import { Inbox, Network, RefreshCw, Server, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { apiGet } from "../api/client";
import type { EventsResponse } from "../api/types";
import GatewayCard from "../components/GatewayCard";
import StatCard from "../components/StatCard";
import { useLive } from "../state/LiveContext";

const WARN_WINDOW_S = 3600;

export default function DashboardPage() {
  const { live, sparks, nowMs, loading, error, refresh, badge } = useLive();
  const [warnings, setWarnings] = useState<number | null>(null);
  const gws = Object.values(live);

  useEffect(() => {
    let dead = false;
    const ids = Object.keys(live);
    if (!ids.length) return;
    Promise.all(
      ids.map((id) => apiGet<EventsResponse>(`/gateways/${id}/events?limit=100`).catch(() => null)),
    ).then((resps) => {
      if (dead) return;
      const cutoff = Date.now() - WARN_WINDOW_S * 1000;
      const n = resps
        .filter(Boolean)
        .flatMap((r) => r!.events)
        .filter(
          (e) =>
            (e.severity === "warning" || e.severity === "critical") &&
            Date.parse(e.received_at) >= cutoff,
        ).length;
      setWarnings(n);
    });
    return () => {
      dead = true;
    };
  }, [live]);

  const online = gws.filter((g) => badge(g.gateway_id) === "online").length;
  const slavesTotal = gws.reduce((a, g) => a + g.slave_count, 0);
  const slavesOnline = gws
    .filter((g) => badge(g.gateway_id) === "online")
    .reduce((a, g) => a + g.slave_count, 0);
  const pct = gws.length ? Math.round((online / gws.length) * 100) : 0;

  return (
    <div className="main-inner">
      <div className="page-head">
        <div>
          <h1 className="page-title">Bảng điều khiển</h1>
          <p className="page-sub">
            {online} / {gws.length} gateway trực tuyến · {pct}%
          </p>
        </div>
        <button className="btn" onClick={refresh}>
          <RefreshCw size={14} aria-hidden="true" /> Làm mới
        </button>
      </div>

      {error ? (
        <div className="error-box">
          <span>Không tải được dữ liệu: {error}</span>
          <button className="btn" onClick={refresh}>
            Thử lại
          </button>
        </div>
      ) : null}

      <div className="stat-row">
        <StatCard
          label="Gateway trực tuyến"
          value={`${online} / ${gws.length}`}
          sub={`${pct}% đang hoạt động`}
          icon={<Network size={16} aria-hidden="true" />}
        />
        <StatCard
          label="PLC trực tuyến"
          value={`${slavesOnline} / ${slavesTotal}`}
          sub={`${slavesTotal - slavesOnline} ngoài phục vụ`}
          icon={<Server size={16} aria-hidden="true" />}
        />
        <StatCard
          label="Cảnh báo 1 giờ qua"
          value={warnings === null ? "…" : warnings}
          sub={warnings ? "cần chú ý" : "all clear"}
          tone={warnings ? (warnings > 0 ? "bad" : "ok") : "amber"}
          icon={<TriangleAlert size={16} aria-hidden="true" />}
        />
      </div>

      {loading && !gws.length ? (
        <div className="gw-grid">
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      ) : gws.length ? (
        <div className="gw-grid">
          {gws.map((g) => (
            <GatewayCard
              key={g.gateway_id}
              gw={g}
              badge={badge(g.gateway_id) ?? "offline"}
              spark={sparks[g.gateway_id] ?? []}
              nowMs={nowMs}
            />
          ))}
        </div>
      ) : (
        <div className="empty-box panel">
          <Inbox size={28} aria-hidden="true" />
          <p>
            <strong>Chưa có gateway nào</strong>
          </p>
          <p>Chạy gateway simulator hoặc đăng ký gateway mới (admin UI có ở M8).</p>
        </div>
      )}
    </div>
  );
}

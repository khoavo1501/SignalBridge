import { ChevronRight, Cpu } from "lucide-react";
import { Link } from "react-router-dom";

import type { Badge } from "../api/types";
import type { LiveGw } from "../state/live";
import { fmtAgo, fmtNum } from "../state/format";
import Sparkline from "./Sparkline";
import StatusBadge from "./StatusBadge";

export default function GatewayCard({
  gw,
  badge,
  spark,
  nowMs,
}: {
  gw: LiveGw;
  badge: Badge;
  spark: number[];
  nowMs: number;
}) {
  const metric = gw.metrics.find((m) => m.key === "ai_raw") ?? gw.metrics[0];
  return (
    <Link to={`/gateways/${gw.gateway_id}`} className="gw-card card-tone-online" data-badge={badge}>
      <div className="gw-head">
        <h3 className="gw-title">{gw.display_name}</h3>
        <StatusBadge badge={badge} />
      </div>
      <p className="gw-id mono">{gw.gateway_id}</p>
      <Sparkline values={spark} />
      <div className="gw-stats">
        <div>
          <span className="gw-stat-label">slave</span>
          <span className="gw-stat-value mono">{fmtNum(gw.slave_count)}</span>
        </div>
        <div>
          <span className="gw-stat-label">firmware</span>
          <span className="gw-stat-value mono">{gw.fw_version ?? "—"}</span>
        </div>
        <div>
          <span className="gw-stat-label">{metric ? `${metric.key} (raw)` : "telemetry"}</span>
          <span className="gw-stat-value mono">
            {metric
              ? fmtNum(metric.value)
              : fmtAgo(gw.lastSeenMs ? new Date(gw.lastSeenMs).toISOString() : null, nowMs)}
          </span>
        </div>
      </div>
      <div className="gw-foot">
        <span className="gw-foot-id">
          <Cpu size={13} aria-hidden="true" />
          {gw.gateway_id}
        </span>
        <ChevronRight size={15} aria-hidden="true" />
      </div>
    </Link>
  );
}

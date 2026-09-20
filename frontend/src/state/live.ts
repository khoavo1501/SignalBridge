import type { Badge, MetricEntry, Summary, WsFrame } from "../api/types";
import { isInfo, isStatus, isSummary, isTelemetry } from "../api/types";

export interface LiveGw {
  gateway_id: string;
  display_name: string;
  state: string; // broker state từ Redis status hash: online | offline | unknown
  lastSeenMs: number | null; // server receive time của telemetry cuối
  fw_version: string | null;
  slave_count: number;
  metrics: MetricEntry[];
}

export type LiveMap = Record<string, LiveGw>;

export function fromSummary(s: Summary): LiveMap {
  const out: LiveMap = {};
  for (const g of s.gateways) {
    out[g.gateway_id] = {
      gateway_id: g.gateway_id,
      display_name: g.display_name,
      state: g.state,
      lastSeenMs: g.last_telemetry_at ? Date.parse(g.last_telemetry_at) : null,
      fw_version: g.fw_version,
      slave_count: g.slave_count,
      metrics: g.primary_metrics,
    };
  }
  return out;
}

function mergeTelemetry(g: LiveGw, signals: Record<string, boolean | number>): LiveGw {
  const metrics = g.metrics.map((m) => ({ ...m }));
  for (const [key, value] of Object.entries(signals)) {
    if (key.startsWith("di_") || typeof value === "boolean") continue; // card chỉ hiện analog/counter
    const hit = metrics.find((m) => m.key === key);
    if (hit) {
      hit.raw = value;
      hit.value = value; // Q2: chưa có công thức scale — value = raw
    } else {
      metrics.push({
        key,
        display_name: key,
        unit: null,
        raw: value,
        value,
        scaled: false,
      });
    }
  }
  return { ...g, metrics };
}

// Reducer thuần cho mọi frame WS — trả [map mới, threshold nếu frame mang thông tin]
export function applyFrame(prev: LiveMap, thresholdS: number, frame: WsFrame): [LiveMap, number] {
  if (isSummary(frame)) {
    return [fromSummary(frame.data), frame.data.stale_threshold_s];
  }
  const gwId =
    isTelemetry(frame) || isStatus(frame) || isInfo(frame) ? frame.data.gateway_id : null;
  if (gwId === null || !(gwId in prev)) {
    // gateway lạ (mới đăng ký) hoặc frame event/diag — trang tổng quan chưa cần; snapshot kế tiếp sẽ đồng bộ
    return [prev, thresholdS];
  }
  const g = prev[gwId];
  if (isTelemetry(frame)) {
    const ts = Date.parse(frame.data.received_at);
    const next: LiveGw = {
      ...mergeTelemetry(g, frame.data.signals),
      lastSeenMs: g.lastSeenMs !== null && ts < g.lastSeenMs ? g.lastSeenMs : ts,
    };
    return [{ ...prev, [gwId]: next }, thresholdS];
  }
  if (isStatus(frame)) {
    return [{ ...prev, [gwId]: { ...g, state: frame.data.state } }, thresholdS];
  }
  if (isInfo(frame)) {
    const next: LiveGw = {
      ...g,
      fw_version: frame.data.fw_version ?? g.fw_version,
      slave_count: frame.data.slaves ? frame.data.slaves.length : g.slave_count,
    };
    return [{ ...prev, [gwId]: next }, thresholdS];
  }
  return [prev, thresholdS];
}

// Badge tính lại phía client mỗi nhịp — DoD: stale trong ≤ threshold + 1 nhịp UI, offline nhanh qua status frame
export function badgeOf(g: LiveGw, nowMs: number, thresholdS: number): Badge {
  if (g.state !== "online") return "offline";
  if (g.lastSeenMs !== null && nowMs - g.lastSeenMs < thresholdS * 1000) return "online";
  return "stale";
}

// Shapes khớp contract REST §4.1 / WS envelope §4.2 (SignalBridge backend)

export type Badge = "online" | "stale" | "offline";

export interface MetricEntry {
  key: string;
  display_name: string;
  unit: string | null;
  raw: number | null;
  value: number | null;
  scaled: boolean;
}

export interface GatewaySummary {
  gateway_id: string;
  display_name: string;
  badge: Badge;
  state: string;
  fresh: boolean;
  last_telemetry_at: string | null;
  fw_version: string | null;
  slave_count: number;
  primary_metrics: MetricEntry[];
}

export interface Summary {
  generated_at: string;
  stale_threshold_s: number;
  gateways: GatewaySummary[];
}

export interface TelemetryData {
  kind: "telemetry";
  gateway_id: string;
  slave_addr: number;
  seq: number | null;
  signals: Record<string, boolean | number>;
  received_at: string;
}

export interface StatusData {
  kind: "status";
  gateway_id: string;
  state: "online" | "offline";
  reason?: string | null;
  received_at: string;
}

export interface InfoData {
  kind: "info";
  gateway_id: string;
  fw_version?: string | null;
  slaves?: { addr: number; name: string | null }[];
  received_at: string;
}

export interface EventItem {
  code: string;
  severity: string | null;
  message: string | null;
  source: string | null;
  slave_addr: number | null;
}

export interface EventData extends NormalizedBase {
  kind: "event";
  events: EventItem[];
}

export interface DiagData extends NormalizedBase {
  kind: "diag";
  poll_cycle_ms: number | null;
  uptime_s: number | null;
  slave_stats: { addr: number; ok: number | null; fail: number | null }[];
  tx_packets: number | null;
  tx_failures: number | null;
  mqtt_reconnect: number | null;
}

interface NormalizedBase {
  gateway_id: string;
  received_at: string;
  adapter_key: string;
}

// REST /gateways/{id}/events row
export interface EventRow extends EventItem {
  received_at: string;
}

export interface EventsResponse {
  events: EventRow[];
  next_before: string | null;
}

// REST /gateways (meta + slaves + state)
export interface SlaveRow {
  id?: number;
  slave_addr: number;
  name: string | null;
}

export interface GatewayRow {
  id: number;
  gateway_id: string;
  display_name: string;
  adapter_key: string;
  enabled: boolean;
  state: string;
  meta: {
    fw_version: string | null;
    hw_version: string | null;
    ip: string | null;
    mac: string | null;
  };
  slaves: SlaveRow[];
}

export interface LatestSlave {
  slave_addr: number;
  name: string | null;
  received_at: string | null;
  seq: number | null;
  signals: Record<string, boolean | number> | null;
}

export interface HistoryPoint {
  t: string;
  v: number;
}

export interface HistorySeries {
  signal: string;
  unit: string | null;
  points: HistoryPoint[];
}

export interface HistoryResponse {
  gateway_id: string;
  slave_addr: number;
  series: HistorySeries[];
  count: number;
}

export interface DiagResponse {
  gateway_id: string;
  latest: {
    received_at: string;
    poll_cycle_ms: number | null;
    uptime_s: number | null;
    tx_packets: number | null;
    tx_failures: number | null;
    mqtt_reconnect: number | null;
    slave_stats: { addr: number; ok: number | null; fail: number | null }[];
  } | null;
  note: string;
}

export interface WsFrame {
  type: "snapshot" | "telemetry" | "status" | "event" | "info" | "diag" | "error";
  ts: string;
  // data = NormalizedMessage serialize (hoặc Summary với snapshot) — narrow theo type ở consumer
  data:
    | Summary
    | TelemetryData
    | StatusData
    | InfoData
    | EventData
    | DiagData
    | Record<string, unknown>;
}

export const isSummary = (frame: WsFrame): frame is WsFrame & { data: Summary } =>
  frame.type === "snapshot";

export const isTelemetry = (frame: WsFrame): frame is WsFrame & { data: TelemetryData } =>
  frame.type === "telemetry" && typeof (frame.data as TelemetryData).gateway_id === "string";

export const isStatus = (frame: WsFrame): frame is WsFrame & { data: StatusData } =>
  frame.type === "status" && typeof (frame.data as StatusData).state === "string";

export const isInfo = (frame: WsFrame): frame is WsFrame & { data: InfoData } =>
  frame.type === "info" && Array.isArray((frame.data as InfoData).slaves);

export const isEvent = (frame: WsFrame): frame is WsFrame & { data: EventData } =>
  frame.type === "event" && Array.isArray((frame.data as EventData).events);

export const isDiag = (frame: WsFrame): frame is WsFrame & { data: DiagData } =>
  frame.type === "diag" && typeof (frame.data as DiagData).gateway_id === "string";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { apiGet } from "../api/client";
import type { DiagData, EventRow, Summary, WsFrame } from "../api/types";
import { isDiag, isEvent, isSummary, isTelemetry } from "../api/types";
import { useGatewaySocket } from "../hooks/useGatewaySocket";
import { applyFrame, badgeOf, fromSummary, type LiveMap } from "./live";

const SPARK_CAP = 90;
const EVENT_CAP = 300;
const DIAG_CAP = 60;

export interface SessionEvent extends EventRow {
  gateway_id: string;
}

export interface SessionDiag extends DiagData {
  gw: string;
}

// Khung telemetry đẩy lên WS — trang SlaveDetail nối vào chart đang hiển thị (M7)
export interface TelemetryTick {
  gateway_id: string;
  slave_addr: number;
  seq: number | null;
  tsMs: number;
  signals: Record<string, boolean | number>;
}

interface LiveState {
  live: LiveMap;
  thresholdS: number;
  connected: boolean;
  nowMs: number;
  sparks: Record<string, number[]>;
  sessionEvents: SessionEvent[];
  sessionDiags: SessionDiag[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
  badge: (gwId: string) => ReturnType<typeof badgeOf> | null;
  subscribeTelemetry: (cb: (t: TelemetryTick) => void) => () => void;
}

const Ctx = createContext<LiveState | null>(null);

export function LiveProvider({ children }: { children: ReactNode }) {
  const [live, setLive] = useState<LiveMap>({});
  const [thresholdS, setThresholdS] = useState(10);
  const [sparks, setSparks] = useState<Record<string, number[]>>({});
  const [sessionEvents, setSessionEvents] = useState<SessionEvent[]>([]);
  const [sessionDiags, setSessionDiags] = useState<SessionDiag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(Date.now());
  const seededRef = useRef(false);
  const thresholdRef = useRef(thresholdS);
  thresholdRef.current = thresholdS;
  const feedSubs = useRef(new Set<(t: TelemetryTick) => void>());

  const subscribeTelemetry = useCallback((cb: (t: TelemetryTick) => void) => {
    feedSubs.current.add(cb);
    return () => {
      feedSubs.current.delete(cb);
    };
  }, []);

  const loadRest = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await apiGet<Summary>("/dashboard/summary");
      setLive(fromSummary(s));
      setThresholdS(s.stale_threshold_s);
      if (!seededRef.current) {
        seededRef.current = true;
        for (const g of s.gateways) {
          const key = g.primary_metrics[0]?.key;
          if (!key) continue;
          const from = new Date(Date.now() - 180_000).toISOString();
          apiGet<{ series: { points: { v: number }[] }[] }>(
            `/gateways/${g.gateway_id}/history?slave=1&signals=${key}&agg=10s&from=${from}`,
          )
            .then((h) =>
              setSparks((p) => ({
                ...p,
                [g.gateway_id]: h.series[0]?.points.map((pt) => pt.v).slice(-SPARK_CAP) ?? [],
              })),
            )
            .catch(() => {
              /* influx trống — sparkline đầy dần qua WS */
            });
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "lỗi không xác định");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRest();
  }, [loadRest]);

  useEffect(() => {
    const t = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  const onFrame = useCallback((frame: WsFrame) => {
    if (isSummary(frame)) {
      setLive(fromSummary(frame.data));
      setThresholdS(frame.data.stale_threshold_s);
      return;
    }
    if (isTelemetry(frame)) {
      setLive((prev) => applyFrame(prev, thresholdRef.current, frame)[0]);
      const { gateway_id, signals } = frame.data;
      const tick: TelemetryTick = {
        gateway_id,
        slave_addr: frame.data.slave_addr ?? 1,
        seq: frame.data.seq ?? null,
        tsMs: Date.parse(frame.data.received_at),
        signals,
      };
      for (const cb of feedSubs.current) cb(tick);
      const hit = Object.entries(signals).find(
        ([k, v]) => typeof v === "number" && !k.startsWith("di_"),
      );
      if (hit) {
        setSparks((prev) => ({
          ...prev,
          [gateway_id]: [...(prev[gateway_id] ?? []), hit[1] as number].slice(-SPARK_CAP),
        }));
      }
      return;
    }
    setLive((prev) => applyFrame(prev, thresholdRef.current, frame)[0]);
    if (isEvent(frame)) {
      const data = frame.data;
      const rows: SessionEvent[] = data.events.map((ev) => ({
        ...ev,
        gateway_id: data.gateway_id,
        received_at: data.received_at,
      }));
      if (rows.length) setSessionEvents((prev) => [...rows, ...prev].slice(0, EVENT_CAP));
    }
    if (isDiag(frame)) {
      const d = frame.data;
      setSessionDiags((prev) => [{ ...d, gw: d.gateway_id }, ...prev].slice(0, DIAG_CAP));
    }
  }, []);

  const connected = useGatewaySocket(onFrame);

  const badge = useCallback(
    (gwId: string) => {
      const g = live[gwId];
      return g ? badgeOf(g, nowMs, thresholdS) : null;
    },
    [live, nowMs, thresholdS],
  );

  const value = useMemo<LiveState>(
    () => ({
      live,
      thresholdS,
      connected,
      nowMs,
      sparks,
      sessionEvents,
      sessionDiags,
      loading,
      error,
      refresh: () => void loadRest(),
      badge,
      subscribeTelemetry,
    }),
    [
      live,
      thresholdS,
      connected,
      nowMs,
      sparks,
      sessionEvents,
      sessionDiags,
      loading,
      error,
      loadRest,
      badge,
      subscribeTelemetry,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- hook đồng hành với provider (pattern context chuẩn)
export function useLive(): LiveState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLive phải nằm trong LiveProvider");
  return v;
}

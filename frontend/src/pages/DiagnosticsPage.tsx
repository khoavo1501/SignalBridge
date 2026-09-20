import { RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { apiGet } from "../api/client";
import type { DiagResponse, GatewayRow, HistoryResponse } from "../api/types";
import { useLive } from "../state/LiveContext";
import { fmtAgo, fmtClock, fmtNum } from "../state/format";

interface SeqGap {
  pct: number; // % seq vắng mặt trong cửa sổ 1 h (R1: chỉ ước lượng — telemetry QoS 0)
  lost: number; // số bước seq nhảy
  expected: number; // last - first + 1
  last: number;
}

interface DiagRow {
  gateway_id: string;
  state: string;
  received_at: string | null;
  poll_cycle_ms: number | null;
  tx_packets: number | null;
  tx_failures: number | null;
  mqtt_reconnect: number | null;
  uptime_s: number | null;
  seqGap: SeqGap | null;
}

async function fetchSeqGap(gatewayId: string): Promise<SeqGap | null> {
  const from = new Date(Date.now() - 3600_000).toISOString();
  try {
    const h = await apiGet<HistoryResponse>(
      `/gateways/${gatewayId}/history?slave=1&signals=seq&agg=raw&from=${from}`,
    );
    const pts = h.series[0]?.points.map((p) => Number(p.v)).filter(Number.isFinite) ?? [];
    if (pts.length < 2) return null;
    let lost = 0;
    for (let i = 1; i < pts.length; i++) lost += Math.max(0, pts[i] - pts[i - 1] - 1);
    const expected = pts[pts.length - 1] - pts[0] + 1;
    if (expected < 1) return null;
    return { pct: (lost / expected) * 100, lost, expected, last: pts[pts.length - 1] };
  } catch {
    return null; // influx trống / gateway chưa có telemetry
  }
}

export default function DiagnosticsPage() {
  const { sessionDiags, nowMs, badge } = useLive();
  const [rows, setRows] = useState<DiagRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const list = await apiGet<{ gateways: GatewayRow[] }>("/gateways");
      const resps = await Promise.all(
        list.gateways.map(async (g) => {
          const d = await apiGet<DiagResponse>(`/gateways/${g.gateway_id}/diag`).catch(() => null);
          return {
            gateway_id: g.gateway_id,
            state: g.state,
            received_at: d?.latest?.received_at ?? null,
            poll_cycle_ms: d?.latest?.poll_cycle_ms ?? null,
            tx_packets: d?.latest?.tx_packets ?? null,
            tx_failures: d?.latest?.tx_failures ?? null,
            mqtt_reconnect: d?.latest?.mqtt_reconnect ?? null,
            uptime_s: d?.latest?.uptime_s ?? null,
            seqGap: await fetchSeqGap(g.gateway_id),
            note: d?.note ?? null,
          };
        }),
      );
      setRows(resps);
      setNote(resps.find((r) => r.note)?.note ?? null);
      setSelected((s) => s ?? resps[0]?.gateway_id ?? null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const history = sessionDiags.filter((d) => d.gw === selected);

  return (
    <div className="main-inner">
      <div className="page-head">
        <div>
          <h1 className="page-title">Chẩn đoán</h1>
          <p className="page-sub">sức khỏe poll của device · diag gần nhất mỗi gateway</p>
        </div>
        <button className="btn" onClick={() => void load()}>
          <RefreshCw size={14} aria-hidden="true" /> Làm mới
        </button>
      </div>

      {err ? (
        <div className="error-box">
          <span>Lỗi tải chẩn đoán: {err}</span>
        </div>
      ) : null}

      <div className="panel">
        <div className="panel-head">
          <h2 className="panel-title">Device</h2>
          {note ? (
            <span className="panel-note">Q7 mở: tx_* là biến đếm Modbus phía firmware</span>
          ) : null}
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>device</th>
              <th>diag cuối</th>
              <th>trạng thái</th>
              <th>poll (ms)</th>
              <th>tx packets</th>
              <th>tx fail</th>
              <th>mqtt reconn</th>
              <th>uptime (s)</th>
              <th title="R1: telemetry QoS 0 — nhảy seq chỉ là ước lượng mất gói">seq gap 1h*</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.gateway_id}
                className="row-link"
                onClick={() => setSelected(r.gateway_id)}
                style={selected === r.gateway_id ? { background: "var(--panel-2)" } : undefined}
              >
                <td className="mono">{r.gateway_id}</td>
                <td className="num dim">
                  {r.received_at
                    ? `${fmtClock(r.received_at)} · ${fmtAgo(r.received_at, nowMs)}`
                    : "—"}
                </td>
                <td>
                  <span className={badge(r.gateway_id) === "online" ? "ok" : "bad"}>
                    {badge(r.gateway_id) ?? r.state}
                  </span>
                </td>
                <td className="num">{fmtNum(r.poll_cycle_ms)}</td>
                <td className="num">{fmtNum(r.tx_packets)}</td>
                <td className={`num${r.tx_failures ? " amber" : ""}`}>{fmtNum(r.tx_failures)}</td>
                <td className="num">{fmtNum(r.mqtt_reconnect)}</td>
                <td className="num">{fmtNum(r.uptime_s)}</td>
                <td
                  className={`num${r.seqGap && r.seqGap.lost > 0 ? " amber" : ""}`}
                  title={
                    r.seqGap
                      ? `seq hiện tại ${r.seqGap.last} · nhảy ${r.seqGap.lost}/${r.seqGap.expected} bước trong 1 h`
                      : "chưa đủ dữ liệu seq"
                  }
                >
                  {r.seqGap ? `${r.seqGap.pct.toFixed(2).replace(".", ",")}%` : "—"}
                </td>
              </tr>
            ))}
            {!rows.length ? (
              <tr>
                <td colSpan={9} className="dim">
                  Chưa có gateway nào.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {selected ? (
        <div className="panel">
          <div className="panel-head">
            <h2 className="panel-title">Diag history · {selected}</h2>
            <div className="pill-row">
              <span className="panel-note">{history.length} dòng (phiên này)</span>
              <button
                className="pill"
                onClick={() => setSelected(null)}
                aria-label="đóng bảng lịch sử"
              >
                <X size={13} aria-hidden="true" />
              </button>
            </div>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>time</th>
                <th>poll (ms)</th>
                <th>tx ok / fail</th>
                <th>uptime (s)</th>
              </tr>
            </thead>
            <tbody>
              {history.map((d, i) => (
                <tr key={i}>
                  <td className="num dim">{fmtClock(d.received_at)}</td>
                  <td className="num">{fmtNum(d.poll_cycle_ms)}</td>
                  <td className="num">
                    {fmtNum(d.tx_packets)} <span className="dim">/</span>{" "}
                    <span className={d.tx_failures ? "amber" : ""}>{fmtNum(d.tx_failures)}</span>
                  </td>
                  <td className="num">{fmtNum(d.uptime_s)}</td>
                </tr>
              ))}
              {!history.length ? (
                <tr>
                  <td colSpan={4} className="dim">
                    Chưa nhận diag frame nào trong phiên — chờ chu kỳ diag của gateway (simulator:
                    `--diag-interval-s`).
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

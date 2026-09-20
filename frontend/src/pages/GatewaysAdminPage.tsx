import { AlertTriangle, KeyRound, Link2Off, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError, apiGet, apiSend } from "../api/client";
import type { AdaptersResponse, GatewayRow, UnknownGateway } from "../api/types";
import { useLive } from "../state/LiveContext";

function errText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === "gateway_exists") return "gateway_id này đã tồn tại — chọn id khác.";
    if (e.code === "invalid_gateway_id")
      return "gateway_id không hợp lệ: 3–64 ký tự, chữ/số/_/-, không bắt đầu bằng ký tự đặc biệt.";
    if (e.code === "invalid_adapter_key") return "adapter_key không có trong registry.";
    return `${e.code}: ${e.message}`;
  }
  return e instanceof Error ? e.message : "lỗi không xác định";
}

export default function GatewaysAdminPage() {
  const { refresh: refreshLive } = useLive();
  const [rows, setRows] = useState<GatewayRow[]>([]);
  const [unknown, setUnknown] = useState<UnknownGateway[]>([]);
  const [adapters, setAdapters] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // gateway_id đang PATCH/DELETE

  const [formGw, setFormGw] = useState("");
  const [formAdapter, setFormAdapter] = useState("");
  const [formName, setFormName] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [formOk, setFormOk] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [gw, un, ad] = await Promise.all([
        apiGet<{ gateways: GatewayRow[] }>("/gateways"),
        apiGet<{ gateways: UnknownGateway[] }>("/gateways/unknown").catch(() => ({
          gateways: [] as UnknownGateway[],
        })),
        apiGet<AdaptersResponse>("/adapters").catch(() => ({ adapters: [] })),
      ]);
      setRows(gw.gateways);
      setUnknown(un.gateways);
      setAdapters(ad.adapters.map((a) => a.key));
    } catch (e) {
      setLoadError(errText(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const afterMutation = () => {
    void load();
    refreshLive();
  };

  const patch = async (gatewayId: string, fields: Record<string, string | boolean>) => {
    setBusy(gatewayId);
    try {
      await apiSend<GatewayRow>("PATCH", `/gateways/${gatewayId}`, fields);
      setRowError(null);
      afterMutation();
    } catch (e) {
      setRowError(`Không cập nhật được ${gatewayId} — ${errText(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const create = async (gatewayId: string, adapterKey: string, displayName?: string) => {
    setBusy(gatewayId ?? "form");
    setFormError(null);
    try {
      await apiSend<GatewayRow>("POST", "/gateways", {
        gateway_id: gatewayId,
        adapter_key: adapterKey,
        display_name: displayName || null,
      });
      setFormOk(`Đã đăng ký ${gatewayId}. Gateway mới sẽ gửi telemetry về trong giây lát.`);
      setFormGw("");
      setFormName("");
      afterMutation();
    } catch (e) {
      setFormError(errText(e));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (gw: GatewayRow) => {
    const slaves = gw.slaves.length;
    const msg =
      `Xóa gateway ${gw.gateway_id}?` +
      ` Xóa dòng PG (cascade ${slaves} slave) và các Redis key latest/status/last_seen.` +
      " Dữ liệu InfluxDB (history/diag) được GIỮ LẠI (Q5). Không thể hoàn tác.";
    if (!window.confirm(msg)) return;
    setBusy(gw.gateway_id);
    try {
      const r = await apiSend<{ deleted: boolean; redis_keys_removed: number }>(
        "DELETE",
        `/gateways/${gw.gateway_id}`,
      );
      setFormOk(`Đã xóa ${gw.gateway_id} (${r.redis_keys_removed} Redis key đã dọn).`);
      setRowError(null);
      afterMutation();
    } catch (e) {
      setRowError(`Không xóa được ${gw.gateway_id} — ${errText(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const defaultAdapter = adapters.includes("s7200_v1") ? "s7200_v1" : (adapters[0] ?? "");

  return (
    <div className="main-inner">
      <div className="page-head">
        <div>
          <h1 className="page-title">Quản trị gateway</h1>
          <p className="page-sub">
            đăng ký / sửa / bật-tắt / xóa gateway · {rows.length} gateway đã đăng ký
            {unknown.length ? ` · ${unknown.length} chưa đăng ký` : ""}
          </p>
        </div>
        <button className="btn" onClick={() => void load()}>
          <RefreshCw size={14} aria-hidden="true" /> Làm mới
        </button>
      </div>

      {loadError ? (
        <div className="error-box">
          <AlertTriangle size={16} aria-hidden="true" /> {loadError}
        </div>
      ) : null}
      {formError ? (
        <div className="error-box">
          <AlertTriangle size={16} aria-hidden="true" /> {formError}
        </div>
      ) : null}
      {rowError ? (
        <div className="error-box">
          <AlertTriangle size={16} aria-hidden="true" /> {rowError}
        </div>
      ) : null}
      {formOk ? (
        <div className="ok-box">
          <KeyRound size={16} aria-hidden="true" /> {formOk}
        </div>
      ) : null}

      <div className="panel" style={{ padding: "16px 18px", marginBottom: 18 }}>
        <h2 className="panel-title" style={{ marginTop: 0 }}>
          Thêm gateway mới
        </h2>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label style={{ display: "grid", gap: 4 }}>
            <span className="filter-label">gateway_id</span>
            <input
              className="input"
              value={formGw}
              onChange={(e) => setFormGw(e.target.value.trim())}
              placeholder="GW_S7200_02"
              spellCheck={false}
            />
          </label>
          <label style={{ display: "grid", gap: 4 }}>
            <span className="filter-label">adapter_key</span>
            <select
              className="input"
              value={formAdapter || defaultAdapter}
              onChange={(e) => setFormAdapter(e.target.value)}
            >
              {(adapters.length ? adapters : ["s7200_v1"]).map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "grid", gap: 4, flex: 1, minWidth: 180 }}>
            <span className="filter-label">display_name (tùy chọn)</span>
            <input
              className="input"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder="để trống = dùng gateway_id"
            />
          </label>
          <button
            className="btn"
            disabled={!formGw || busy !== null}
            onClick={() => void create(formGw, formAdapter || defaultAdapter, formName)}
          >
            <Plus size={14} aria-hidden="true" /> Đăng ký
          </button>
        </div>
        <p className="dim" style={{ margin: "10px 0 0", fontSize: 12.5 }}>
          id hợp lệ: 3–64 ký tự `[A-Za-z0-9_-]`, không bắt đầu bằng `_`/`-`. Gateway tự đăng ký qua
          telemetry (persist upsert) — form này dành cho việc đặt tên/sửa adapter trước khi thiết bị
          lên sóng.
        </p>
      </div>

      <div className="panel" style={{ paddingBottom: 6, marginBottom: 18 }}>
        <table className="table">
          <thead>
            <tr>
              <th>gateway_id</th>
              <th>display_name</th>
              <th>adapter</th>
              <th>state</th>
              <th>slaves</th>
              <th>enabled</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((g) => (
              <tr key={g.gateway_id}>
                <td className="mono">
                  <Link to={`/gateways/${g.gateway_id}`}>{g.gateway_id}</Link>
                </td>
                <td>
                  <DisplayNameCell
                    initial={g.display_name}
                    disabled={busy === g.gateway_id}
                    onSave={(v) => void patch(g.gateway_id, { display_name: v })}
                  />
                </td>
                <td className="mono dim">{g.adapter_key}</td>
                <td className={g.state === "online" ? "ok" : "dim"}>{g.state}</td>
                <td className="num">{g.slaves.length}</td>
                <td>
                  <button
                    className="btn"
                    style={{ padding: "4px 10px" }}
                    disabled={busy === g.gateway_id}
                    onClick={() => void patch(g.gateway_id, { enabled: !g.enabled })}
                  >
                    {g.enabled ? "tắt" : "bật"}
                  </button>
                </td>
                <td style={{ textAlign: "right" }}>
                  <button
                    className="btn"
                    style={{ padding: "4px 10px" }}
                    disabled={busy === g.gateway_id}
                    onClick={() => void remove(g)}
                    title="Xóa gateway (PG + Redis; Influx giữ lại)"
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && !rows.length ? (
          <div className="empty-box">
            <Link2Off size={26} aria-hidden="true" />
            <p>
              <strong>Chưa có gateway nào đăng ký</strong>
            </p>
            <p>Dùng form ở trên, hoặc chờ telemetry từ thiết bị tự đăng ký.</p>
          </div>
        ) : null}
      </div>

      {unknown.length ? (
        <div className="panel" style={{ padding: "16px 18px" }}>
          <h2 className="panel-title" style={{ marginTop: 0 }}>
            Gateway thấy trên bus nhưng chưa đăng ký
          </h2>
          <p className="dim" style={{ fontSize: 12.5, margin: "0 0 12px" }}>
            pipeline ghi nhận payload của các id này nhưng DB chưa có dòng — thêm nhanh để dashboard
            hiển thị chúng.
          </p>
          <div style={{ display: "grid", gap: 8 }}>
            {unknown.map((u) => (
              <div
                key={u.gateway_id}
                style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}
              >
                <span className="mono">{u.gateway_id}</span>
                <span className="dim num" style={{ fontSize: 12 }}>
                  last seen {u.last_seen}
                </span>
                <button
                  className="btn"
                  style={{ padding: "4px 10px" }}
                  disabled={busy !== null}
                  onClick={() => void create(u.gateway_id, defaultAdapter)}
                >
                  <Plus size={14} aria-hidden="true" /> thêm (adapter {defaultAdapter})
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function DisplayNameCell({
  initial,
  disabled,
  onSave,
}: {
  initial: string;
  disabled: boolean;
  onSave: (v: string) => void;
}) {
  const [v, setV] = useState(initial);
  useEffect(() => setV(initial), [initial]);
  const dirty = v.trim() !== initial.trim();
  return (
    <input
      className="input"
      style={{ width: 220, padding: "4px 8px" }}
      value={v}
      disabled={disabled}
      onChange={(e) => setV(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter" && dirty) onSave(v.trim());
      }}
      onBlur={() => {
        if (dirty && v.trim()) onSave(v.trim());
      }}
    />
  );
}

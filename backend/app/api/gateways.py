import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.common import iso_z, parse_iso, require_gateway, require_slave
from app.api.errors import ApiError
from app.deps import get_current_user
from app.ingestion import pipeline
from app.parsers import registry
from app.stores import influx_query, postgres, redis_reader, redis_writer

router = APIRouter(prefix="/api/v1", tags=["gateways"], dependencies=[Depends(get_current_user)])

log = logging.getLogger("signalbridge.api.gateways")

AGG_RE = re.compile(r"^\d+(ms|s|m|h|d)$")
GATEWAY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")
MAX_WINDOW_S = 7 * 24 * 3600  # §4.4: history quá 7 ngày → 400


@router.get("/gateways")
async def list_gateways() -> dict:
    gateways = await postgres.fetch_gateways(include_disabled=True)
    out = []
    for gw in gateways:
        slaves = await postgres.fetch_slaves(gw["id"])
        status_hash = await redis_reader.read_status(gw["gateway_id"])
        gw["slaves"] = slaves
        gw["state"] = (status_hash or {}).get("state", "unknown")
        gw["meta"] = {k: gw.pop(k) for k in ("fw_version", "hw_version", "ip", "mac")}
        out.append(gw)
    return {"gateways": out}


class GatewayCreate(BaseModel):
    gateway_id: str
    adapter_key: str
    display_name: str | None = None


@router.post("/gateways", status_code=201)
async def create_gateway(body: GatewayCreate) -> dict:
    if not GATEWAY_ID_RE.match(body.gateway_id):
        raise ApiError(
            400,
            "invalid_gateway_id",
            "gateway_id 3–64 ký tự: chữ/số/_/-, bắt đầu bằng chữ hoặc số",
        )
    if registry.get_by_key(body.adapter_key) is None:
        raise ApiError(
            422,
            "invalid_adapter_key",
            f"adapter_key {body.adapter_key} không có trong registry",
        )
    gw = await postgres.insert_gateway(
        body.gateway_id, body.display_name or body.gateway_id, body.adapter_key
    )
    if gw is None:
        raise ApiError(409, "gateway_exists", f"gateway {body.gateway_id} đã được đăng ký")
    return gw


# PHẢI đặt trước route /gateways/{gateway_id} — không thì "unknown" bị nuốt làm gateway_id
@router.get("/gateways/unknown")
async def unknown_gateways() -> dict:
    seen = pipeline.unknown_seen_snapshot()
    out = []
    for gid, last_seen in sorted(seen.items()):
        if await postgres.fetch_gateway(gid) is None:
            out.append({"gateway_id": gid, "last_seen": last_seen})
    return {"gateways": out}


@router.get("/gateways/{gateway_id}")
async def get_gateway(gateway_id: str) -> dict:
    gw = await require_gateway(gateway_id)
    slaves = await postgres.fetch_slaves(gw["id"])
    status_hash = await redis_reader.read_status(gateway_id)
    gw["slaves"] = slaves
    gw["state"] = (status_hash or {}).get("state", "unknown")
    gw["meta"] = {k: gw.pop(k) for k in ("fw_version", "hw_version", "ip", "mac")}
    return gw


class GatewayPatch(BaseModel):
    display_name: str | None = None
    adapter_key: str | None = None
    enabled: bool | None = None


@router.patch("/gateways/{gateway_id}")
async def patch_gateway(gateway_id: str, body: GatewayPatch) -> dict:
    fields = body.model_dump(exclude_none=True)
    if "adapter_key" in fields and registry.get_by_key(fields["adapter_key"]) is None:
        raise ApiError(
            422,
            "invalid_adapter_key",
            f"adapter_key {fields['adapter_key']} không có trong registry",
        )
    gw = await postgres.patch_gateway(gateway_id, fields)
    if gw is None:
        raise ApiError(404, "gateway_not_found", f"gateway {gateway_id} chưa đăng ký")
    return gw


@router.delete("/gateways/{gateway_id}")
async def delete_gateway(gateway_id: str) -> dict:
    gw = await require_gateway(gateway_id)
    slaves = await postgres.fetch_slaves(gw["id"])
    if await postgres.delete_gateway(gateway_id) is None:
        raise ApiError(404, "gateway_not_found", f"gateway {gateway_id} chưa đăng ký")
    # §4.1: xóa cascade Postgres, dọn key Redis; dữ liệu Influx GIỮ NGUYÊN (retention 60 ngày Q5)
    try:
        removed = await redis_writer.delete_gateway(gateway_id, [s["slave_addr"] for s in slaves])
    except Exception as exc:
        log.warning("delete gateway %s: redis cleanup failed (keys còn sót): %s", gateway_id, exc)
        removed = 0
    return {"deleted": gateway_id, "redis_keys_removed": removed}


@router.get("/adapters")
async def list_adapters() -> dict:
    return {"adapters": [{"key": a.key} for a in registry.ADAPTERS]}


@router.get("/gateways/{gateway_id}/latest")
async def latest(gateway_id: str) -> dict:
    gw = await require_gateway(gateway_id)
    slaves = await postgres.fetch_slaves(gw["id"])
    entries = []
    for s in slaves:
        entry = await redis_reader.read_latest(gateway_id, s["slave_addr"]) or {
            "slave_addr": s["slave_addr"],
            "received_at": None,
            "seq": None,
            "signals": None,
        }
        entry["slave_addr"] = s["slave_addr"]
        entry["name"] = s["name"]
        entries.append(entry)
    return {"gateway_id": gateway_id, "slaves": entries}


@router.get("/gateways/{gateway_id}/history")
async def history(
    gateway_id: str,
    slave: int = 1,
    signals: str = "",
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    agg: str = "raw",
    limit: int = 5000,
) -> dict:
    gw = await require_gateway(gateway_id)
    await require_slave(gw["id"], slave)
    keys = [k.strip() for k in signals.split(",") if k.strip()]
    if not keys:
        raise ApiError(400, "invalid_request", "tham số signals bắt buộc, vd ?signals=ai_raw,hc0")
    if agg != "raw" and not AGG_RE.match(agg):
        raise ApiError(
            400, "invalid_request", f"agg phải là raw hoặc duration (10s, 1m...), nhận: {agg}"
        )
    limit = max(1, min(limit, 20000))
    stop = parse_iso("to", to) or datetime.now(UTC)
    start = parse_iso("from", from_) or datetime.fromtimestamp(stop.timestamp() - 3600, UTC)
    if (stop - start).total_seconds() > MAX_WINDOW_S:
        raise ApiError(400, "range_too_large", "cửa sổ history tối đa 7 ngày")
    if start >= stop:
        raise ApiError(400, "invalid_request", "from phải trước to")
    try:
        series = await influx_query.query_history(
            gateway_id, slave, keys, start, stop, agg=None if agg == "raw" else agg, limit=limit
        )
    except Exception as exc:
        raise ApiError(503, "store_unavailable", f"influxdb query failed: {exc}") from exc
    defs = {d["key"]: d for d in await postgres.fetch_signal_defs(gw["id"])}
    out_series = []
    count = 0
    for key in keys:
        points = [{"t": iso_z(t), "v": v} for t, v in series.get(key, [])]
        count += len(points)
        out_series.append({"signal": key, "unit": defs.get(key, {}).get("unit"), "points": points})
    return {"gateway_id": gateway_id, "slave_addr": slave, "series": out_series, "count": count}


@router.get("/gateways/{gateway_id}/events")
async def events(
    gateway_id: str, limit: int = 20, before: str | None = None, code: str | None = None
) -> dict:
    gw = await require_gateway(gateway_id)
    limit = max(1, min(limit, 200))
    before_dt = parse_iso("before", before)
    rows = await postgres.fetch_events(gw["id"], limit + 1, before=before_dt, code=code)
    has_more = len(rows) > limit
    rows = rows[:limit]
    events_out = [
        {
            "received_at": iso_z(r["received_at"]),
            "code": r["code"],
            "severity": r["severity"],
            "message": r["message"],
            "source": r["source"],
            "slave_addr": r["slave_addr"],
        }
        for r in rows
    ]
    next_before = iso_z(rows[-1]["received_at"]) if has_more and rows else None
    return {"events": events_out, "next_before": next_before}


@router.get("/events")
async def events_all(limit: int = 200, before: str | None = None, code: str | None = None) -> dict:
    """M8 backlog: events toàn hệ thống trong một request (UI khỏi lặp theo gateway)."""
    limit = max(1, min(limit, 500))
    before_dt = parse_iso("before", before)
    rows = await postgres.fetch_events_all(limit + 1, before=before_dt, code=code)
    has_more = len(rows) > limit
    rows = rows[:limit]
    events_out = [
        {
            "gateway_id": r["gateway_id"],
            "received_at": iso_z(r["received_at"]),
            "code": r["code"],
            "severity": r["severity"],
            "message": r["message"],
            "source": r["source"],
            "slave_addr": r["slave_addr"],
        }
        for r in rows
    ]
    next_before = iso_z(rows[-1]["received_at"]) if has_more and rows else None
    return {"events": events_out, "next_before": next_before}


@router.get("/gateways/{gateway_id}/diag")
async def diag(gateway_id: str) -> dict:
    await require_gateway(gateway_id)
    try:
        latest = await influx_query.query_diag_latest(gateway_id)
    except Exception as exc:
        raise ApiError(503, "store_unavailable", f"influxdb query failed: {exc}") from exc
    payload = None
    if latest:
        f = latest["fields"]
        payload = {
            "received_at": iso_z(latest["received_at"]),
            "poll_cycle_ms": f.get("poll_cycle_ms"),
            "uptime_s": f.get("uptime_s"),
            "tx_packets": f.get("tx_packets"),
            "tx_failures": f.get("tx_failures"),
            "mqtt_reconnect": f.get("mqtt_reconnect"),
            "slave_stats": latest["slave_stats"],
        }
    return {
        "gateway_id": gateway_id,
        "latest": payload,
        "note": "tx_packets/tx_failures là biến đếm Modbus phía firmware (Q7 mở — docs/payloads)",
    }

import json
import logging

import sqlalchemy as sa

from app.parsers.base import Diag, GatewayEvent, GatewayInfo, NormalizedMessage, Status, Telemetry
from app.stores import redis_writer
from app.stores.influx_writer import diag_point, telemetry_point
from app.stores.influx_writer import writer as influx_writer
from app.stores.postgres import get_engine
from app.ws import hub as ws_hub

log = logging.getLogger("signalbridge.persist")

counters: dict[str, int] = {"pg_errors": 0, "status_events": 0, "pg_skipped_unregistered": 0}


async def persist_message(msg: NormalizedMessage) -> None:
    # M5: sau khi ghi stores thì phát lên WS hub (§4.2) — telemetry có throttle, còn lại gửi ngay
    if isinstance(msg, Telemetry):
        influx_writer.enqueue(telemetry_point(msg))
        await _safe(redis_writer.write_telemetry(msg), "redis telemetry")
        await ws_hub.submit_telemetry(msg)  # throttle latest-wins bên trong hub
    elif isinstance(msg, Diag):
        influx_writer.enqueue(diag_point(msg))
        await ws_hub.broadcast_message(msg)
    elif isinstance(msg, Status):
        try:
            changed = await redis_writer.write_status(msg)
        except Exception as exc:
            log.warning("persist: status redis write failed, skip pg event: %s", exc)
            return
        if changed:
            await _record_status_event(msg)
        else:
            log.debug("status unchanged for %s (retain replay/periodic) — no event", msg.gateway_id)
        await ws_hub.broadcast_message(msg)
    elif isinstance(msg, GatewayInfo):
        await _upsert_gateway_info(msg)
        await ws_hub.broadcast_message(msg)  # §4.3: gửi sau upsert để client cập nhật slave list
    elif isinstance(msg, GatewayEvent):
        await _insert_events(msg)
        await ws_hub.broadcast_message(msg)


async def _safe(coro, label: str) -> None:
    try:
        await coro
    except Exception as exc:
        log.warning("persist: %s failed: %s", label, exc)


async def _gateway_pk(conn, gateway_id: str) -> int | None:
    row = await conn.execute(
        sa.text("SELECT id FROM gateways WHERE gateway_id = :gid"), {"gid": gateway_id}
    )
    return row.scalar()


async def _upsert_gateway_info(msg: GatewayInfo) -> None:
    # upsert idempotent: broker replay retain info sau khi backend restart không tạo bản ghi trùng
    try:
        async with get_engine().begin() as conn:
            gw = await conn.execute(
                sa.text("""
                    INSERT INTO gateways
                        (gateway_id, display_name, adapter_key, fw_version, hw_version, ip, mac)
                    VALUES (:gid, :gid, :key, :fw, :hw, :ip, :mac)
                    ON CONFLICT (gateway_id) DO UPDATE SET
                        updated_at = now(),
                        fw_version = COALESCE(EXCLUDED.fw_version, gateways.fw_version),
                        hw_version = COALESCE(EXCLUDED.hw_version, gateways.hw_version),
                        ip = COALESCE(EXCLUDED.ip, gateways.ip),
                        mac = COALESCE(EXCLUDED.mac, gateways.mac)
                    RETURNING id
                    """),
                {
                    "gid": msg.gateway_id,
                    "key": msg.adapter_key,
                    "fw": msg.fw_version,
                    "hw": msg.hw_version,
                    "ip": msg.ip,
                    "mac": msg.mac,
                },
            )
            gw_pk = gw.scalar_one()
            for slave in msg.slaves:
                await conn.execute(
                    sa.text("""
                        INSERT INTO slaves (gateway_id, slave_addr, name)
                        VALUES (:gw, :addr, :name)
                        ON CONFLICT (gateway_id, slave_addr)
                        DO UPDATE SET name = COALESCE(EXCLUDED.name, slaves.name)
                        """),
                    {"gw": gw_pk, "addr": slave.addr, "name": slave.name},
                )
    except Exception as exc:
        counters["pg_errors"] += 1
        log.warning("persist: info upsert failed for %s: %s", msg.gateway_id, exc)


async def _insert_event_row(
    conn, gw_pk: int, *, slave_addr, code, severity, message, source, msg, raw
):
    await conn.execute(
        sa.text("""
            INSERT INTO gateway_events
                (gateway_id, slave_addr, code, severity, message, source, received_at, raw)
            VALUES (:gw, :addr, :code, :sev, :msg, :src, :rat, CAST(:raw AS jsonb))
            """),
        {
            "gw": gw_pk,
            "addr": slave_addr,
            "code": code,
            "sev": severity,
            "msg": message,
            "src": source,
            "rat": msg.received_at,
            "raw": json.dumps(raw, ensure_ascii=False, default=str),
        },
    )


async def _gateway_pk_or_skip(msg: NormalizedMessage, conn) -> int | None:
    gw_pk = await _gateway_pk(conn, msg.gateway_id)
    if gw_pk is None:
        counters["pg_skipped_unregistered"] += 1
        log.warning(
            "persist: gateway %s chưa đăng ký ở gateways — bỏ qua event (không tự seed)",
            msg.gateway_id,
        )
    return gw_pk


async def _record_status_event(msg: Status) -> None:
    try:
        async with get_engine().begin() as conn:
            gw_pk = await _gateway_pk_or_skip(msg, conn)
            if gw_pk is None:
                return
            await _insert_event_row(
                conn,
                gw_pk,
                slave_addr=None,
                code="STATUS_ONLINE" if msg.state == "online" else "STATUS_OFFLINE",
                severity="info",
                message=msg.reason or f"gateway {msg.state}",
                source=None,
                msg=msg,
                raw=msg.model_dump(mode="json"),
            )
        counters["status_events"] += 1
    except Exception as exc:
        counters["pg_errors"] += 1
        log.warning("persist: status event failed for %s: %s", msg.gateway_id, exc)


async def _insert_events(msg: GatewayEvent) -> None:
    try:
        async with get_engine().begin() as conn:
            gw_pk = await _gateway_pk_or_skip(msg, conn)
            if gw_pk is None:
                return
            for item in msg.events:
                await _insert_event_row(
                    conn,
                    gw_pk,
                    slave_addr=item.slave_addr,
                    code=item.code,
                    severity=item.severity or "info",
                    message=item.message,
                    source=item.source,
                    msg=msg,
                    raw=item.model_dump(mode="json"),
                )
    except Exception as exc:
        counters["pg_errors"] += 1
        log.warning("persist: event insert failed for %s: %s", msg.gateway_id, exc)

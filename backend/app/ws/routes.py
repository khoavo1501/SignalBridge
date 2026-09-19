import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.common import iso_z
from app.api.dashboard import build_summary
from app.config import get_settings
from app.ws import hub

log = logging.getLogger("signalbridge.ws")

router = APIRouter(tags=["ws"])


async def _pump(conn: hub.ClientConn, ws: WebSocket) -> None:
    while True:
        await ws.send_json(await conn.queue.get())


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    # §4.5 placeholder: AUTH_ENABLED=true thì bắt buộc ?token= — kiểm JWT gắn vào phase sau
    if get_settings().auth_enabled and not ws.query_params.get("token"):
        await ws.close(code=1008)
        return
    await ws.accept()
    conn = hub.client_hub.register()
    pump = asyncio.create_task(_pump(conn, ws))
    try:
        try:
            data = await build_summary()
            await ws.send_json({"type": "snapshot", "ts": iso_z(datetime.now(UTC)), "data": data})
        except Exception as exc:
            log.warning("ws snapshot failed: %s", exc)
            await ws.send_json(
                {
                    "type": "error",
                    "ts": iso_z(datetime.now(UTC)),
                    "data": {"code": "store_unavailable", "message": str(exc)},
                }
            )
        while True:
            try:
                frame = await ws.receive_json()
            except ValueError:
                continue  # frame không phải JSON — bỏ qua, client chỉ cần gửi subscribe
            if isinstance(frame, dict) and frame.get("type") == "subscribe":
                gateways = frame.get("gateways")
                hub.client_hub.set_gateways(conn, gateways if isinstance(gateways, list) else None)
    except WebSocketDisconnect:
        pass
    finally:
        hub.client_hub.unregister(conn)
        pump.cancel()

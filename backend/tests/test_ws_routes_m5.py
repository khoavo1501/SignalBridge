import time

import pytest
from fastapi import FastAPI, Request
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.ws import hub as hub_mod
from app.ws import routes

SUMMARY = {"generated_at": "2026-09-19T08:00:00Z", "stale_threshold_s": 10, "gateways": []}


def _env(gw: str, kind: str = "telemetry") -> dict:
    return {"type": kind, "ts": "t", "data": {"gateway_id": gw}}


@pytest.fixture
def client(monkeypatch):
    hub_mod.client_hub._conns.clear()
    monkeypatch.setattr(routes, "get_settings", lambda: Settings(auth_enabled=False))

    async def fake_summary():
        return SUMMARY

    monkeypatch.setattr(routes, "build_summary", fake_summary)

    app = FastAPI()
    app.include_router(routes.router)

    @app.post("/pub")
    async def pub(request: Request):
        hub_mod.client_hub.publish(await request.json())  # publish ĐÚNG event loop của app
        return {"ok": True}

    with TestClient(app) as c:
        yield c
    hub_mod.client_hub._conns.clear()


def test_snapshot_is_first_frame_and_no_conn_leak(client):
    with client.websocket_connect("/ws") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "snapshot"
        assert frame["data"] == SUMMARY
        assert frame["ts"].endswith("Z")
    # đóng tab không leak connection (nền tảng cho DoD M6)
    assert hub_mod.client_hub.client_count() == 0


def test_subscribe_filter(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        # chưa gửi subscribe = nhận tất cả (§4.2)
        client.post("/pub", json=_env("A"))
        assert ws.receive_json()["data"]["gateway_id"] == "A"

        ws.send_json({"type": "subscribe", "gateways": ["B"]})
        time.sleep(0.2)  # chờ endpoint xử lý frame subscribe
        client.post("/pub", json=_env("A"))  # bị lọc
        client.post("/pub", json=_env("B"))
        assert ws.receive_json()["data"]["gateway_id"] == "B"

        ws.send_json({"type": "subscribe"})  # thiếu gateways = quay lại tất cả
        time.sleep(0.2)
        client.post("/pub", json=_env("C", "status"))
        got = ws.receive_json()
        assert got["type"] == "status" and got["data"]["gateway_id"] == "C"


def test_malformed_frames_ignored(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # snapshot
        ws.send_text("khong phai json")
        ws.send_json({"type": "ping"})  # kind lạ — bỏ qua
        client.post("/pub", json=_env("A"))
        assert ws.receive_json()["data"]["gateway_id"] == "A"


def test_snapshot_failure_sends_error_frame_then_streams(monkeypatch):
    async def boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(routes, "get_settings", lambda: Settings(auth_enabled=False))
    monkeypatch.setattr(routes, "build_summary", boom)
    app = FastAPI()
    app.include_router(routes.router)

    @app.post("/pub")
    async def pub(request: Request):
        hub_mod.client_hub.publish(await request.json())
        return {"ok": True}

    with (
        TestClient(app) as c,
        c.websocket_connect("/ws") as ws,
    ):
        frame = ws.receive_json()
        assert frame["type"] == "error"
        assert frame["data"]["code"] == "store_unavailable"
        c.post("/pub", json=_env("A"))  # vẫn nhận stream dù snapshot hỏng
        assert ws.receive_json()["data"]["gateway_id"] == "A"


def test_auth_placeholder_requires_token_when_enabled(monkeypatch):
    hub_mod.client_hub._conns.clear()
    monkeypatch.setattr(routes, "get_settings", lambda: Settings(auth_enabled=True))

    async def fake_summary():
        return SUMMARY

    monkeypatch.setattr(routes, "build_summary", fake_summary)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as c:
        with pytest.raises(WebSocketDisconnect):  # thiếu token -> close 1008 trước khi accept
            with c.websocket_connect("/ws"):
                pass
        with c.websocket_connect("/ws?token=jwt-gia") as ws:  # có token placeholder -> nối được
            assert ws.receive_json()["type"] == "snapshot"

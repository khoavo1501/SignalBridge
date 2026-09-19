from datetime import UTC, datetime

import pytest

from app.ingestion import persist
from app.parsers.base import Diag, EventItem, GatewayEvent, GatewayInfo, SlaveRef, Status, Telemetry
from app.stores import redis_writer
from app.ws import hub as hub_mod

T = datetime(2026, 9, 19, 8, 0, 0, tzinfo=UTC)


def _telemetry(slave=1) -> Telemetry:
    return Telemetry(
        gateway_id="G",
        adapter_key="s7200_v1",
        received_at=T,
        slave_addr=slave,
        seq=1,
        signals={"ai_raw": 1},
        raw={},
    )


@pytest.fixture
def spy(monkeypatch):
    """Chặn broadcast + stores, trả về (frames, order) để kiểm chứng routing M5."""
    frames = []
    order = []

    async def fake_broadcast(msg):
        frames.append(hub_mod.make_envelope(msg))

    monkeypatch.setattr(hub_mod, "broadcast_message", fake_broadcast)
    monkeypatch.setattr(hub_mod, "submit_telemetry", fake_broadcast)  # gate throttle test ở hub
    monkeypatch.setattr(persist.influx_writer, "enqueue", lambda p: order.append("influx"))
    return frames, order


async def test_telemetry_persist_first_then_submit_to_throttle(spy, monkeypatch):
    frames, order = spy

    async def fake_write_telemetry(msg):
        order.append("redis")

    monkeypatch.setattr(redis_writer, "write_telemetry", fake_write_telemetry)
    await persist.persist_message(_telemetry(slave=3))
    assert order == ["influx", "redis"]  # persist trước, phát WS sau
    assert len(frames) == 1 and frames[0]["type"] == "telemetry"
    assert frames[0]["data"]["slave_addr"] == 3


async def test_status_broadcast_even_when_unchanged(spy, monkeypatch):
    frames, _ = spy

    async def fake_write_status(msg):
        return False  # retain replay

    monkeypatch.setattr(redis_writer, "write_status", fake_write_status)
    s = Status(gateway_id="G", adapter_key="s7200_v1", received_at=T, state="online")
    await persist.persist_message(s)
    assert len(frames) == 1 and frames[0]["type"] == "status"


async def test_info_diag_event_always_broadcast(spy, monkeypatch):
    frames, order = spy

    async def fake_upsert(msg):
        order.append("pg_upsert")

    async def fake_events(msg):
        order.append("pg_events")

    monkeypatch.setattr(persist, "_upsert_gateway_info", fake_upsert)
    monkeypatch.setattr(persist, "_insert_events", fake_events)

    await persist.persist_message(
        GatewayInfo(
            gateway_id="G",
            adapter_key="s7200_v1",
            received_at=T,
            slaves=[SlaveRef(addr=1)],
        )
    )
    await persist.persist_message(
        Diag(gateway_id="G", adapter_key="s7200_v1", received_at=T, uptime_s=10)
    )
    await persist.persist_message(
        GatewayEvent(
            gateway_id="G",
            adapter_key="s7200_v1",
            received_at=T,
            events=[EventItem(code="SLAVE_COMM_LOST")],
        )
    )
    assert [f["type"] for f in frames] == ["info", "diag", "event"]
    assert order == ["pg_upsert", "influx", "pg_events"]  # info/event gửi SAU khi ghi PG (§4.3)


async def test_status_redis_failure_skips_broadcast(spy, monkeypatch):
    frames, _ = spy

    async def boom(msg):
        raise RuntimeError("redis down")

    monkeypatch.setattr(redis_writer, "write_status", boom)
    s = Status(gateway_id="G", adapter_key="s7200_v1", received_at=T, state="offline")
    await persist.persist_message(s)
    assert frames == []  # không có state tin cậy -> không phát, giữ hành vi M3

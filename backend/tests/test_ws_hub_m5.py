import asyncio
import json
from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.parsers.base import Telemetry
from app.stores import redis_client
from app.ws import hub as hub_mod
from app.ws.hub import MAX_QUEUE, Hub, RedisPubSubBroadcaster, TelemetryThrottle

T = datetime(2026, 9, 19, 8, 0, 0, tzinfo=UTC)


def _telemetry(gw="GW_S7200_01", slave=1, **kw) -> Telemetry:
    base = dict(
        gateway_id=gw, adapter_key="s7200_v1", received_at=T, slave_addr=slave, seq=1, raw={}
    )
    base.update(kw)
    return Telemetry(signals={"ai_raw": 100}, **base)


@pytest.fixture(autouse=True)
def _clean_hub():
    yield
    hub_mod.client_hub._conns.clear()
    hub_mod.reset_broadcaster()
    hub_mod.reset_throttle()


# ---------- TelemetryThrottle (latest-wins, leading + trailing flush) ----------


def _env(gw: str, slave: int = 1, v: int = 0) -> dict:
    return {"type": "telemetry", "ts": "t", "data": {"gateway_id": gw, "slave_addr": slave, "v": v}}


async def test_throttle_leading_then_trailing_flush_at_boundary():
    published: list[dict] = []
    sleeps: list[float] = []
    gates: list[asyncio.Event] = []
    clock = {"t": 1000.0}

    async def publish(env):
        published.append(env)

    async def fake_sleep(d):
        sleeps.append(d)
        ev = asyncio.Event()
        gates.append(ev)
        await ev.wait()  # mô phỏng boundary chưa tới

    th = TelemetryThrottle(0.25, publish=publish, now=lambda: clock["t"], sleep=fake_sleep)

    await th.submit(_env("G", v=1))  # cửa sổ trống -> leading emit ngay
    assert [p["data"]["v"] for p in published] == [1]
    assert sleeps == []

    clock["t"] += 0.1
    await th.submit(_env("G", v=2))  # giữa cửa sổ -> giữ pending + hẹn flush đúng boundary
    await asyncio.sleep(0.01)  # cho task trailing chạy tới fake_sleep
    assert [p["data"]["v"] for p in published] == [1]
    assert sleeps == pytest.approx([0.15])

    clock["t"] += 0.05
    await th.submit(_env("G", v=3))  # latest wins — timer cũ còn chờ, không tạo timer mới
    assert sleeps == pytest.approx([0.15])
    clock["t"] += 0.1  # đồng hồ chạm boundary 1000.25 -> timer thức giấc
    gates[0].set()
    await asyncio.sleep(0.01)
    assert [p["data"]["v"] for p in published] == [1, 3]
    # mốc phát neo theo boundary (1000.25), không trôi theo thời điểm input
    assert th._last_emit[("G", 1)] == pytest.approx(1000.25)

    clock["t"] += 0.15  # 1000.4 - 1000.25 = 0.15 < 0.25 -> vẫn trong cửa sổ mới
    await th.submit(_env("G", v=4))
    await asyncio.sleep(0.01)
    assert len(published) == 2
    assert sleeps == pytest.approx([0.15, 0.1])
    clock["t"] += 0.1  # 1000.5 - 1000.25 = 0.25 -> leading của cửa sổ kế tiếp
    await th.submit(_env("G", v=5))
    assert [p["data"]["v"] for p in published] == [1, 3, 5]
    # pending v4 bị hủy vì đã có frame mới hơn — flush muộn không ghi đè giá trị cũ
    gates[1].set()
    await asyncio.sleep(0.01)
    assert [p["data"]["v"] for p in published] == [1, 3, 5]


async def test_throttle_keys_independent_and_zero_interval():
    published: list[dict] = []

    async def publish(env):
        published.append(env)

    th = TelemetryThrottle(0.25, publish=publish, now=lambda: 500.0)
    await th.submit(_env("G", slave=1))
    await th.submit(_env("G", slave=2))  # slave khác độc lập
    await th.submit(_env("H", slave=1))  # gateway khác độc lập
    await th.submit(_env("G", slave=1))  # cùng key, thời điểm đứng -> pending, không phát thêm
    assert len(published) == 3
    for t in th._timers.values():
        t.cancel()

    th0 = TelemetryThrottle(0.0, publish=publish)
    await th0.submit(_env("G"))
    await th0.submit(_env("G"))
    assert len(published) == 5  # interval=0 -> passthrough


# ---------- Hub fan-out ----------


def test_hub_publish_respects_gateway_filter():
    hub = Hub()
    all_conn = hub.register()
    b_conn = hub.register()
    hub.set_gateways(b_conn, ["B"])
    hub.publish(_env("A"))
    hub.publish(_env("B"))
    assert all_conn.queue.qsize() == 2
    assert b_conn.queue.qsize() == 1
    assert b_conn.queue.get_nowait()["data"]["gateway_id"] == "B"


def test_hub_publish_envelope_without_gateway_goes_everywhere():
    hub = Hub()
    c = hub.register()
    hub.set_gateways(c, ["B"])
    hub.publish({"type": "info", "ts": "x", "data": {}})
    assert c.queue.qsize() == 1


def test_hub_slow_client_drops_not_blocks():
    hub = Hub()
    c = hub.register()
    for _ in range(MAX_QUEUE):
        c.queue.put_nowait(_env("A"))
    before = hub.counters["ws_dropped"]
    hub.publish(_env("A"))
    assert hub.counters["ws_dropped"] == before + 1
    assert c.queue.qsize() == MAX_QUEUE


def test_set_gateways_empty_list_means_all():
    hub = Hub()
    c = hub.register()
    hub.set_gateways(c, ["B"])
    hub.set_gateways(c, [])
    hub.publish(_env("Z"))
    assert c.queue.qsize() == 1


# ---------- envelope ----------


def test_make_envelope_shape():
    env = hub_mod.make_envelope(_telemetry(slave=2, seq=43))
    assert env["type"] == "telemetry"
    assert env["ts"].endswith("Z")
    data = env["data"]
    assert data["gateway_id"] == "GW_S7200_01"
    assert data["slave_addr"] == 2
    assert data["seq"] == 43
    assert data["signals"] == {"ai_raw": 100}
    assert data["received_at"] == "2026-09-19T08:00:00Z"  # pydantic serialize UTC dạng Z


# ---------- Broadcaster impls ----------


def test_get_broadcaster_selection(monkeypatch):
    monkeypatch.setattr(hub_mod, "get_settings", lambda: Settings(ws_pubsub_enabled=False))
    hub_mod.reset_broadcaster()
    assert isinstance(hub_mod.get_broadcaster(), hub_mod.LocalBroadcaster)
    monkeypatch.setattr(hub_mod, "get_settings", lambda: Settings(ws_pubsub_enabled=True))
    hub_mod.reset_broadcaster()
    assert isinstance(hub_mod.get_broadcaster(), RedisPubSubBroadcaster)


async def test_redis_pubsub_publish_feeds_local_hub_and_channel(monkeypatch):
    published = []

    class FakeRedis:
        async def publish(self, channel, payload):
            published.append((channel, payload))

    monkeypatch.setattr(redis_client, "get_redis", lambda: FakeRedis())
    b = RedisPubSubBroadcaster()
    hub_mod.reset_broadcaster()
    env = _env("A")
    before = hub_mod.client_hub.counters["ws_published"]
    await b.publish(env)
    assert hub_mod.client_hub.counters["ws_published"] == before + 1
    assert published[0][0] == "sb:ws"
    wrapper = json.loads(published[0][1])
    assert wrapper["o"] == b._origin
    assert wrapper["e"] == env


def test_decode_foreign_skips_own_origin_and_garbage():
    b = RedisPubSubBroadcaster()
    assert b.decode_foreign(json.dumps({"o": b._origin, "e": _env("A")})) is None
    assert b.decode_foreign(json.dumps({"o": "other", "e": _env("A")}))["data"]["gateway_id"] == "A"
    assert b.decode_foreign(b"not-json") is None
    assert b.decode_foreign(json.dumps({"o": "x", "e": "not-a-dict"})) is None
    assert b.decode_foreign(json.dumps({"random": 1})) is None


async def test_broadcast_message_never_raises(monkeypatch):
    class Boom:
        async def publish(self, envelope):
            raise RuntimeError("redis down")

    monkeypatch.setattr(hub_mod, "get_broadcaster", lambda: Boom())
    await hub_mod.broadcast_message(_telemetry())  # phải KHÔNG raise

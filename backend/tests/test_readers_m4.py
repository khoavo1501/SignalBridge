from datetime import UTC, datetime

from app.stores import redis_reader
from app.stores.influx_query import _history_fluxes

T = datetime(2026, 9, 19, 8, 0, 0, tzinfo=UTC)


class FakeRedis:
    def __init__(self, data):
        self.data = data

    async def hgetall(self, key):
        return self.data.get(key, {})

    async def get(self, key):
        return self.data.get(key)


async def test_redis_reader_decodes_hash(monkeypatch):
    # redis-py encode key khi gửi (str ok) nhưng trả về bytes cho hash field/value
    data = {
        "sb:status:GW": {b"state": b"online", b"since": b"2026-09-19T08:00:00+00:00"},
        "sb:last_seen:GW": b"1789804800.4",
        "sb:latest:GW:1": {
            b"di_0": b"true",
            b"ai_raw": b"12345",
            b"_received_at": b"2026-09-19T08:00:00+00:00",
            b"_seq": b"42",
        },
    }
    monkeypatch.setattr(redis_reader, "get_redis", lambda: FakeRedis(data))
    assert await redis_reader.read_status("GW") == {
        "state": "online",
        "since": "2026-09-19T08:00:00+00:00",
    }
    assert await redis_reader.read_last_seen("GW") == 1789804800.4
    latest = await redis_reader.read_latest("GW", 1)
    assert latest["signals"] == {"di_0": True, "ai_raw": 12345}
    assert latest["seq"] == 42 and latest["received_at"].endswith("+00:00")
    assert await redis_reader.read_status("MISSING") is None
    assert await redis_reader.read_latest("GW", 9) is None
    assert await redis_reader.read_last_seen("MISSING") is None


def test_history_fluxes_raw_and_agg():
    raw = _history_fluxes("GW", 1, ["ai_raw"], T, T, agg=None, limit=5000)
    assert len(raw) == 1
    assert 'r.gateway_id == "GW"' in raw[0]
    assert "aggregateWindow" not in raw[0]
    fluxes = _history_fluxes('GW"x', 1, ["ai_raw", "di_0", "hc0"], T, T, agg="10s", limit=100)
    assert len(fluxes) == 2
    numeric, digital = fluxes
    assert 'r.gateway_id == "GW\\"x"' in numeric
    assert '_field == "ai_raw" or r._field == "hc0"' in numeric
    assert "aggregateWindow(every: 10s, fn: mean" in numeric
    assert "map(fn" not in numeric
    assert '_field == "di_0"' in digital
    assert "if r._value then 1.0 else 0.0" in digital
    assert "aggregateWindow" in digital

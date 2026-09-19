import json
from datetime import UTC, datetime

from app.ingestion import persist
from app.parsers.base import (
    Diag,
    EventItem,
    GatewayEvent,
    GatewayInfo,
    SlaveRef,
    SlaveStat,
    Status,
    Telemetry,
)
from app.stores import redis_writer
from app.stores.influx_writer import diag_point, telemetry_point

T = datetime(2026, 9, 19, 8, 0, 0, 400_000, tzinfo=UTC)


def _telemetry(**kw) -> Telemetry:
    base = dict(
        gateway_id="GW_S7200_01",
        adapter_key="s7200_v1",
        received_at=T,
        slave_addr=1,
        seq=42,
        signals={"di_0": True, "di_1": False, "di_word": 5, "ai_raw": 12345},
        raw={},
    )
    base.update(kw)
    return Telemetry(**base)


class FakeResult:
    def __init__(self, pk):
        self._pk = pk

    def scalar(self):
        return self._pk

    def scalar_one(self):
        return self._pk


class FakeConn:
    def __init__(self, calls, pk=42):
        self.calls = calls
        self.pk = pk

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        return FakeResult(self.pk)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeEngine:
    def __init__(self, calls, pk=42):
        self.calls = calls
        self.pk = pk

    def begin(self):
        return FakeConn(self.calls, self.pk)


class FakeRedis:
    def __init__(self, stored=None):
        self.stored = stored or {}
        self.ops = []

    async def hget(self, key, field):
        return self.stored.get((key, field))

    async def hset(self, key, mapping=None):
        self.ops.append(("hset", key, dict(mapping or {})))

    async def set(self, key, value):
        self.ops.append(("set", key, value))


# ---------- Influx point builders ----------


def test_telemetry_point_tags_sparse_fields_and_server_time():
    t = _telemetry(signals={"di_0": True, "ai_raw": 12345})  # không có hc0/c0 — firmware hiện tại
    lp = telemetry_point(t).to_line_protocol()
    assert "telemetry," in lp
    assert "gateway_id=GW_S7200_01" in lp
    assert "slave_addr=1" in lp
    assert "adapter_key=s7200_v1" in lp
    assert "di_0=true" in lp
    assert "ai_raw=12345i" in lp
    assert "hc0" not in lp and "c0" not in lp
    assert "seq=42i" in lp
    # timestamp = received_at (server time) tính bằng ns
    assert lp.endswith(str(int(T.timestamp() * 1e9)))


def test_diag_point_slave_fields():
    d = Diag(
        gateway_id="GW_S7200_01",
        adapter_key="s7200_v1",
        received_at=T,
        poll_cycle_ms=100,
        uptime_s=3600,
        slave_stats=[SlaveStat(addr=1, ok=12345, fail=6)],
        tx_packets=12340,
        tx_failures=6,
        mqtt_reconnect=3,
    )
    lp = diag_point(d).to_line_protocol()
    assert lp.startswith("diag,adapter_key=s7200_v1,gateway_id=GW_S7200_01 ")
    assert "slave_1_ok=12345i" in lp
    assert "slave_1_fail=6i" in lp
    assert "uptime_s=3600i" in lp


# ---------- Redis writer ----------


async def test_write_telemetry_hash_fields(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(redis_writer, "get_redis", lambda: r)
    await redis_writer.write_telemetry(_telemetry())
    hset = [op for op in r.ops if op[0] == "hset"][0]
    assert hset[1] == "sb:latest:GW_S7200_01:1"
    mapping = hset[2]
    assert mapping["_received_at"] == T.isoformat()  # server time, không phải ts=0
    assert mapping["_seq"] == "42"
    assert json.loads(mapping["di_0"]) is True
    assert json.loads(mapping["ai_raw"]) == 12345
    set_op = [op for op in r.ops if op[0] == "set"][0]
    assert set_op[1] == "sb:last_seen:GW_S7200_01"
    assert float(set_op[2]) == T.timestamp()


async def test_status_change_detection(monkeypatch):
    def make_status(state):
        return Status(gateway_id="GW_S7200_01", adapter_key="s7200_v1", received_at=T, state=state)

    # lần đầu (redis trống) -> changed, có since
    r = FakeRedis()
    monkeypatch.setattr(redis_writer, "get_redis", lambda: r)
    assert await redis_writer.write_status(make_status("online")) is True
    key, mapping = r.ops[0][1], r.ops[0][2]
    assert key == "sb:status:GW_S7200_01"
    assert mapping["since"] == T.isoformat()

    # retain replay cùng state -> không đổi, không ghi đè since
    r2 = FakeRedis(stored={("sb:status:GW_S7200_01", "state"): b"online"})
    monkeypatch.setattr(redis_writer, "get_redis", lambda: r2)
    assert await redis_writer.write_status(make_status("online")) is False
    assert "since" not in r2.ops[0][2]

    # LWT offline -> đổi state, cập nhật since + reason
    r3 = FakeRedis(stored={("sb:status:GW_S7200_01", "state"): "online"})
    monkeypatch.setattr(redis_writer, "get_redis", lambda: r3)
    off = make_status("offline")
    off.reason = "unexpected_disconnect"
    assert await redis_writer.write_status(off) is True
    assert r3.ops[0][2]["reason"] == "unexpected_disconnect"


# ---------- persist routing ----------


async def test_persist_telemetry_to_influx_and_redis(monkeypatch):
    calls = []

    async def fake_write_telemetry(msg):
        calls.append("redis")

    monkeypatch.setattr(persist.influx_writer, "enqueue", lambda p: calls.append("influx"))
    monkeypatch.setattr(redis_writer, "write_telemetry", fake_write_telemetry)
    await persist.persist_message(_telemetry())
    assert calls == ["influx", "redis"]


async def test_persist_status_only_inserts_pg_event_on_change(monkeypatch):
    seen = []

    async def fake_write_status(msg):
        return fake_write_status.changed

    async def spy_event(msg):
        seen.append(msg)

    monkeypatch.setattr(redis_writer, "write_status", fake_write_status)
    monkeypatch.setattr(persist, "_record_status_event", spy_event)

    s = Status(gateway_id="G", adapter_key="s7200_v1", received_at=T, state="online")
    fake_write_status.changed = False
    await persist.persist_message(s)
    assert seen == []  # retain replay — không spam event

    fake_write_status.changed = True
    await persist.persist_message(s)
    assert seen == [s]


async def test_record_status_event_uses_lookup_and_code(monkeypatch):
    calls = []
    monkeypatch.setattr(persist, "get_engine", lambda: FakeEngine(calls, pk=42))
    s = Status(gateway_id="GW_S7200_01", adapter_key="s7200_v1", received_at=T, state="offline")
    s.reason = "unexpected_disconnect"
    await persist._record_status_event(s)
    assert len(calls) == 2  # SELECT id + INSERT
    insert_sql, params = calls[1]
    assert "INSERT INTO gateway_events" in insert_sql
    assert params["code"] == "STATUS_OFFLINE"
    assert params["gw"] == 42
    assert params["src"] is None
    assert params["msg"] == "unexpected_disconnect"
    assert json.loads(params["raw"])["state"] == "offline"


async def test_upsert_info_slaves_idempotent(monkeypatch):
    calls = []
    monkeypatch.setattr(persist, "get_engine", lambda: FakeEngine(calls, pk=42))
    info = GatewayInfo(
        gateway_id="GW_S7200_01",
        adapter_key="s7200_v1",
        received_at=T,
        fw_version="1.1.0",
        slaves=[SlaveRef(addr=1, name="S7-200")],
    )
    await persist._upsert_gateway_info(info)
    assert len(calls) == 2
    upsert_sql, params = calls[0]
    assert "ON CONFLICT (gateway_id) DO UPDATE SET" in upsert_sql
    assert "fw_version = COALESCE(EXCLUDED.fw_version" in upsert_sql
    assert params == {
        "gid": "GW_S7200_01",
        "key": "s7200_v1",
        "fw": "1.1.0",
        "hw": None,
        "ip": None,
        "mac": None,
    }
    slave_sql, slave_params = calls[1]
    assert "INSERT INTO slaves" in slave_sql
    assert slave_params == {"gw": 42, "addr": 1, "name": "S7-200"}


async def test_events_skip_unregistered_gateway(monkeypatch):
    calls = []
    monkeypatch.setattr(persist, "get_engine", lambda: FakeEngine(calls, pk=None))
    before = persist.counters["pg_skipped_unregistered"]
    ev = GatewayEvent(
        gateway_id="GW_UNKNOWN",
        adapter_key="s7200_v1",
        received_at=T,
        events=[
            EventItem(code="SLAVE_COMM_LOST", severity="critical", source="slave:1", slave_addr=1)
        ],
    )
    await persist._insert_events(ev)
    assert len(calls) == 1  # chỉ có SELECT, không INSERT
    assert persist.counters["pg_skipped_unregistered"] == before + 1


async def test_events_insert_each_item(monkeypatch):
    calls = []
    monkeypatch.setattr(persist, "get_engine", lambda: FakeEngine(calls, pk=7))
    ev = GatewayEvent(
        gateway_id="GW_S7200_01",
        adapter_key="s7200_v1",
        received_at=T,
        events=[
            EventItem(
                code="SLAVE_COMM_LOST",
                severity="critical",
                message="Modbus RTU read failed",
                source="slave:1",
                slave_addr=1,
            ),
            EventItem(code="SOMETHING_ELSE"),
        ],
    )
    await persist._insert_events(ev)
    assert len(calls) == 3  # SELECT + 2 INSERT
    _, p1 = calls[1]
    assert p1["code"] == "SLAVE_COMM_LOST" and p1["addr"] == 1 and p1["sev"] == "critical"
    _, p2 = calls[2]
    assert p2["code"] == "SOMETHING_ELSE" and p2["sev"] == "info" and p2["addr"] is None

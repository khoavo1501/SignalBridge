from datetime import UTC, datetime

import httpx
import pytest

from app.ingestion import pipeline
from app.main import app
from app.stores import postgres, redis_writer

T0 = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def stores(monkeypatch):
    class Fake:
        gateways = [
            {
                "id": 1,
                "gateway_id": "GW_S7200_01",
                "display_name": "Gateway S7-200 demo",
                "adapter_key": "s7200_v1",
                "fw_version": None,
                "hw_version": None,
                "ip": None,
                "mac": None,
                "enabled": True,
            }
        ]
        slaves = [{"slave_addr": 1, "name": "S7-200", "protocol": None, "enabled": True}]
        insert_result = {"gateway_id": "GW_S7200_02", "enabled": True, "adapter_key": "s7200_v1"}
        insert_call: tuple | None = None
        delete_result = gateways[0]
        delete_call: str | None = None
        redis_removed = 3
        redis_fail = False
        unknown = {"GW_ROBOT_09": "2026-09-20T03:00:00Z", "GW_S7200_01": "2026-09-20T03:10:00Z"}

    async def fetch_gateway(gid):
        return next((g for g in Fake.gateways if g["gateway_id"] == gid), None)

    async def fetch_slaves(pk):
        return Fake.slaves

    async def insert_gateway(gid, dn, key):
        Fake.insert_call = (gid, dn, key)
        return Fake.insert_result

    async def delete_gateway(gid):
        Fake.delete_call = gid
        return Fake.delete_result

    async def redis_delete(gid, addrs):
        Fake.redis_call = (gid, addrs)
        if Fake.redis_fail:
            raise RuntimeError("redis down")
        return Fake.redis_removed

    def unknown_snapshot():
        return dict(Fake.unknown)

    monkeypatch.setattr(postgres, "fetch_gateway", fetch_gateway)
    monkeypatch.setattr(postgres, "fetch_slaves", fetch_slaves)
    monkeypatch.setattr(postgres, "insert_gateway", insert_gateway)
    monkeypatch.setattr(postgres, "delete_gateway", delete_gateway)
    monkeypatch.setattr(redis_writer, "delete_gateway", redis_delete)
    monkeypatch.setattr(pipeline, "unknown_seen_snapshot", unknown_snapshot)
    return Fake


# ---------- POST /gateways ----------


async def test_create_ok(client, stores):
    r = await client.post(
        "/api/v1/gateways",
        json={"gateway_id": "GW_S7200_02", "adapter_key": "s7200_v1", "display_name": "Máy 2"},
    )
    assert r.status_code == 201
    assert r.json()["gateway_id"] == "GW_S7200_02"
    assert stores.insert_call == ("GW_S7200_02", "Máy 2", "s7200_v1")


async def test_create_display_name_defaults_to_id(client, stores):
    r = await client.post(
        "/api/v1/gateways", json={"gateway_id": "GW_S7200_03", "adapter_key": "s7200_v1"}
    )
    assert r.status_code == 201
    assert stores.insert_call == ("GW_S7200_03", "GW_S7200_03", "s7200_v1")


async def test_create_invalid_id_400(client, stores):
    for bad in ["ab", "GW S7200", "_leading", "x" * 65]:
        r = await client.post(
            "/api/v1/gateways", json={"gateway_id": bad, "adapter_key": "s7200_v1"}
        )
        assert r.status_code == 400, bad
        assert r.json()["error"]["code"] == "invalid_gateway_id"


async def test_create_unknown_adapter_422(client, stores):
    r = await client.post(
        "/api/v1/gateways", json={"gateway_id": "GW_NEW_01", "adapter_key": "khong_ton_tai"}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_adapter_key"


async def test_create_duplicate_409(client, stores):
    stores.insert_result = None
    r = await client.post(
        "/api/v1/gateways", json={"gateway_id": "GW_S7200_01", "adapter_key": "s7200_v1"}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "gateway_exists"


# ---------- GET /gateways/unknown (route phải đứng trước /{gateway_id}) ----------


async def test_unknown_lists_only_unregistered(client, stores):
    body = (await client.get("/api/v1/gateways/unknown")).json()
    assert body["gateways"] == [{"gateway_id": "GW_ROBOT_09", "last_seen": "2026-09-20T03:00:00Z"}]


# ---------- DELETE /gateways/{id} ----------


async def test_delete_cascades_pg_and_cleans_redis(client, stores):
    r = await client.delete("/api/v1/gateways/GW_S7200_01")
    assert r.status_code == 200
    assert r.json() == {"deleted": "GW_S7200_01", "redis_keys_removed": 3}
    assert stores.delete_call == "GW_S7200_01"
    assert stores.redis_call == ("GW_S7200_01", [1])


async def test_delete_redis_failure_still_reports(client, stores):
    stores.redis_fail = True
    r = await client.delete("/api/v1/gateways/GW_S7200_01")
    assert r.status_code == 200 and r.json()["redis_keys_removed"] == 0


async def test_delete_404(client, stores):
    r = await client.delete("/api/v1/gateways/GW_KHONG_CO")
    assert r.status_code == 404 and r.json()["error"]["code"] == "gateway_not_found"


# ---------- GET /adapters ----------


async def test_adapters_list(client):
    body = (await client.get("/api/v1/adapters")).json()
    assert {"key": "s7200_v1"} in body["adapters"]


# ---------- pipeline unknown tracking ----------


def test_record_unknown_snapshot_roundtrip():
    import app.ingestion.pipeline as p

    original = dict(p._unknown_seen)
    try:
        p._unknown_seen.clear()
        p._record_unknown("GW_TEST_99", p.datetime.now(p.UTC))
        snap = p.unknown_seen_snapshot()
        assert "GW_TEST_99" in snap and snap["GW_TEST_99"].endswith("Z")
    finally:
        p._unknown_seen.clear()
        p._unknown_seen.update(original)


# ---------- M8 backlog: /history limit giữ điểm mới nhất ----------


def test_history_fluxes_limit_keeps_newest():
    from app.stores.influx_query import _history_fluxes

    for flux in _history_fluxes("GW_X", 1, ["ai_raw"], T0, T0, agg=None, limit=500):
        assert '|> sort(columns: ["_time"], desc: true)' in flux  # mới nhất trước
        assert (
            flux.index("desc: true")
            < flux.index("|> limit(n: 500)")
            < flux.rindex('|> sort(columns: ["_time"])')
        )  # cắt rồi trả lại thứ tự thời gian
    for flux in _history_fluxes("GW_X", 1, ["ai_raw", "di_0"], T0, T0, agg="10s", limit=99):
        assert len(flux) > 0 and flux.endswith('|> sort(columns: ["_time"])')


# ---------- M8 backlog: GET /api/v1/events aggregate ----------


async def test_events_aggregate_cursor(client, stores, monkeypatch):
    row = {
        "received_at": T0,
        "code": "SLAVE_COMM_LOST",
        "severity": "critical",
        "message": "Modbus RTU read failed",
        "source": "slave:1",
        "slave_addr": 1,
        "gateway_id": "GW_S7200_01",
    }

    captured = {}

    async def fetch_events_all(limit, before=None, code=None):
        captured.update(limit=limit, before=before, code=code)
        return [row] * (limit if captured["stage"] == "first" else 1)

    captured["stage"] = "first"
    monkeypatch.setattr(postgres, "fetch_events_all", fetch_events_all)
    body = (await client.get("/api/v1/events?limit=5")).json()
    assert captured["limit"] == 6  # limit+1 probe
    assert len(body["events"]) == 5
    assert body["events"][0]["gateway_id"] == "GW_S7200_01"
    assert body["next_before"] == "2026-09-19T08:00:00Z"

    captured["stage"] = "second"
    before = T0.isoformat().replace("+00:00", "Z")
    body = (await client.get(f"/api/v1/events?limit=5&before={before}&code=SLAVE_COMM_LOST")).json()
    assert body["next_before"] is None
    assert captured["before"] == T0 and captured["code"] == "SLAVE_COMM_LOST"


async def test_events_aggregate_limit_clamped(client, stores, monkeypatch):
    async def fetch_events_all(limit, before=None, code=None):
        assert limit == 501  # 100000 → clamp 500 → +1
        return []

    monkeypatch.setattr(postgres, "fetch_events_all", fetch_events_all)
    body = (await client.get("/api/v1/events?limit=100000")).json()
    assert body == {"events": [], "next_before": None}

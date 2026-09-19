from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.api import dashboard, gateways
from app.main import app
from app.stores import influx_query, postgres, redis_reader

T = datetime(2026, 9, 19, 8, 0, 0, tzinfo=UTC)


def _z(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _gw_row(**kw):
    base = dict(
        id=1,
        gateway_id="GW_S7200_01",
        display_name="Gateway S7-200 demo",
        adapter_key="s7200_v1",
        fw_version="1.1.0",
        hw_version="STM32F411_W5500_RS485",
        ip="192.168.1.50",
        mac="02:53:37:20:00:01",
        enabled=True,
        created_at=T,
        updated_at=T,
    )
    base.update(kw)
    return base


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def stores(monkeypatch):
    """Bọc các reader với fake data; set trường bên trong để từng test đổi."""

    class Fake:
        gateways = [_gw_row()]
        slaves = [{"slave_addr": 1, "name": "S7-200", "protocol": "modbus-rtu", "enabled": True}]
        defs: list[dict] = []
        status = {"state": "online", "since": T.isoformat(), "reason": ""}
        last_seen: float | None = T.timestamp()
        latest = {
            "slave_addr": 1,
            "received_at": T.isoformat(),
            "seq": 42,
            # hc0/c0 VẮNG MẶT — đúng firmware hiện tại (ràng buộc #3)
            "signals": {"di_0": True, "di_word": 5, "ai_raw": 12345},
        }
        events: list[dict] = []
        history: dict[str, list] = {}
        diag: dict | None = None
        patch_result = _gw_row(enabled=False)
        errors: dict[str, Exception] = {}

    async def fetch_gateways(include_disabled=True):
        if include_disabled:
            return Fake.gateways
        return [g for g in Fake.gateways if g["enabled"]]

    async def fetch_gateway(gid):
        g = next((x for x in Fake.gateways if x["gateway_id"] == gid), None)
        return g

    async def fetch_slaves(pk):
        return Fake.slaves

    async def fetch_signal_defs(pk):
        return Fake.defs

    async def fetch_events(pk, limit, before=None, code=None):
        Fake.events_query = {"limit": limit, "before": before, "code": code}
        return Fake.events

    async def patch_gateway(gid, fields):
        Fake.patch_call = (gid, fields)
        return Fake.patch_result

    async def read_status(gid):
        return Fake.status

    async def read_last_seen(gid):
        return Fake.last_seen

    async def read_latest(gid, slave):
        if Fake.latest is None or slave != Fake.latest["slave_addr"]:
            return None
        return dict(Fake.latest)

    async def query_history(gid, slave, signals, start, stop, agg=None, limit=5000):
        if "history" in Fake.errors:
            raise Fake.errors["history"]
        Fake.history_query = {
            "signals": signals,
            "start": start,
            "stop": stop,
            "agg": agg,
            "limit": limit,
        }
        return {k: v for k, v in Fake.history.items() if k in signals}

    async def query_diag_latest(gid):
        if "diag" in Fake.errors:
            raise Fake.errors["diag"]
        return Fake.diag

    monkeypatch.setattr(postgres, "fetch_gateways", fetch_gateways)
    monkeypatch.setattr(postgres, "fetch_gateway", fetch_gateway)
    monkeypatch.setattr(postgres, "fetch_slaves", fetch_slaves)
    monkeypatch.setattr(postgres, "fetch_signal_defs", fetch_signal_defs)
    monkeypatch.setattr(postgres, "fetch_events", fetch_events)
    monkeypatch.setattr(postgres, "patch_gateway", patch_gateway)
    monkeypatch.setattr(redis_reader, "read_status", read_status)
    monkeypatch.setattr(redis_reader, "read_last_seen", read_last_seen)
    monkeypatch.setattr(redis_reader, "read_latest", read_latest)
    monkeypatch.setattr(influx_query, "query_history", query_history)
    monkeypatch.setattr(influx_query, "query_diag_latest", query_diag_latest)
    return Fake


# ---------- dashboard/summary ----------


async def test_summary_online_with_raw_metrics(client, stores):
    stores.last_seen = datetime.now(UTC).timestamp()
    r = await client.get("/api/v1/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["stale_threshold_s"] == 10
    gw = body["gateways"][0]
    assert gw["badge"] == "online" and gw["fresh"] is True
    assert gw["fw_version"] == "1.1.0" and gw["slave_count"] == 1
    # Q2: raw + scaled=false; DI loại khỏi primary metrics; hc0 vắng mặt không lỗi
    assert gw["primary_metrics"] == [
        {
            "key": "ai_raw",
            "display_name": "ai_raw",
            "unit": None,
            "raw": 12345,
            "value": 12345,
            "scaled": False,
        }
    ]


async def test_summary_uses_signal_defs_display_name(client, stores):
    stores.defs = [
        {"key": "ai_raw", "display_name": "Tốc độ", "unit": None, "kind": "analog", "enabled": True}
    ]
    stores.last_seen = datetime.now(UTC).timestamp()
    gw = (await client.get("/api/v1/dashboard/summary")).json()["gateways"][0]
    assert gw["primary_metrics"][0]["display_name"] == "Tốc độ"


async def test_summary_badge_stale_when_telemetry_lags(client, stores):
    stores.last_seen = datetime.now(UTC).timestamp() - 30  # state vẫn online
    gw = (await client.get("/api/v1/dashboard/summary")).json()["gateways"][0]
    assert gw["badge"] == "stale" and gw["state"] == "online" and gw["fresh"] is False


async def test_summary_badge_offline_on_lwt(client, stores):
    stores.status = {"state": "offline", "since": T.isoformat(), "reason": "unexpected_disconnect"}
    gw = (await client.get("/api/v1/dashboard/summary")).json()["gateways"][0]
    assert gw["badge"] == "offline"


async def test_summary_excludes_disabled(client, stores):
    stores.gateways = [_gw_row(enabled=False)]
    body = (await client.get("/api/v1/dashboard/summary")).json()
    assert body["gateways"] == []  # M8: card ẩn khi disable
    listing = (await client.get("/api/v1/gateways")).json()
    assert len(listing["gateways"]) == 1  # /gateways vẫn thấy (admin cần)


# ---------- gateways list/detail/patch ----------


async def test_list_gateways_shape(client, stores):
    body = (await client.get("/api/v1/gateways")).json()
    g = body["gateways"][0]
    assert g["meta"] == {
        "fw_version": "1.1.0",
        "hw_version": "STM32F411_W5500_RS485",
        "ip": "192.168.1.50",
        "mac": "02:53:37:20:00:01",
    }
    assert g["state"] == "online" and g["slaves"][0]["slave_addr"] == 1


async def test_detail_and_404(client, stores):
    body = (await client.get("/api/v1/gateways/GW_S7200_01")).json()
    assert body["gateway_id"] == "GW_S7200_01" and "id" in body
    r = await client.get("/api/v1/gateways/GW_NOPE")
    assert r.status_code == 404
    assert r.json() == {
        "error": {"code": "gateway_not_found", "message": "gateway GW_NOPE chưa đăng ký"}
    }


async def test_patch_enabled_and_bad_adapter(client, stores):
    r = await client.patch("/api/v1/gateways/GW_S7200_01", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert stores.patch_call == ("GW_S7200_01", {"enabled": False})
    r = await client.patch("/api/v1/gateways/GW_S7200_01", json={"adapter_key": "khong_ton_tai"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_adapter_key"


async def test_patch_404(client, stores):
    stores.patch_result = None
    r = await client.patch("/api/v1/gateways/GW_GONE", json={"display_name": "x"})
    assert r.status_code == 404


# ---------- latest ----------


async def test_latest_multi_slave_missing_values(client, stores):
    stores.slaves = [
        {"slave_addr": 1, "name": "S7-200", "protocol": "modbus-rtu", "enabled": True},
        {"slave_addr": 2, "name": None, "protocol": None, "enabled": True},
    ]
    body = (await client.get("/api/v1/gateways/GW_S7200_01/latest")).json()
    assert body["gateway_id"] == "GW_S7200_01"
    s1, s2 = body["slaves"]
    assert s1["signals"]["ai_raw"] == 12345 and s1["seq"] == 42
    assert s2["signals"] is None and s2["received_at"] is None  # slave chưa có dữ liệu


# ---------- history ----------


async def test_history_sparse_signal_and_count(client, stores):
    t2 = T + timedelta(seconds=10)
    stores.history = {"ai_raw": [(T, 12345), (t2, 12350)]}  # hc0 KHÔNG có series — đường đứt quãng
    r = await client.get(
        "/api/v1/gateways/GW_S7200_01/history?slave=1&signals=ai_raw,hc0"
        f"&from={T.isoformat().replace('+00:00', 'Z')}&to={t2.isoformat().replace('+00:00', 'Z')}"
    )
    body = r.json()
    assert body["series"][0]["signal"] == "ai_raw" and len(body["series"][0]["points"]) == 2
    assert body["series"][0]["points"][0] == {"t": "2026-09-19T08:00:00Z", "v": 12345}
    assert body["series"][1]["signal"] == "hc0" and body["series"][1]["points"] == []
    assert body["count"] == 2
    assert stores.history_query["agg"] is None


async def test_history_agg_and_defaults(client, stores):
    stores.history = {"ai_raw": [(T, 1.5)]}
    r = await client.get("/api/v1/gateways/GW_S7200_01/history?signals=ai_raw&agg=10s&limit=99999")
    assert r.status_code == 200
    assert stores.history_query["agg"] == "10s" and stores.history_query["limit"] == 20000
    assert stores.history_query["stop"] - stores.history_query["start"] == timedelta(hours=1)


async def test_history_validation(client, stores):
    r = await client.get("/api/v1/gateways/GW_S7200_01/history")
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"
    r = await client.get("/api/v1/gateways/GW_S7200_01/history?signals=ai_raw&agg=xyz")
    assert r.status_code == 400
    start = _z(T)
    end = _z(T + timedelta(days=8))
    r = await client.get(
        f"/api/v1/gateways/GW_S7200_01/history?signals=ai_raw&from={start}&to={end}"
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "range_too_large"
    r = await client.get("/api/v1/gateways/GW_S7200_01/history?signals=ai_raw&to=khong-phai-iso")
    assert r.status_code == 400
    r = await client.get("/api/v1/gateways/GW_S7200_01/history?signals=ai_raw&slave=9")
    assert r.status_code == 404 and r.json()["error"]["code"] == "slave_not_found"


async def test_history_store_unavailable(client, stores):
    stores.errors["history"] = RuntimeError("influx down")
    r = await client.get("/api/v1/gateways/GW_S7200_01/history?signals=ai_raw")
    assert r.status_code == 503 and r.json()["error"]["code"] == "store_unavailable"


# ---------- events ----------


async def test_events_pagination(client, stores):
    row = {
        "received_at": T,
        "code": "SLAVE_COMM_LOST",
        "severity": "critical",
        "message": "Modbus RTU read failed",
        "source": "slave:1",
        "slave_addr": 1,
    }
    stores.events = [row] * 21  # limit+1 → còn trang
    r = await client.get("/api/v1/gateways/GW_S7200_01/events?limit=20")
    body = r.json()
    assert len(body["events"]) == 20
    assert body["next_before"] == "2026-09-19T08:00:00Z"
    assert stores.events_query["limit"] == 21
    assert body["events"][0]["code"] == "SLAVE_COMM_LOST"

    stores.events = [row]
    before = _z(T)
    r = await client.get(f"/api/v1/gateways/GW_S7200_01/events?before={before}&code=STATUS_ONLINE")
    body = r.json()
    assert body["next_before"] is None
    assert stores.events_query["before"] == T and stores.events_query["code"] == "STATUS_ONLINE"


# ---------- diag ----------


async def test_diag_latest_and_note(client, stores):
    stores.diag = {
        "received_at": T,
        "fields": {
            "poll_cycle_ms": 100,
            "uptime_s": 3600,
            "tx_packets": 12340,
            "tx_failures": 6,
            "mqtt_reconnect": 3,
        },
        "slave_stats": [{"addr": 1, "ok": 12345, "fail": 6}],
    }
    body = (await client.get("/api/v1/gateways/GW_S7200_01/diag")).json()
    assert body["latest"]["uptime_s"] == 3600
    assert body["latest"]["slave_stats"] == [{"addr": 1, "ok": 12345, "fail": 6}]
    assert "tx_packets" in body["note"]  # Q7: chú thích biến đếm Modbus


async def test_diag_empty_and_store_down(client, stores):
    body = (await client.get("/api/v1/gateways/GW_S7200_01/diag")).json()
    assert body["latest"] is None
    stores.errors["diag"] = RuntimeError("down")
    r = await client.get("/api/v1/gateways/GW_S7200_01/diag")
    assert r.status_code == 503


async def test_health_endpoints_unaffected(client):
    assert (await client.get("/api/v1/healthz")).status_code == 200
    assert (await client.get("/api/v1/ingestion/stats")).status_code == 200


def test_dashboard_module_symbols():
    assert callable(dashboard._metric_entries)
    assert callable(gateways.patch_gateway)  # router function tồn tại

import json
from datetime import UTC, datetime

import pytest

from app.parsers import registry
from app.parsers.base import Diag, GatewayEvent, GatewayInfo, Status, Telemetry
from app.parsers.s7200_v1 import S7200Adapter

RECEIVED = datetime(2026, 9, 19, 8, 0, 0, tzinfo=UTC)
ADAPTER = S7200Adapter()


def parse(topic: str, payload: dict):
    return ADAPTER.parse("GW_S7200_01", topic, payload, RECEIVED)


def full_telemetry() -> dict:
    return {
        "device_id": "GW_S7200_01",
        "ts": 0,
        "type": "telemetry",
        "seq": 42,
        "fw": "1.1.0",
        "plc": {
            "di_word": 5,
            "di": [True, False, True] + [False] * 5 + [True] * 8,
            "ai": 12345,
        },
        "registers": {
            "di_0": True,
            "di_1": False,
            "di_2": True,
            "di_3": False,
            "di_4": False,
            "di_5": False,
            "di_6": False,
            "di_7": False,
            "hr_50": 12345,
            "hr_54": 123456789,
            "hr_58": 100,
        },
    }


def test_telemetry_full():
    (msg,) = parse("devices/GW_S7200_01/telemetry", full_telemetry())
    assert isinstance(msg, Telemetry)
    assert msg.received_at == RECEIVED  # ts=0 trong payload bị bỏ (ràng buộc #1)
    assert msg.seq == 42
    assert msg.slave_addr == 1
    s = msg.signals
    assert s["di_0"] is True and s["di_2"] is True and s["di_7"] is False
    # bit 8–15 luôn false với fw hiện tại → cố ý bỏ qua (chỉ 8 DI)
    assert "di_8" not in s and "di_15" not in s
    assert s["di_word"] == 5
    assert s["ai_raw"] == 12345  # plc.ai và hr_50 trùng → chỉ một signal
    assert s["hc0"] == 123456789
    assert s["c0"] == 100
    assert msg.raw["type"] == "telemetry"


def test_telemetry_missing_hr54_hr58_no_raise():
    payload = full_telemetry()
    for k in ("hr_54", "hr_58"):
        del payload["registers"][k]
    (msg,) = parse("devices/GW_S7200_01/telemetry", payload)
    assert isinstance(msg, Telemetry)
    assert "hc0" not in msg.signals and "c0" not in msg.signals
    assert msg.signals["ai_raw"] == 12345
    # 9 giá trị hiện tại của fw: 8 DI + ai_raw → đúng như rủi ro #6 báo cáo
    assert sum(1 for k in msg.signals if k.startswith("di_") and k != "di_word") == 8


def test_telemetry_missing_plc_entirely():
    payload = full_telemetry()
    del payload["plc"]
    (msg,) = parse("devices/GW_S7200_01/telemetry", payload)
    # hr_50 vẫn cho ai_raw qua REGISTER_MAP
    assert msg.signals["ai_raw"] == 12345
    assert "di_word" not in msg.signals


def test_telemetry_empty_registers():
    payload = full_telemetry()
    payload["registers"] = {}
    (msg,) = parse("devices/GW_S7200_01/telemetry", payload)
    assert isinstance(msg, Telemetry)


def test_registers_unknown_names_prefixed():
    payload = full_telemetry()
    payload["registers"]["hr_99"] = 7
    (msg,) = parse("devices/GW_S7200_01/telemetry", payload)
    assert msg.signals["reg_hr_99"] == 7


def test_status_online_and_lwt():
    (msg,) = parse(
        "devices/GW_S7200_01/status",
        {
            "device_id": "GW_S7200_01",
            "ts": 0,
            "type": "status",
            "state": "online",
            "uptime_s": 3600,
        },
    )
    assert isinstance(msg, Status) and msg.state == "online" and msg.uptime_s == 3600
    (lwt,) = parse(
        "devices/GW_S7200_01/status",
        {
            "device_id": "GW_S7200_01",
            "ts": 0,
            "type": "status",
            "state": "offline",
            "reason": "unexpected_disconnect",
        },
    )
    assert lwt.state == "offline" and lwt.reason == "unexpected_disconnect"


def test_info_slaves():
    payload = json.loads("""{"device_id":"GW_S7200_01","ts":0,"type":"info","master":{
      "fw_version":"1.1.0","hw_version":"STM32F411_W5500_RS485","ip":"192.168.1.50",
      "mac":"02:53:37:20:00:01","reset_reason":"POWER_ON",
      "slaves":[{"id":1,"addr":1,"name":"S7-200"}]}}""")
    (msg,) = parse("devices/GW_S7200_01/info", payload)
    assert isinstance(msg, GatewayInfo)
    assert msg.fw_version == "1.1.0" and msg.ip == "192.168.1.50"
    assert msg.slaves[0].addr == 1 and msg.slaves[0].name == "S7-200"


def test_diag():
    payload = {
        "device_id": "GW_S7200_01",
        "type": "diag",
        "stats": {
            "poll_cycle_ms": 100,
            "uptime_s": 3600,
            "slaves": [{"id": 1, "addr": 1, "ok": 12345, "fail": 6}],
            "tx_packets": 12340,
            "tx_failures": 6,
            "mqtt_reconnect": 3,
        },
    }
    (msg,) = parse("devices/GW_S7200_01/diag", payload)
    assert isinstance(msg, Diag)
    assert msg.slave_stats[0].addr == 1 and msg.slave_stats[0].fail == 6
    assert msg.mqtt_reconnect == 3


def test_event_slave_source():
    payload = {
        "device_id": "GW_S7200_01",
        "type": "event",
        "events": [
            {
                "code": "SLAVE_COMM_LOST",
                "severity": "critical",
                "message": "Modbus RTU read failed",
                "source": "slave:1",
            }
        ],
    }
    (msg,) = parse("devices/GW_S7200_01/event", payload)
    assert isinstance(msg, GatewayEvent)
    assert msg.events[0].code == "SLAVE_COMM_LOST" and msg.events[0].slave_addr == 1


def test_unknown_category_returns_empty():
    assert parse("devices/GW_S7200_01/other", {"device_id": "GW_S7200_01"}) == []


def test_registry_match_fallback_and_key():
    assert registry.get_by_key("s7200_v1") is not None
    assert registry.get_by_key("nope") is None
    assert isinstance(
        registry.resolve_by_match("GW_S7200_99", "devices/GW_S7200_99/telemetry", full_telemetry()),
        S7200Adapter,
    )
    assert registry.resolve_by_match("X", "devices/X/telemetry", {"type": "other"}) is None


@pytest.mark.parametrize("bad", [b"", b"not json", b"[1,2]", b"null"])
async def test_pipeline_garbage_counts_parse_error(bad):
    from app.ingestion import pipeline

    before = pipeline.stats["parse_errors"]
    result = await pipeline.handle_message("devices/GW_UNKNOWN/telemetry", bad)
    assert result == []
    assert pipeline.stats["parse_errors"] == before + 1

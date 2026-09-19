import re
from datetime import datetime

from app.parsers.base import (
    Diag,
    EventItem,
    GatewayAdapter,
    GatewayEvent,
    GatewayInfo,
    NormalizedMessage,
    SignalValue,
    SlaveRef,
    SlaveStat,
    Status,
    Telemetry,
)

# register thô → tên signal chuẩn (§2.3); register lạ → reg_<ten> nguyên bản
REGISTER_MAP = {"hr_50": "ai_raw", "hr_54": "hc0", "hr_58": "c0"}
TOPIC_SUFFIX_RE = re.compile(r"^devices/(?P<gid>[^/]+)/(?P<category>[a-z]+)$")
VALID_DI_BITS = 8  # bit 8–15 luôn false với fw hiện tại (báo cáo payload, rủi ro #5)


class S7200Adapter(GatewayAdapter):
    key = "s7200_v1"

    def match(self, gateway_id: str, topic: str, payload: dict) -> bool:
        if gateway_id.startswith("GW_S7200"):
            return True
        ptype = payload.get("type")
        if ptype == "telemetry":
            return "plc" in payload or isinstance(payload.get("registers"), dict)
        if ptype == "info":
            return isinstance(payload.get("master"), dict)
        if ptype == "diag":
            return isinstance(payload.get("stats"), dict)
        if ptype == "status":
            return "state" in payload
        if ptype == "event":
            return isinstance(payload.get("events"), list)
        return False

    def parse(
        self, gateway_id: str, topic: str, payload: dict, received_at: datetime
    ) -> list[NormalizedMessage]:
        m = TOPIC_SUFFIX_RE.match(topic)
        category = m.group("category") if m else str(payload.get("type", ""))
        base = {
            "gateway_id": str(payload.get("device_id") or gateway_id),
            "received_at": received_at,
            "adapter_key": self.key,
        }
        # payload.ts luôn = 0 (NTP tắt) → cố ý bỏ hoàn toàn (ràng buộc #1)

        if category == "telemetry":
            return [self._telemetry(base, payload)]
        if category == "status":
            state = payload.get("state")
            if state not in ("online", "offline"):
                state = "online" if state is None else str(state)
            return [
                Status(
                    **base,
                    state="offline" if state == "offline" else "online",
                    uptime_s=_as_int(payload.get("uptime_s")),
                    reason=payload.get("reason"),
                )
            ]
        if category == "info":
            master = payload.get("master") or {}
            slaves = [
                SlaveRef(addr=s.get("id", s.get("addr", 0)), name=s.get("name"))
                for s in (master.get("slaves") or [])
                if isinstance(s, dict)
            ]
            return [
                GatewayInfo(
                    **base,
                    fw_version=master.get("fw_version"),
                    hw_version=master.get("hw_version"),
                    ip=master.get("ip"),
                    mac=master.get("mac"),
                    reset_reason=master.get("reset_reason"),
                    slaves=slaves,
                )
            ]
        if category == "diag":
            stats = payload.get("stats") or {}
            return [
                Diag(
                    **base,
                    poll_cycle_ms=_as_int(stats.get("poll_cycle_ms")),
                    uptime_s=_as_int(stats.get("uptime_s")),
                    slave_stats=[
                        SlaveStat(
                            addr=s.get("id", s.get("addr", 0)),
                            ok=_as_int(s.get("ok")),
                            fail=_as_int(s.get("fail")),
                        )
                        for s in (stats.get("slaves") or [])
                        if isinstance(s, dict)
                    ],
                    tx_packets=_as_int(stats.get("tx_packets")),
                    tx_failures=_as_int(stats.get("tx_failures")),
                    mqtt_reconnect=_as_int(stats.get("mqtt_reconnect")),
                )
            ]
        if category == "event":
            items = []
            for e in payload.get("events") or []:
                if not isinstance(e, dict):
                    continue
                items.append(
                    EventItem(
                        code=str(e.get("code", "UNKNOWN")),
                        severity=e.get("severity"),
                        message=e.get("message"),
                        source=e.get("source"),
                        slave_addr=_parse_source_slave(e.get("source")),
                    )
                )
            return [GatewayEvent(**base, events=items)]
        return []

    def _telemetry(self, base: dict, payload: dict) -> Telemetry:
        signals: dict[str, SignalValue] = {}
        plc = payload.get("plc") or {}
        di = plc.get("di")
        if isinstance(di, list):
            for i, bit in enumerate(di[:VALID_DI_BITS]):
                signals[f"di_{i}"] = bool(bit)
        di_word = _as_int(plc.get("di_word"))
        if di_word is not None:
            signals["di_word"] = di_word
        ai = _as_int(plc.get("ai"))
        if ai is not None:
            signals["ai_raw"] = ai
        registers = payload.get("registers") or {}
        if isinstance(registers, dict):
            for name, value in registers.items():
                if isinstance(value, bool):
                    signals.setdefault(name if name.startswith("di_") else f"reg_{name}", value)
                    continue
                iv = _as_int(value)
                if iv is None:
                    continue
                mapped = REGISTER_MAP.get(name)
                if mapped:
                    signals.setdefault(mapped, iv)  # plc.ai đã set ai_raw thì giữ bản plc
                elif name.startswith("di_"):
                    signals.setdefault(name, iv)
                else:
                    signals.setdefault(f"reg_{name}", iv)
        return Telemetry(
            **base,
            slave_addr=1,
            seq=_as_int(payload.get("seq")),
            signals=signals,
            raw=payload,
        )


def _as_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _parse_source_slave(source) -> int | None:
    if isinstance(source, str) and source.startswith("slave:"):
        try:
            return int(source.split(":", 1)[1])
        except ValueError:
            return None
    return None

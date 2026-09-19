from abc import ABC, abstractmethod
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class NormalizedMessage(BaseModel):
    kind: Literal["telemetry", "status", "info", "diag", "event"]
    gateway_id: str
    received_at: datetime
    adapter_key: str


class SlaveRef(BaseModel):
    addr: int
    name: str | None = None


class SlaveStat(BaseModel):
    addr: int
    ok: int | None = None
    fail: int | None = None


class EventItem(BaseModel):
    code: str
    severity: str | None = None
    message: str | None = None
    source: str | None = None
    slave_addr: int | None = None


SignalValue = bool | int | float


class Telemetry(NormalizedMessage):
    kind: Literal["telemetry"] = "telemetry"
    slave_addr: int = 1
    seq: int | None = None
    signals: dict[str, SignalValue]
    raw: dict


class Status(NormalizedMessage):
    kind: Literal["status"] = "status"
    state: Literal["online", "offline"]
    uptime_s: int | None = None
    reason: str | None = None


class GatewayInfo(NormalizedMessage):
    kind: Literal["info"] = "info"
    fw_version: str | None = None
    hw_version: str | None = None
    ip: str | None = None
    mac: str | None = None
    reset_reason: str | None = None
    slaves: list[SlaveRef] = []


class Diag(NormalizedMessage):
    kind: Literal["diag"] = "diag"
    poll_cycle_ms: int | None = None
    uptime_s: int | None = None
    slave_stats: list[SlaveStat] = []
    tx_packets: int | None = None
    tx_failures: int | None = None
    mqtt_reconnect: int | None = None


class GatewayEvent(NormalizedMessage):
    kind: Literal["event"] = "event"
    events: list[EventItem] = []


class GatewayAdapter(ABC):
    key: str

    @abstractmethod
    def match(self, gateway_id: str, topic: str, payload: dict) -> bool: ...

    @abstractmethod
    def parse(
        self, gateway_id: str, topic: str, payload: dict, received_at: datetime
    ) -> list[NormalizedMessage]: ...

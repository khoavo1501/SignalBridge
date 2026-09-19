import asyncio
import logging
from collections import deque

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS, WritePrecision

from app.config import get_settings
from app.parsers.base import Diag, Telemetry

log = logging.getLogger("signalbridge.influx")

FLUSH_INTERVAL_S = 1.0
MAX_BATCH = 2000


def telemetry_point(msg: Telemetry) -> Point:
    p = (
        Point("telemetry")
        .tag("gateway_id", msg.gateway_id)
        .tag("slave_addr", str(msg.slave_addr))
        .tag("adapter_key", msg.adapter_key)
        .time(msg.received_at, WritePrecision.NS)  # server time — ts payload có giá trị 0, bỏ qua
    )
    for key, value in msg.signals.items():
        if isinstance(value, bool):
            p.field(key, value)
        elif isinstance(value, int):
            p.field(key, int(value))
        elif isinstance(value, float):
            p.field(key, float(value))
    if msg.seq is not None:
        p.field("seq", int(msg.seq))
    return p


def diag_point(msg: Diag) -> Point:
    p = (
        Point("diag")
        .tag("gateway_id", msg.gateway_id)
        .tag("adapter_key", msg.adapter_key)
        .time(msg.received_at, WritePrecision.NS)
    )
    for name in ("poll_cycle_ms", "uptime_s", "tx_packets", "tx_failures", "mqtt_reconnect"):
        value = getattr(msg, name)
        if value is not None:
            p.field(name, int(value))
    for s in msg.slave_stats:
        if s.ok is not None:
            p.field(f"slave_{s.addr}_ok", int(s.ok))
        if s.fail is not None:
            p.field(f"slave_{s.addr}_fail", int(s.fail))
    return p


class InfluxWriter:
    """Hàng đợi point + flush mỗi 1 s (hoặc khi >= MAX_BATCH) trong thread riêng."""

    def __init__(self) -> None:
        self.queue: deque[Point] = deque()
        counters: dict[str, int] = {"influx_written": 0, "influx_errors": 0, "influx_dropped": 0}
        self.counters = counters
        self._client: InfluxDBClient | None = None
        self._write_api = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def enqueue(self, point: Point) -> None:
        if len(self.queue) >= MAX_BATCH * 4:  # DB chết kéo dài — không cho queue phình vô hạn
            self.queue.popleft()
            self.counters["influx_dropped"] += 1
        self.queue.append(point)

    def start(self) -> None:
        if self._task is None:
            self._stop = asyncio.Event()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        await self._task
        self._task = None
        if self._client is not None:
            self._client.close()
            self._client = None
            self._write_api = None

    async def _run(self) -> None:
        while True:
            stopping = False
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=FLUSH_INTERVAL_S)
                stopping = True
            except TimeoutError:
                pass
            await self._flush()
            if stopping:
                break

    async def _flush(self) -> None:
        points: list[Point] = []
        while self.queue and len(points) < MAX_BATCH:
            points.append(self.queue.popleft())
        if not points:
            return
        try:
            await asyncio.to_thread(self._write_sync, points)
            self.counters["influx_written"] += len(points)
        except Exception as exc:
            self.counters["influx_errors"] += 1
            log.warning("influx flush failed (%d points dropped): %s", len(points), exc)

    def _write_sync(self, points: list[Point]) -> None:
        if self._write_api is None:
            s = get_settings()
            self._client = InfluxDBClient(url=s.influx_url, token=s.influx_token, org=s.influx_org)
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        s = get_settings()
        self._write_api.write(bucket=s.influx_bucket, org=s.influx_org, record=points)


writer = InfluxWriter()

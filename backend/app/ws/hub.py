import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.api.common import iso_z
from app.config import get_settings
from app.parsers.base import NormalizedMessage

log = logging.getLogger("signalbridge.ws")

# Hàng đợi mỗi client: chậm thì drop frame mới, không block event loop (DoS từ 1 tab treo)
MAX_QUEUE = 200
PUBSUB_CHANNEL = "sb:ws"
Key = tuple[str, int]  # (gateway_id, slave_addr)


class ClientConn:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict] = asyncio.Queue(MAX_QUEUE)
        self.gateways: set[str] | None = None  # None = subscribe tất cả (§4.2)

    def matches(self, gateway_id: str | None) -> bool:
        return self.gateways is None or gateway_id is None or gateway_id in self.gateways


class Hub:
    """Fan-out in-process. LocalBroadcaster và RedisPubSub subscriber đều đổ vào đây."""

    def __init__(self) -> None:
        self._conns: set[ClientConn] = set()
        self.counters = {"ws_published": 0, "ws_dropped": 0}

    def register(self) -> ClientConn:
        conn = ClientConn()
        self._conns.add(conn)
        return conn

    def unregister(self, conn: ClientConn) -> None:
        self._conns.discard(conn)

    def client_count(self) -> int:
        return len(self._conns)

    def set_gateways(self, conn: ClientConn, gateways: list[str] | None) -> None:
        conn.gateways = set(gateways) if gateways else None

    def publish(self, envelope: dict) -> None:
        gw = envelope.get("data", {}).get("gateway_id")
        self.counters["ws_published"] += 1
        for conn in list(self._conns):
            if conn.matches(gw):
                try:
                    conn.queue.put_nowait(envelope)
                except asyncio.QueueFull:
                    self.counters["ws_dropped"] += 1


client_hub = Hub()


class Broadcaster(ABC):
    """Interface fan-out §4.2 — 2 impl: Local (mặc định) và Redis Pub/Sub (nhiều instance)."""

    @abstractmethod
    async def publish(self, envelope: dict) -> None: ...

    async def run(self) -> None:
        """Vòng nền cho impl cần subscriber. Mặc định không làm gì."""
        await asyncio.Event().wait()


class LocalBroadcaster(Broadcaster):
    async def publish(self, envelope: dict) -> None:
        client_hub.publish(envelope)


class RedisPubSubBroadcaster(Broadcaster):
    """Bật khi WS_PUBSUB_ENABLED=1 (điều kiện tách instance — plan §1.2).

    Instance của mình nhận frame trực tiếp từ hub; instance khác nhận qua kênh `sb:ws`.
    Message bọc {o: origin_id, e: envelope} để subscriber bỏ qua chính mình đăng (chống đôi frame).
    """

    def __init__(self) -> None:
        self._origin = uuid4().hex

    async def publish(self, envelope: dict) -> None:
        client_hub.publish(envelope)
        from app.stores.redis_client import get_redis

        try:
            payload = json.dumps({"o": self._origin, "e": envelope})
            await get_redis().publish(PUBSUB_CHANNEL, payload)
        except Exception as exc:
            log.warning("ws pubsub publish failed: %s", exc)

    def decode_foreign(self, raw) -> dict | None:
        """Envelope từ instance khác; None nếu của mình hoặc hỏng."""
        try:
            wrapper = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if not isinstance(wrapper, dict) or wrapper.get("o") == self._origin:
            return None
        envelope = wrapper.get("e")
        return envelope if isinstance(envelope, dict) else None

    async def run(self) -> None:
        from app.stores.redis_client import get_redis

        backoff = 1.0
        while True:
            ps = None
            try:
                ps = get_redis().pubsub()
                await ps.subscribe(PUBSUB_CHANNEL)
                log.info("ws pubsub subscriber on %s", PUBSUB_CHANNEL)
                backoff = 1.0
                async for m in ps.listen():
                    if m.get("type") == "message":
                        envelope = self.decode_foreign(m["data"])
                        if envelope is not None:
                            client_hub.publish(envelope)
            except Exception as exc:
                log.warning("ws pubsub subscriber lost: %s — retry in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            finally:
                if ps is not None:
                    try:
                        await ps.aclose()
                    except Exception:
                        pass


_broadcaster: Broadcaster | None = None


def get_broadcaster() -> Broadcaster:
    global _broadcaster
    if _broadcaster is None:
        if get_settings().ws_pubsub_enabled:
            _broadcaster = RedisPubSubBroadcaster()
        else:
            _broadcaster = LocalBroadcaster()
    return _broadcaster


def reset_broadcaster() -> None:
    global _broadcaster
    _broadcaster = None


class TelemetryThrottle:
    """Aggregate telemetry latest-wins mỗi (gateway, slave) theo §4.2.

    Frame đầu của mỗi cửa sổ gửi ngay (leading); frame sau trong cửa sổ được giữ lại
    (giá trị mới nhất) và gửi đúng boundary `last_emit + interval` qua trailing timer.
    Gate pure-sẽ bị quantize theo nhịp input (input 100 ms + throttle 250 ms -> chu kỳ thực 300 ms),
    trailing flush đảm bảo nhịp ra ≈ interval — yêu cầu DoD ±10%.

    status/event/info/diag KHÔNG qua throttle (§4.2 — luôn gửi ngay).
    """

    def __init__(
        self,
        min_interval_s: float,
        publish: Callable[[dict], Awaitable[None]],
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._interval = min_interval_s
        self._publish = publish
        self._now = now
        self._sleep = sleep
        self._last_emit: dict[Key, float] = {}
        self._pending: dict[Key, dict] = {}
        self._timers: dict[Key, asyncio.Task] = {}

    async def submit(self, envelope: dict) -> None:
        if self._interval <= 0:
            await self._publish(envelope)
            return
        data = envelope["data"]
        key: Key = (data["gateway_id"], data.get("slave_addr", 1))
        now = self._now()
        last = self._last_emit.get(key)
        if last is None or now - last >= self._interval:
            self._pending.pop(key, None)  # envelope mới hơn mọi pending — hủy flush cũ
            self._last_emit[key] = now
            await self._publish(envelope)
            return
        self._pending[key] = envelope  # giá trị mới nhất thắng
        timer = self._timers.get(key)
        if timer is None or timer.done():
            self._timers[key] = asyncio.create_task(
                self._flush_at(key, last + self._interval - now)
            )

    async def _flush_at(self, key: Key, delay: float) -> None:
        try:
            await self._sleep(max(delay, 0.0))
            env = self._pending.pop(key, None)
            self._timers.pop(key, None)
            if env is not None:
                self._last_emit[key] = self._now()
                await self._publish(env)
        except asyncio.CancelledError:
            self._pending.pop(key, None)
            self._timers.pop(key, None)
            raise
        except Exception as exc:
            log.warning("ws throttle flush failed for %s: %s", key, exc)


_throttle: TelemetryThrottle | None = None


async def _publish_envelope(envelope: dict) -> None:
    """WS không bao giờ được làm hỏng vòng ingestion — mọi lỗi chỉ log."""
    try:
        await get_broadcaster().publish(envelope)
    except Exception as exc:
        log.warning("ws broadcast failed (%s): %s", envelope.get("type"), exc)


def get_throttle() -> TelemetryThrottle:
    global _throttle
    if _throttle is None:
        _throttle = TelemetryThrottle(
            get_settings().ws_telemetry_min_interval_ms / 1000.0, publish=_publish_envelope
        )
    return _throttle


def reset_throttle() -> None:
    global _throttle
    if _throttle is not None:
        for task in _throttle._timers.values():
            task.cancel()
    _throttle = None


def make_envelope(msg: NormalizedMessage) -> dict:
    return {"type": msg.kind, "ts": iso_z(datetime.now(UTC)), "data": msg.model_dump(mode="json")}


async def submit_telemetry(msg: NormalizedMessage) -> None:
    await get_throttle().submit(make_envelope(msg))


async def broadcast_message(msg: NormalizedMessage) -> None:
    await _publish_envelope(make_envelope(msg))

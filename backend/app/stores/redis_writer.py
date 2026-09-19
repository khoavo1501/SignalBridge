import json

from app.parsers.base import Status, Telemetry
from app.stores.redis_client import get_redis

counters: dict[str, int] = {"redis_errors": 0}


def _latest_key(gateway_id: str, slave_addr: int) -> str:
    return f"sb:latest:{gateway_id}:{slave_addr}"


def _status_key(gateway_id: str) -> str:
    return f"sb:status:{gateway_id}"


def _last_seen_key(gateway_id: str) -> str:
    return f"sb:last_seen:{gateway_id}"


async def write_telemetry(msg: Telemetry) -> None:
    try:
        r = get_redis()
        mapping = {k: json.dumps(v) for k, v in msg.signals.items()}
        mapping["_received_at"] = msg.received_at.isoformat()
        mapping["_seq"] = str(msg.seq) if msg.seq is not None else ""
        key = _latest_key(msg.gateway_id, msg.slave_addr)
        seen = _last_seen_key(msg.gateway_id)
        await r.hset(key, mapping=mapping)
        await r.set(seen, str(msg.received_at.timestamp()))
    except Exception as exc:
        counters["redis_errors"] += 1
        raise RuntimeError(f"redis telemetry write failed: {exc}") from exc


async def write_status(msg: Status) -> bool:
    """Ghi sb:status:{gw}. Trả về True nếu state THAY ĐỔI so với giá trị trước
    (dedupe: broker replay retain / status định kỳ 30 s không được tính là chuyển trạng thái)."""
    try:
        r = get_redis()
        key = _status_key(msg.gateway_id)
        prev = await r.hget(key, "state")
        if isinstance(prev, bytes):
            prev = prev.decode()
        changed = prev != msg.state
        mapping = {"state": msg.state, "reason": msg.reason or ""}
        if changed:
            mapping["since"] = msg.received_at.isoformat()
        await r.hset(key, mapping=mapping)
        return changed
    except Exception as exc:
        counters["redis_errors"] += 1
        raise RuntimeError(f"redis status write failed: {exc}") from exc

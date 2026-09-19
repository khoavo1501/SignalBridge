import json

from app.stores.redis_client import get_redis


def _s(value) -> str | None:
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


async def read_status(gateway_id: str) -> dict | None:
    h = await get_redis().hgetall(f"sb:status:{gateway_id}")
    if not h:
        return None
    return {k.decode() if isinstance(k, bytes) else k: _s(v) for k, v in h.items()}


async def read_last_seen(gateway_id: str) -> float | None:
    v = _s(await get_redis().get(f"sb:last_seen:{gateway_id}"))
    return float(v) if v else None


async def read_latest(gateway_id: str, slave_addr: int) -> dict | None:
    h = await get_redis().hgetall(f"sb:latest:{gateway_id}:{slave_addr}")
    if not h:
        return None
    signals: dict[str, bool | int | float] = {}
    received_at = None
    seq = None
    for k, v in h.items():
        key = k.decode() if isinstance(k, bytes) else k
        val = v.decode() if isinstance(v, bytes) else str(v)
        if key == "_received_at":
            received_at = val
        elif key == "_seq":
            seq = int(val) if val else None
        else:
            signals[key] = json.loads(val)
    return {"slave_addr": slave_addr, "received_at": received_at, "seq": seq, "signals": signals}

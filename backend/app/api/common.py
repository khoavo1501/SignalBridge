from datetime import UTC, datetime

from app.api.errors import ApiError
from app.stores import postgres


def iso_z(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def compute_badge(
    state: str | None, last_seen: float | None, now: float, threshold_s: int
) -> tuple[str, bool, bool]:
    """§3.3 — online vs freshness là hai khái niệm riêng (ràng buộc #5)."""
    state_online = state == "online"
    fresh = last_seen is not None and (now - last_seen) < threshold_s
    if not state_online:
        badge = "offline"
    elif fresh:
        badge = "online"
    else:
        badge = "stale"
    return badge, state_online, fresh


async def require_gateway(gateway_id: str) -> dict:
    gw = await postgres.fetch_gateway(gateway_id)
    if gw is None:
        raise ApiError(404, "gateway_not_found", f"gateway {gateway_id} chưa đăng ký")
    return gw


async def require_slave(gateway_pk: int, slave_addr: int) -> dict:
    slaves = await postgres.fetch_slaves(gateway_pk)
    for s in slaves:
        if s["slave_addr"] == slave_addr:
            return s
    raise ApiError(404, "slave_not_found", f"slave {slave_addr} không tồn tại trên gateway")


def parse_iso(name: str, value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiError(
            400, "invalid_request", f"tham số {name} không phải ISO-8601: {value}"
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt

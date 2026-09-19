from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.api.common import compute_badge, iso_z
from app.config import get_settings
from app.deps import get_current_user
from app.stores import postgres, redis_reader

router = APIRouter(prefix="/api/v1", tags=["dashboard"], dependencies=[Depends(get_current_user)])


def _metric_entries(latest: dict | None, defs: list[dict]) -> list[dict]:
    """primary_metrics = signal analog/counter gần nhất (bỏ DI), raw + scaled=false (Q2).

    display_name/unit lấy từ signal_defs nếu admin đã khai báo; chưa có thì dùng key, unit=null.
    """
    if not latest:
        return []
    by_key = {d["key"]: d for d in defs if d.get("enabled", True)}
    out = []
    for key, value in sorted(latest["signals"].items()):
        if key.startswith("di_") or isinstance(value, bool):
            continue
        d = by_key.get(key, {})
        out.append(
            {
                "key": key,
                "display_name": d.get("display_name", key),
                "unit": d.get("unit"),
                "raw": value,
                "value": value,  # Q2: chưa có công thức scale — value = raw, KHÔNG đoán
                "scaled": False,
            }
        )
    return out


async def build_summary() -> dict:
    s = get_settings()
    now = datetime.now(UTC).timestamp()
    gateways = await postgres.fetch_gateways(include_disabled=False)
    items = []
    for gw in gateways:
        status_hash = await redis_reader.read_status(gw["gateway_id"])
        last_seen = await redis_reader.read_last_seen(gw["gateway_id"])
        badge, state_online, fresh = compute_badge(
            (status_hash or {}).get("state"), last_seen, now, s.stale_threshold_s
        )
        slaves = await postgres.fetch_slaves(gw["id"])
        defs = await postgres.fetch_signal_defs(gw["id"])
        latest = (
            await redis_reader.read_latest(gw["gateway_id"], slaves[0]["slave_addr"])
            if slaves
            else None
        )
        items.append(
            {
                "gateway_id": gw["gateway_id"],
                "display_name": gw["display_name"],
                "badge": badge,
                "state": (status_hash or {}).get("state", "unknown"),
                "fresh": fresh,
                "last_telemetry_at": (
                    datetime.fromtimestamp(last_seen, UTC).isoformat().replace("+00:00", "Z")
                    if last_seen
                    else None
                ),
                "fw_version": gw["fw_version"],
                "slave_count": len(slaves),
                "primary_metrics": _metric_entries(latest, defs),
            }
        )
    return {
        "generated_at": iso_z(datetime.now(UTC)),
        "stale_threshold_s": s.stale_threshold_s,
        "gateways": items,
    }


@router.get("/dashboard/summary")
async def dashboard_summary() -> dict:
    return await build_summary()

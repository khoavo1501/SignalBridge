import json
import logging
from datetime import UTC, datetime

import sqlalchemy as sa

from app.parsers import registry
from app.parsers.base import NormalizedMessage
from app.stores.postgres import get_engine

log = logging.getLogger("signalbridge.pipeline")

stats: dict[str, int] = {"received": 0, "parsed": 0, "parse_errors": 0, "unknown_gateway": 0}

_adapter_cache: dict[str, str] = {}
_adapter_cache_loaded: float = 0.0

# M8: gateway_id thấy publish trên broker nhưng chưa có trong DB — cho trang admin quick-add
_unknown_seen: dict[str, str] = {}


def _record_unknown(gateway_id: str, received_at: datetime) -> None:
    _unknown_seen[gateway_id] = received_at.isoformat().replace("+00:00", "Z")


def unknown_seen_snapshot() -> dict[str, str]:
    return dict(_unknown_seen)


async def _adapter_key_for(gateway_id: str) -> str | None:
    global _adapter_cache, _adapter_cache_loaded
    now = datetime.now(UTC).timestamp()
    if now - _adapter_cache_loaded > 60:
        try:
            async with get_engine().connect() as conn:
                rows = await conn.execute(sa.text("SELECT gateway_id, adapter_key FROM gateways"))
                _adapter_cache = {r[0]: r[1] for r in rows}
            _adapter_cache_loaded = now
        except Exception:
            log.warning("cannot load gateway adapter keys from DB (will use match fallback)")
    return _adapter_cache.get(gateway_id)


async def handle_message(topic: str, payload_bytes: bytes) -> list[NormalizedMessage]:
    """Parse payload thành NormalizedMessage. Việc ghi stores diễn ra ở mqtt_client → persist."""
    stats["received"] += 1
    received_at = datetime.now(UTC)
    gateway_id = topic.split("/")[1] if len(topic.split("/")) >= 2 else topic

    try:
        payload = json.loads(payload_bytes)
        if not isinstance(payload, dict):
            raise ValueError("payload is not a JSON object")
    except (ValueError, TypeError) as exc:
        stats["parse_errors"] += 1
        log.warning("parse_error topic=%s err=%s raw=%s", topic, exc, payload_bytes[:200])
        return []

    adapter_key = await _adapter_key_for(gateway_id)
    adapter = registry.get_by_key(adapter_key) if adapter_key else None
    if adapter is None:
        if adapter_key:
            stats["parse_errors"] += 1
            log.error("unknown adapter_key=%s for gateway=%s", adapter_key, gateway_id)
            return []
        stats["unknown_gateway"] += 1
        _record_unknown(gateway_id, received_at)
        log.warning("unknown gateway=%s (not registered), trying match() fallback", gateway_id)
        adapter = registry.resolve_by_match(gateway_id, topic, payload)
        if adapter is None:
            stats["parse_errors"] += 1
            log.warning("parse_error: no adapter matches gateway=%s topic=%s", gateway_id, topic)
            return []

    try:
        messages = adapter.parse(gateway_id, topic, payload, received_at)
    except Exception as exc:
        stats["parse_errors"] += 1
        log.exception("parse_error adapter=%s topic=%s err=%s", adapter.key, topic, exc)
        return []

    for msg in messages:
        stats["parsed"] += 1
        line = json.dumps(
            msg.model_dump(mode="json"), ensure_ascii=False, default=str, sort_keys=False
        )
        log.info("NORMALIZED %s", line)
    return messages


def stats_snapshot() -> dict[str, int]:
    return dict(stats)

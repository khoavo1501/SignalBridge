import asyncio

import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sa_async

from app.config import get_settings


def get_engine() -> sa_async.AsyncEngine:
    # module-level cache qua attr (đơn giản, 1 event loop/progress)
    engine = getattr(get_engine, "_engine", None)
    if engine is None:
        engine = sa_async.create_async_engine(get_settings().database_url, pool_size=5)
        get_engine._engine = engine  # type: ignore[attr-defined]
    return engine


async def check() -> bool:
    try:
        async with asyncio.timeout(3):
            async with get_engine().connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


# ---------- readers (M4 API) ----------

_GATEWAY_COLS = (
    "id, gateway_id, display_name, adapter_key, fw_version, hw_version, ip, mac, "
    "enabled, created_at, updated_at"
)


async def fetch_gateways(include_disabled: bool = True) -> list[dict]:
    where = "" if include_disabled else "WHERE enabled"
    async with get_engine().connect() as conn:
        rows = await conn.execute(
            sa.text(f"SELECT {_GATEWAY_COLS} FROM gateways {where} ORDER BY gateway_id")
        )  # noqa: E501,S501
        return [dict(r._mapping) for r in rows]


async def fetch_gateway(gateway_id: str) -> dict | None:
    async with get_engine().connect() as conn:
        rows = await conn.execute(
            sa.text(f"SELECT {_GATEWAY_COLS} FROM gateways WHERE gateway_id = :gid"),  # noqa: S608
            {"gid": gateway_id},
        )
        r = rows.first()
        return dict(r._mapping) if r else None


async def fetch_slaves(gateway_pk: int) -> list[dict]:
    async with get_engine().connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT slave_addr, name, protocol, enabled FROM slaves "
                "WHERE gateway_id = :gw ORDER BY slave_addr"
            ),
            {"gw": gateway_pk},
        )
        return [dict(r._mapping) for r in rows]


async def fetch_signal_defs(gateway_pk: int) -> list[dict]:
    async with get_engine().connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT key, display_name, unit, kind, enabled FROM signal_defs "
                "WHERE gateway_id = :gw ORDER BY key"
            ),
            {"gw": gateway_pk},
        )
        return [dict(r._mapping) for r in rows]


async def fetch_events(gateway_pk: int, limit: int, before=None, code=None) -> list[dict]:
    sql = """
        SELECT received_at, code, severity, message, source, slave_addr
        FROM gateway_events WHERE gateway_id = :gw
    """
    params: dict = {"gw": gateway_pk, "limit": limit}
    if before is not None:
        sql += " AND received_at < :before"
        params["before"] = before
    if code:
        sql += " AND code = :code"
        params["code"] = code
    sql += " ORDER BY received_at DESC, id DESC LIMIT :limit"
    async with get_engine().connect() as conn:
        rows = await conn.execute(sa.text(sql), params)
        return [dict(r._mapping) for r in rows]


PATCHABLE = {"display_name", "adapter_key", "enabled"}


async def patch_gateway(gateway_id: str, fields: dict) -> dict | None:
    cols = {k: v for k, v in fields.items() if k in PATCHABLE and v is not None}
    if not cols:
        return await fetch_gateway(gateway_id)
    set_clause = ", ".join(f"{k} = :{k}" for k in cols)  # chỉ tên cột hard-coded — không phải input
    async with get_engine().begin() as conn:
        rows = await conn.execute(
            sa.text(
                f"UPDATE gateways SET {set_clause}, updated_at = now() "  # noqa: S608
                "WHERE gateway_id = :gid RETURNING " + _GATEWAY_COLS
            ),
            {**cols, "gid": gateway_id},
        )
        r = rows.first()
        return dict(r._mapping) if r else None

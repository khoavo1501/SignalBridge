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

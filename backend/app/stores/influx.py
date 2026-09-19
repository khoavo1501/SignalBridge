import asyncio

import httpx

from app.config import get_settings


async def check() -> bool:
    s = get_settings()
    try:
        async with asyncio.timeout(3):
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{s.influx_url}/health", timeout=3)
                return resp.status_code == 200 and resp.json().get("status") in ("pass", "ready")
    except Exception:
        return False

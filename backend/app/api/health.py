import asyncio

from fastapi import APIRouter, Response, status

from app.ingestion.mqtt_client import tcp_check
from app.stores import influx, postgres, redis_client

router = APIRouter(prefix="/api/v1", tags=["health"])


async def _checks() -> dict[str, bool]:
    pg, ifx, rds, mqtt = await asyncio.gather(
        postgres.check(), influx.check(), redis_client.check(), tcp_check()
    )
    return {"postgres": pg, "influxdb": ifx, "redis": rds, "mqtt": mqtt}


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/health")
async def health(resp: Response) -> dict:
    checks = await _checks()
    ok = all(checks.values())
    if not ok:
        resp.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ok else "degraded", "checks": checks}

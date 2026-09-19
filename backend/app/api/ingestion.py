from fastapi import APIRouter

from app.ingestion import persist, pipeline
from app.stores import redis_writer
from app.stores.influx_writer import writer as influx_writer

router = APIRouter(prefix="/api/v1", tags=["ingestion"])


@router.get("/ingestion/stats")
async def ingestion_stats() -> dict:
    return {
        **pipeline.stats_snapshot(),
        **influx_writer.counters,
        **redis_writer.counters,
        **persist.counters,
    }

from fastapi import APIRouter

from app.ingestion import pipeline

router = APIRouter(prefix="/api/v1", tags=["ingestion"])


@router.get("/ingestion/stats")
async def ingestion_stats() -> dict:
    return pipeline.stats_snapshot()

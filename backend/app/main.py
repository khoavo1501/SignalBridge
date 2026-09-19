import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.ingestion import router as ingestion_router
from app.config import get_settings
from app.ingestion.mqtt_client import run_ingestion
from app.logging_config import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if get_settings().ingest_enabled:
        task = asyncio.create_task(run_ingestion())
    yield
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="SignalBridge", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(ingestion_router)
    return app


app = create_app()

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dashboard import router as dashboard_router
from app.api.errors import install_error_handlers
from app.api.gateways import router as gateways_router
from app.api.health import router as health_router
from app.api.ingestion import router as ingestion_router
from app.config import get_settings
from app.ingestion.mqtt_client import run_ingestion
from app.logging_config import setup_logging
from app.stores.influx_writer import writer as influx_writer


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if get_settings().ingest_enabled:
        influx_writer.start()
        task = asyncio.create_task(run_ingestion())
    yield
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await influx_writer.stop()  # flush điểm cuối trước khi tắt


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="SignalBridge", version="0.1.0", lifespan=lifespan)
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(ingestion_router)
    app.include_router(dashboard_router)
    app.include_router(gateways_router)
    return app


app = create_app()

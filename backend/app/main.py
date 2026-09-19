from fastapi import FastAPI

from app.api.health import router as health_router
from app.logging_config import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="SignalBridge", version="0.1.0")
    app.include_router(health_router)
    return app


app = create_app()

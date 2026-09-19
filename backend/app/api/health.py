from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

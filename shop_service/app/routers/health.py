from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.events import get_redis

router = APIRouter(prefix="/api/shop", tags=["health"])


@router.get("/health/", summary="Service health (used by Docker)")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001
        database = "unavailable"
    try:
        await get_redis().ping()
        redis_status = "ok"
    except Exception:  # noqa: BLE001
        redis_status = "unavailable"

    healthy = database == "ok"
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy and redis_status == "ok" else "degraded",
            "service": "shop",
            "database": database,
            "redis": redis_status,
        },
    )

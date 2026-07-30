"""Healthcheck: usado pelo docker-compose, pelo deploy e pelo monitoramento."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "error"

    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "environment": settings.environment,
        "version": "0.1.0",
    }

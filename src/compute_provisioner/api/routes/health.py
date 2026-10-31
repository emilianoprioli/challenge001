from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from compute_provisioner.db.session import engine

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "ready", "not_ready"]


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    """Report whether the API process is alive."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def readiness(response: Response) -> HealthResponse:
    """Report readiness only when PostgreSQL accepts a minimal query."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="not_ready")
    return HealthResponse(status="ready")

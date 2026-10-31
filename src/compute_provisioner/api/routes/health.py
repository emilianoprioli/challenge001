from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "ready"]


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    """Report whether the API process is alive."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def readiness() -> HealthResponse:
    """Report whether the API is ready to receive traffic.

    Database and provider checks will be added when those dependencies are wired.
    """
    return HealthResponse(status="ready")

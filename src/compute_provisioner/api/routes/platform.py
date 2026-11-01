import socket
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter
from sqlalchemy import func, select

from compute_provisioner.api.routes.resource_requests import DbSession
from compute_provisioner.core.config import get_settings
from compute_provisioner.db.models import RequestStatus, ResourceRequest
from compute_provisioner.db.session import engine
from compute_provisioner.services.railway import RailwayInfrastructureClient

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])
settings = get_settings()
railway_client = RailwayInfrastructureClient(
    token=settings.railway_project_token,
    environment_id=settings.railway_environment_id,
    cache_seconds=settings.railway_metrics_cache_seconds,
)


@router.get("/snapshot")
def platform_snapshot(session: DbSession) -> dict:
    counts = dict(
        session.execute(
            select(RequestStatus.code, func.count(ResourceRequest.id))
            .outerjoin(ResourceRequest, ResourceRequest.status_id == RequestStatus.id)
            .group_by(RequestStatus.code)
        ).all()
    )
    oldest_pending = session.scalar(
        select(func.min(ResourceRequest.created_at))
        .join(RequestStatus, RequestStatus.id == ResourceRequest.status_id)
        .where(RequestStatus.code == "PENDING")
    )
    oldest_age = (
        max(0.0, (datetime.now(UTC) - oldest_pending).total_seconds())
        if oldest_pending
        else 0.0
    )
    provider: dict = {"reachable": False}
    try:
        response = httpx.get(f"{settings.provider_url}/capacity", timeout=1.5)
        response.raise_for_status()
        provider = {"reachable": True, **response.json()}
    except httpx.HTTPError as exc:
        provider["error"] = type(exc).__name__

    pool = engine.pool
    return {
        "timestamp": datetime.now(UTC),
        "api_instance_id": socket.gethostname(),
        "queue": {
            "pending": counts.get("PENDING", 0),
            "provisioning": counts.get("PROVISIONING", 0),
            "unknown": counts.get("UNKNOWN", 0),
            "oldest_pending_age_seconds": round(oldest_age, 3),
        },
        "database_pool": {
            "size": pool.size(),
            "capacity": pool.size() + settings.database_max_overflow,
            "checked_out": pool.checkedout(),
            "overflow_in_use": max(0, pool.overflow()),
        },
        "provider": provider,
        "railway": railway_client.snapshot(),
    }

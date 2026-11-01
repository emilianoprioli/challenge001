import asyncio
import socket
import uuid
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from compute_provisioner.core.config import get_settings


class ProviderScenario(StrEnum):
    HEALTHY = "healthy"
    SLOW = "slow"
    TIMEOUT = "timeout"
    ERROR = "error"


class ProvisionRequest(BaseModel):
    application_id: uuid.UUID
    cpu_per_replica: float = Field(gt=0)
    memory_per_replica_mb: int = Field(gt=0)
    replicas: int = Field(gt=0)


class ProvisionedResource(ProvisionRequest):
    resource_id: uuid.UUID
    operation_id: uuid.UUID
    provider_status: str


def create_provider_app(
    max_concurrency: int | None = None,
    max_queue_size: int | None = None,
    processing_ms: int | None = None,
) -> FastAPI:
    settings = get_settings()
    concurrency = max_concurrency or settings.provider_max_concurrency
    queue_limit = (
        max_queue_size if max_queue_size is not None else settings.provider_max_queue_size
    )
    processing_time_ms = (
        processing_ms if processing_ms is not None else settings.provider_processing_ms
    )
    base_delay = processing_time_ms / 1000
    application = FastAPI(title="Infrastructure Provider Simulator", version="0.2.0")
    resources: dict[str, ProvisionedResource] = {}
    resource_lock = asyncio.Lock()
    state_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(concurrency)
    state = {"in_flight": 0, "waiting": 0, "accepted": 0, "rejected": 0, "completed": 0}

    @asynccontextmanager
    async def capacity_slot():
        queued = False
        async with state_lock:
            if state["in_flight"] >= concurrency:
                if state["waiting"] >= queue_limit:
                    state["rejected"] += 1
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="provider capacity queue is full",
                        headers={"Retry-After": "1"},
                    )
                state["waiting"] += 1
                queued = True
            state["accepted"] += 1
        await semaphore.acquire()
        async with state_lock:
            if queued:
                state["waiting"] -= 1
            state["in_flight"] += 1
        try:
            yield
        finally:
            semaphore.release()
            async with state_lock:
                state["in_flight"] -= 1
                state["completed"] += 1

    async def apply_scenario(scenario: ProviderScenario) -> None:
        await asyncio.sleep(base_delay)
        if scenario is ProviderScenario.SLOW:
            await asyncio.sleep(2)
        elif scenario is ProviderScenario.ERROR:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="simulated provider outage",
            )

    @application.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/capacity")
    async def capacity() -> dict[str, int | str]:
        async with state_lock:
            return {
                "instance_id": socket.gethostname(),
                "max_concurrency": concurrency,
                "max_queue_size": queue_limit,
                "resource_count": len(resources),
                **state,
            }

    @application.put("/resources/{idempotency_key}", response_model=ProvisionedResource)
    async def provision(
        idempotency_key: str,
        request: ProvisionRequest,
        x_provider_scenario: Annotated[ProviderScenario, Header()] = ProviderScenario.HEALTHY,
    ) -> ProvisionedResource:
        async with capacity_slot():
            if x_provider_scenario is not ProviderScenario.TIMEOUT:
                await apply_scenario(x_provider_scenario)
            else:
                await asyncio.sleep(base_delay)

            async with resource_lock:
                existing = resources.get(idempotency_key)
                if existing is not None:
                    comparable = existing.model_dump(
                        exclude={"resource_id", "operation_id", "provider_status"}
                    )
                    if comparable != request.model_dump():
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="idempotency key was already used with a different payload",
                        )
                    return existing
                resource = ProvisionedResource(
                    **request.model_dump(),
                    resource_id=uuid.uuid4(),
                    operation_id=uuid.uuid4(),
                    provider_status="ACTIVE",
                )
                resources[idempotency_key] = resource

            if x_provider_scenario is ProviderScenario.TIMEOUT:
                await asyncio.sleep(30)
            return resource

    @application.get("/resources/{idempotency_key}", response_model=ProvisionedResource)
    async def get_resource(
        idempotency_key: str,
        x_provider_scenario: Annotated[ProviderScenario, Header()] = ProviderScenario.HEALTHY,
    ) -> ProvisionedResource:
        async with capacity_slot():
            await apply_scenario(x_provider_scenario)
            resource = resources.get(idempotency_key)
            if resource is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="resource not found",
                )
            return resource

    return application


app = create_provider_app()

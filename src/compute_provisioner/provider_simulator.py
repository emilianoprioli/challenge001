import asyncio
import uuid
from enum import StrEnum
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field


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


def create_provider_app() -> FastAPI:
    application = FastAPI(title="Infrastructure Provider Simulator", version="0.1.0")
    resources: dict[str, ProvisionedResource] = {}

    async def apply_scenario(scenario: ProviderScenario) -> None:
        if scenario is ProviderScenario.SLOW:
            await asyncio.sleep(2)
        elif scenario is ProviderScenario.TIMEOUT:
            # Intentionally longer than the client timeout used by the provisioner.
            await asyncio.sleep(30)
        elif scenario is ProviderScenario.ERROR:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="simulated provider outage",
            )

    @application.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.put("/resources/{idempotency_key}", response_model=ProvisionedResource)
    async def provision(
        idempotency_key: str,
        request: ProvisionRequest,
        x_provider_scenario: Annotated[ProviderScenario, Header()] = ProviderScenario.HEALTHY,
    ) -> ProvisionedResource:
        if x_provider_scenario is not ProviderScenario.TIMEOUT:
            await apply_scenario(x_provider_scenario)

        existing = resources.get(idempotency_key)
        if existing is not None:
            comparable_existing = existing.model_dump(
                exclude={"resource_id", "operation_id", "provider_status"}
            )
            if comparable_existing != request.model_dump():
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
            # The side effect happened, but the caller will time out before receiving the response.
            await asyncio.sleep(30)
        return resource

    @application.get("/resources/{idempotency_key}", response_model=ProvisionedResource)
    async def get_resource(
        idempotency_key: str,
        x_provider_scenario: Annotated[ProviderScenario, Header()] = ProviderScenario.HEALTHY,
    ) -> ProvisionedResource:
        await apply_scenario(x_provider_scenario)
        resource = resources.get(idempotency_key)
        if resource is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource not found")
        return resource

    return application


app = create_provider_app()

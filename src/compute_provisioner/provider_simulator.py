import asyncio
import threading
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Protocol

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from compute_provisioner.core.config import get_settings
from compute_provisioner.core.instance import instance_id, public_instance_id
from compute_provisioner.db.models import ProviderResource
from compute_provisioner.db.session import SessionFactory


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
    provider_instance_id: str


class ProviderConflictError(Exception):
    pass


class ProviderStore(Protocol):
    def provision(
        self, idempotency_key: str, request: ProvisionRequest, owner: str
    ) -> ProvisionedResource: ...

    def get(self, idempotency_key: str) -> ProvisionedResource | None: ...

    def count(self) -> int: ...


def stored_resource(model: ProviderResource) -> ProvisionedResource:
    return ProvisionedResource(
        application_id=model.application_id,
        cpu_per_replica=float(model.cpu_per_replica),
        memory_per_replica_mb=model.memory_per_replica_mb,
        replicas=model.replicas,
        resource_id=model.resource_id,
        operation_id=model.operation_id,
        provider_status=model.provider_status,
        provider_instance_id=model.provider_instance_id,
    )


def same_payload(resource: ProvisionedResource, request: ProvisionRequest) -> bool:
    return resource.model_dump(
        exclude={"resource_id", "operation_id", "provider_status", "provider_instance_id"}
    ) == request.model_dump()


class DatabaseProviderStore:
    def provision(
        self, idempotency_key: str, request: ProvisionRequest, owner: str
    ) -> ProvisionedResource:
        model = ProviderResource(
            idempotency_key=idempotency_key,
            application_id=request.application_id,
            cpu_per_replica=Decimal(str(request.cpu_per_replica)),
            memory_per_replica_mb=request.memory_per_replica_mb,
            replicas=request.replicas,
            resource_id=uuid.uuid4(),
            operation_id=uuid.uuid4(),
            provider_status="ACTIVE",
            provider_instance_id=owner,
        )
        try:
            with SessionFactory.begin() as session:
                session.add(model)
                session.flush()
                result = stored_resource(model)
        except IntegrityError:
            with SessionFactory() as session:
                existing = session.get(ProviderResource, idempotency_key)
                if existing is None:
                    raise
                result = stored_resource(existing)
        if not same_payload(result, request):
            raise ProviderConflictError
        return result

    def get(self, idempotency_key: str) -> ProvisionedResource | None:
        with SessionFactory() as session:
            resource = session.get(ProviderResource, idempotency_key)
            return stored_resource(resource) if resource else None

    def count(self) -> int:
        with SessionFactory() as session:
            return session.scalar(select(func.count()).select_from(ProviderResource)) or 0


class InMemoryProviderStore:
    def __init__(self) -> None:
        self.resources: dict[str, ProvisionedResource] = {}
        self.lock = threading.Lock()

    def provision(
        self, idempotency_key: str, request: ProvisionRequest, owner: str
    ) -> ProvisionedResource:
        with self.lock:
            existing = self.resources.get(idempotency_key)
            if existing is not None:
                if not same_payload(existing, request):
                    raise ProviderConflictError
                return existing
            resource = ProvisionedResource(
                **request.model_dump(),
                resource_id=uuid.uuid4(),
                operation_id=uuid.uuid4(),
                provider_status="ACTIVE",
                provider_instance_id=owner,
            )
            self.resources[idempotency_key] = resource
            return resource

    def get(self, idempotency_key: str) -> ProvisionedResource | None:
        with self.lock:
            return self.resources.get(idempotency_key)

    def count(self) -> int:
        with self.lock:
            return len(self.resources)


def create_provider_app(
    max_concurrency: int | None = None,
    max_queue_size: int | None = None,
    processing_ms: int | None = None,
    store: ProviderStore | None = None,
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
    resource_store = store or DatabaseProviderStore()
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
        resource_count = await asyncio.to_thread(resource_store.count)
        async with state_lock:
            return {
                "instance_id": public_instance_id(instance_id()),
                "max_concurrency": concurrency,
                "max_queue_size": queue_limit,
                "resource_count": resource_count,
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

            try:
                resource = await asyncio.to_thread(
                    resource_store.provision,
                    idempotency_key,
                    request,
                    instance_id(),
                )
            except ProviderConflictError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="idempotency key was already used with a different payload",
                ) from exc

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
            resource = await asyncio.to_thread(resource_store.get, idempotency_key)
            if resource is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="resource not found",
                )
            return resource

    return application


app = create_provider_app()

import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from compute_provisioner.core.config import get_settings
from compute_provisioner.db.models import (
    Application,
    ApplicationResourceDesired,
    ApplicationResourceObservation,
    ApplicationResourcePolicy,
    Department,
    RequestStatus,
    ResourceRequest,
    SimulationControl,
)
from compute_provisioner.db.session import get_db_session


def require_lab_access(x_simulation_key: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().simulation_key
    if expected and x_simulation_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing simulation key")


router = APIRouter(
    prefix="/api/v1",
    tags=["resource requests"],
    dependencies=[Depends(require_lab_access)],
)
DbSession = Annotated[Session, Depends(get_db_session)]
Scenario = Literal[
    "normal",
    "degraded",
    "critical",
    "healthy",
    "slow",
    "timeout",
    "error",
]


class ResourceRequestInput(BaseModel):
    cpu_per_replica: Decimal = Field(gt=0)
    memory_per_replica_mb: int = Field(gt=0)
    replicas: int = Field(gt=0)
    simulated_scenario: Scenario = "normal"


class ResourceRequestOutput(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    status: str
    idempotency_key: str
    cpu_per_replica: Decimal
    memory_per_replica_mb: int
    replicas: int
    attempt_count: int
    last_error: str | None
    simulated_scenario: str
    last_provider_scenario: str | None
    created_at: datetime
    updated_at: datetime


class DemoContext(BaseModel):
    department_id: uuid.UUID
    application_id: uuid.UUID
    department_name: str
    application_name: str


class SimulationControlInput(BaseModel):
    worker_paused: bool
    degraded_mode: bool


def serialize_request(request: ResourceRequest, status_code: str) -> ResourceRequestOutput:
    return ResourceRequestOutput(
        id=request.id,
        application_id=request.application_id,
        status=status_code,
        idempotency_key=request.idempotency_key,
        cpu_per_replica=request.cpu_per_replica,
        memory_per_replica_mb=request.memory_per_replica_mb,
        replicas=request.replicas,
        attempt_count=request.attempt_count,
        last_error=request.last_error,
        simulated_scenario=request.simulated_scenario,
        last_provider_scenario=request.last_provider_scenario,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


@router.post("/demo/bootstrap", response_model=DemoContext)
def bootstrap_demo(session: DbSession) -> DemoContext:
    with session.begin():
        department = session.scalar(select(Department).where(Department.name == "Platform Demo"))
        if department is None:
            department = Department(
                name="Platform Demo",
                max_cpu=Decimal("100"),
                max_memory_mb=204800,
            )
            session.add(department)
            session.flush()

        application = session.scalar(
            select(Application).where(
                Application.department_id == department.id,
                Application.name == "payments-api",
            )
        )
        if application is None:
            application = Application(department_id=department.id, name="payments-api")
            session.add(application)
            session.flush()
            session.add(
                ApplicationResourcePolicy(
                    application_id=application.id,
                    max_cpu_per_replica=Decimal("8"),
                    max_memory_per_replica_mb=16384,
                    max_replicas=20,
                    max_total_cpu=Decimal("80"),
                    max_total_memory_mb=163840,
                )
            )

    return DemoContext(
        department_id=department.id,
        application_id=application.id,
        department_name=department.name,
        application_name=application.name,
    )


@router.get("/demo/control", response_model=SimulationControlInput)
def get_simulation_control(session: DbSession) -> SimulationControlInput:
    control = session.get(SimulationControl, 1)
    return SimulationControlInput(
        worker_paused=control.worker_paused,
        degraded_mode=control.degraded_mode,
    )


@router.put("/demo/control", response_model=SimulationControlInput)
def update_simulation_control(
    payload: SimulationControlInput,
    session: DbSession,
) -> SimulationControlInput:
    with session.begin():
        control = session.get(SimulationControl, 1, with_for_update=True)
        control.worker_paused = payload.worker_paused
        control.degraded_mode = payload.degraded_mode
    return payload


@router.post(
    "/applications/{application_id}/resource-requests",
    response_model=ResourceRequestOutput,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_resource_request(
    application_id: uuid.UUID,
    payload: ResourceRequestInput,
    session: DbSession,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=255)],
) -> ResourceRequestOutput:
    canonical = json.dumps(
        {
            "cpu_per_replica": str(payload.cpu_per_replica),
            "memory_per_replica_mb": payload.memory_per_replica_mb,
            "replicas": payload.replicas,
        },
        sort_keys=True,
    )
    request_hash = hashlib.sha256(canonical.encode()).hexdigest()

    with session.begin():
        existing = session.scalar(
            select(ResourceRequest).where(
                ResourceRequest.application_id == application_id,
                ResourceRequest.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=409,
                    detail="idempotency key reused with another payload",
                )
            return serialize_request(existing, existing.status.code)

        application = session.scalar(
            select(Application).where(Application.id == application_id)
        )
        if application is None:
            raise HTTPException(status_code=404, detail="application not found")

        department = session.scalar(
            select(Department)
            .where(Department.id == application.department_id)
            .with_for_update()
        )
        policy = session.get(ApplicationResourcePolicy, application_id)
        if policy is None:
            raise HTTPException(status_code=409, detail="application has no resource policy")

        total_cpu = payload.cpu_per_replica * payload.replicas
        total_memory = payload.memory_per_replica_mb * payload.replicas
        if (
            payload.cpu_per_replica > policy.max_cpu_per_replica
            or payload.memory_per_replica_mb > policy.max_memory_per_replica_mb
            or payload.replicas > policy.max_replicas
            or total_cpu > policy.max_total_cpu
            or total_memory > policy.max_total_memory_mb
        ):
            raise HTTPException(status_code=422, detail="request exceeds application policy")

        used_cpu, used_memory = session.execute(
            select(
                func.coalesce(func.sum(ApplicationResourceDesired.reserved_cpu), 0),
                func.coalesce(func.sum(ApplicationResourceDesired.reserved_memory_mb), 0),
            )
            .join(Application, Application.id == ApplicationResourceDesired.application_id)
            .where(Application.department_id == department.id)
        ).one()
        current = session.get(ApplicationResourceDesired, application_id)
        if current is not None:
            used_cpu -= current.reserved_cpu
            used_memory -= current.reserved_memory_mb
        exceeds_cpu = used_cpu + total_cpu > department.max_cpu
        exceeds_memory = used_memory + total_memory > department.max_memory_mb
        if exceeds_cpu or exceeds_memory:
            raise HTTPException(status_code=409, detail="department quota is insufficient")

        if current is None:
            current = ApplicationResourceDesired(application_id=application_id)
            session.add(current)
        current.cpu_per_replica = payload.cpu_per_replica
        current.memory_per_replica_mb = payload.memory_per_replica_mb
        current.replicas = payload.replicas
        current.reserved_cpu = total_cpu
        current.reserved_memory_mb = total_memory
        current.version = (current.version or 0) + 1

        pending = session.scalar(select(RequestStatus).where(RequestStatus.code == "PENDING"))
        request = ResourceRequest(
            application_id=application_id,
            status_id=pending.id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            cpu_per_replica=payload.cpu_per_replica,
            memory_per_replica_mb=payload.memory_per_replica_mb,
            replicas=payload.replicas,
            simulated_scenario=payload.simulated_scenario,
        )
        session.add(request)
        session.flush()
        session.execute(select(func.pg_notify("resource_requests", str(request.id))))
        output = serialize_request(request, "PENDING")

    return output


@router.get("/resource-requests", response_model=list[ResourceRequestOutput])
def list_resource_requests(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ResourceRequestOutput]:
    rows = session.execute(
        select(ResourceRequest, RequestStatus.code)
        .join(RequestStatus, RequestStatus.id == ResourceRequest.status_id)
        .order_by(ResourceRequest.created_at.desc())
        .limit(limit)
    ).all()
    return [serialize_request(request, status_code) for request, status_code in rows]


@router.get("/applications/{application_id}/resources")
def get_application_resources(application_id: uuid.UUID, session: DbSession) -> dict:
    desired = session.get(ApplicationResourceDesired, application_id)
    observed = session.get(ApplicationResourceObservation, application_id)
    if desired is None:
        raise HTTPException(status_code=404, detail="desired resources not found")
    return {
        "desired": {
            "cpu_per_replica": desired.cpu_per_replica,
            "memory_per_replica_mb": desired.memory_per_replica_mb,
            "replicas": desired.replicas,
            "version": desired.version,
        },
        "observed": None
        if observed is None
        else {
            "provider_status": observed.provider_status,
            "provisioned_replicas": observed.provisioned_replicas,
            "ready_replicas": observed.ready_replicas,
            "observed_at": observed.observed_at,
        },
    }

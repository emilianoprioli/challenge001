import asyncio
import contextlib
import logging
import random
import sys
from datetime import UTC, datetime, timedelta

import httpx
import psycopg
from sqlalchemy import or_, select

from compute_provisioner.core.config import get_settings
from compute_provisioner.core.instance import instance_id
from compute_provisioner.db.models import (
    ApplicationResourceObservation,
    RequestStatus,
    ResourceRequest,
    SimulationControl,
)
from compute_provisioner.db.session import SessionFactory

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("compute-provisioner-worker")
settings = get_settings()
worker_name = instance_id()
wake_event = asyncio.Event()

FAILURE_PROFILES: dict[str, tuple[tuple[str, float], ...]] = {
    "normal": (("healthy", 1.0),),
    "degraded": (
        ("healthy", 0.80),
        ("slow", 0.15),
        ("error", 0.03),
        ("timeout", 0.02),
    ),
    "critical": (
        ("healthy", 0.30),
        ("slow", 0.40),
        ("error", 0.20),
        ("timeout", 0.10),
    ),
}


def status_id(session, code: str):
    return session.scalar(select(RequestStatus.id).where(RequestStatus.code == code))


def claim_next_request() -> ResourceRequest | None:
    now = datetime.now(UTC)
    with SessionFactory.begin() as session:
        control = session.get(SimulationControl, 1)
        if control is not None and control.worker_paused:
            return None
        pending_id = status_id(session, "PENDING")
        request = session.scalar(
            select(ResourceRequest)
            .where(
                ResourceRequest.status_id == pending_id,
                or_(ResourceRequest.next_retry_at.is_(None), ResourceRequest.next_retry_at <= now),
            )
            .order_by(ResourceRequest.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if request is None:
            return None
        request.status_id = status_id(session, "PROVISIONING")
        request.processing_owner = worker_name
        request.processing_started_at = now
        request.attempt_count += 1
        session.flush()
        session.expunge(request)
        return request


def provider_payload(request: ResourceRequest) -> dict:
    return {
        "application_id": str(request.application_id),
        "cpu_per_replica": float(request.cpu_per_replica),
        "memory_per_replica_mb": request.memory_per_replica_mb,
        "replicas": request.replicas,
    }


def choose_provider_scenario(configured: str) -> str:
    profile = FAILURE_PROFILES.get(configured)
    if profile is None:
        return configured
    scenarios, weights = zip(*profile, strict=True)
    return random.choices(scenarios, weights=weights, k=1)[0]


def record_provider_scenario(request_id, scenario: str) -> None:
    with SessionFactory.begin() as session:
        request = session.get(ResourceRequest, request_id, with_for_update=True)
        request.last_provider_scenario = scenario


def mark_active(request_id, provider_data: dict) -> None:
    now = datetime.now(UTC)
    with SessionFactory.begin() as session:
        request = session.get(ResourceRequest, request_id, with_for_update=True)
        request.status_id = status_id(session, "ACTIVE")
        request.external_operation_id = provider_data["operation_id"]
        request.worker_instance_id = request.processing_owner
        request.provider_instance_id = provider_data.get("provider_instance_id")
        request.processing_owner = None
        request.processing_started_at = None
        request.last_error = None
        observation = session.get(ApplicationResourceObservation, request.application_id)
        if observation is None:
            observation = ApplicationResourceObservation(application_id=request.application_id)
            session.add(observation)
        observation.external_resource_id = provider_data["resource_id"]
        observation.observed_cpu = request.cpu_per_replica * request.replicas
        observation.observed_memory_mb = request.memory_per_replica_mb * request.replicas
        observation.provisioned_replicas = request.replicas
        observation.ready_replicas = request.replicas
        observation.provider_status = provider_data["provider_status"]
        observation.observed_at = now


def mark_unknown(request_id, error: str) -> None:
    with SessionFactory.begin() as session:
        request = session.get(ResourceRequest, request_id, with_for_update=True)
        request.status_id = status_id(session, "UNKNOWN")
        request.last_error = error[:500]
        request.processing_owner = None
        request.processing_started_at = None


def schedule_retry(request_id, error: str) -> None:
    with SessionFactory.begin() as session:
        request = session.get(ResourceRequest, request_id, with_for_update=True)
        if request.attempt_count >= settings.worker_max_attempts:
            request.status_id = status_id(session, "FAILED")
        else:
            request.status_id = status_id(session, "PENDING")
            delay = min(2 ** request.attempt_count, 30)
            request.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
        request.last_error = error[:500]
        request.processing_owner = None
        request.processing_started_at = None


async def provision(request: ResourceRequest, client: httpx.AsyncClient) -> None:
    provider_scenario = choose_provider_scenario(request.simulated_scenario)
    record_provider_scenario(request.id, provider_scenario)
    logger.info(
        "Request %s profile=%s selected_scenario=%s",
        request.id,
        request.simulated_scenario,
        provider_scenario,
    )
    try:
        response = await client.put(
            f"/resources/{request.idempotency_key}",
            json=provider_payload(request),
            headers={"X-Provider-Scenario": provider_scenario},
        )
        if response.status_code >= 500:
            schedule_retry(request.id, f"provider returned {response.status_code}")
            return
        response.raise_for_status()
        mark_active(request.id, response.json())
    except httpx.TimeoutException:
        mark_unknown(request.id, "provider response timed out; external result is unknown")
    except httpx.HTTPError as exc:
        schedule_retry(request.id, str(exc))


async def reconcile_unknown(client: httpx.AsyncClient) -> None:
    with SessionFactory() as session:
        unknown_id = status_id(session, "UNKNOWN")
        request_ids = list(
            session.scalars(
                select(ResourceRequest.id)
                .where(ResourceRequest.status_id == unknown_id)
                .order_by(ResourceRequest.updated_at)
                .limit(10)
            )
        )
    for request_id in request_ids:
        with SessionFactory() as session:
            request = session.get(ResourceRequest, request_id)
            idempotency_key = request.idempotency_key
        try:
            response = await client.get(f"/resources/{idempotency_key}")
            if response.status_code == 200:
                mark_active(request_id, response.json())
            elif response.status_code == 404:
                schedule_retry(request_id, "reconciliation confirmed resource is absent")
        except httpx.HTTPError:
            logger.warning("Reconciliation could not reach provider for %s", request_id)


async def listen_for_work() -> None:
    connection_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(
                connection_url,
                autocommit=True,
            ) as connection:
                await connection.execute("LISTEN resource_requests")
                logger.info("Listening for PostgreSQL notifications")
                async for notification in connection.notifies():
                    logger.debug("Received notification for %s", notification.payload)
                    wake_event.set()
        except (psycopg.Error, OSError) as exc:
            logger.warning("Listener disconnected: %s; reconnecting", exc)
            await asyncio.sleep(2)


async def run() -> None:
    logger.info("Worker %s started", worker_name)
    listener = asyncio.create_task(listen_for_work())
    timeout = httpx.Timeout(settings.provider_timeout_seconds)
    try:
        async with httpx.AsyncClient(base_url=settings.provider_url, timeout=timeout) as client:
            while True:
                request = await asyncio.to_thread(claim_next_request)
                if request is not None:
                    logger.info(
                        "Processing request %s attempt %s",
                        request.id,
                        request.attempt_count,
                    )
                    await provision(request, client)
                    continue

                await reconcile_unknown(client)
                wake_event.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        wake_event.wait(),
                        timeout=settings.worker_poll_seconds,
                    )
    finally:
        listener.cancel()
        await asyncio.gather(listener, return_exceptions=True)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Worker stopped")

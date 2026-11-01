from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from compute_provisioner.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Department(TimestampMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (
        CheckConstraint("max_cpu > 0", name="max_cpu_positive"),
        CheckConstraint("max_memory_mb > 0", name="max_memory_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    max_cpu: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    max_memory_mb: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_pending_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )

    applications: Mapped[list[Application]] = relationship(back_populates="department")
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="department")


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("department_id", "name", name="application_department_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(255), unique=True)

    department: Mapped[Department] = relationship(back_populates="applications")
    resource_policy: Mapped[ApplicationResourcePolicy] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        single_parent=True,
    )
    resource_desired: Mapped[ApplicationResourceDesired] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        single_parent=True,
    )
    resource_observation: Mapped[ApplicationResourceObservation | None] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        single_parent=True,
    )
    resource_requests: Mapped[list[ResourceRequest]] = relationship(back_populates="application")
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="application")


class ApplicationResourcePolicy(Base):
    __tablename__ = "application_resource_policies"
    __table_args__ = (
        CheckConstraint("max_cpu_per_replica > 0", name="max_cpu_per_replica_positive"),
        CheckConstraint(
            "max_memory_per_replica_mb > 0",
            name="max_memory_per_replica_positive",
        ),
        CheckConstraint("max_replicas > 0", name="max_replicas_positive"),
        CheckConstraint("max_total_cpu > 0", name="max_total_cpu_positive"),
        CheckConstraint("max_total_memory_mb > 0", name="max_total_memory_positive"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    max_cpu_per_replica: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    max_memory_per_replica_mb: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_replicas: Mapped[int] = mapped_column(Integer, nullable=False)
    max_total_cpu: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    max_total_memory_mb: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    application: Mapped[Application] = relationship(back_populates="resource_policy")


class ApplicationResourceDesired(Base):
    __tablename__ = "application_resource_desired"
    __table_args__ = (
        CheckConstraint("cpu_per_replica > 0", name="cpu_per_replica_positive"),
        CheckConstraint("memory_per_replica_mb > 0", name="memory_per_replica_positive"),
        CheckConstraint("replicas > 0", name="replicas_positive"),
        CheckConstraint("reserved_cpu >= 0", name="reserved_cpu_non_negative"),
        CheckConstraint("reserved_memory_mb >= 0", name="reserved_memory_non_negative"),
        CheckConstraint("version > 0", name="version_positive"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    cpu_per_replica: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    memory_per_replica_mb: Mapped[int] = mapped_column(BigInteger, nullable=False)
    replicas: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_cpu: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reserved_memory_mb: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    application: Mapped[Application] = relationship(back_populates="resource_desired")


class ApplicationResourceObservation(Base):
    __tablename__ = "application_resource_observations"
    __table_args__ = (
        CheckConstraint("observed_cpu >= 0", name="observed_cpu_non_negative"),
        CheckConstraint("observed_memory_mb >= 0", name="observed_memory_non_negative"),
        CheckConstraint("provisioned_replicas >= 0", name="provisioned_replicas_non_negative"),
        CheckConstraint("ready_replicas >= 0", name="ready_replicas_non_negative"),
        CheckConstraint(
            "ready_replicas <= provisioned_replicas",
            name="ready_not_above_provisioned",
        ),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    external_resource_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    observed_cpu: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, default=0, server_default="0"
    )
    observed_memory_mb: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    provisioned_replicas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    ready_replicas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    provider_status: Mapped[str] = mapped_column(String(50), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    application: Mapped[Application] = relationship(back_populates="resource_observation")


class RequestStatus(Base):
    __tablename__ = "request_statuses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allows_retry: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    releases_quota: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    resource_requests: Mapped[list[ResourceRequest]] = relationship(back_populates="status")


class ResourceRequest(TimestampMixin, Base):
    __tablename__ = "resource_requests"
    __table_args__ = (
        UniqueConstraint(
            "application_id",
            "idempotency_key",
            name="resource_request_application_idempotency",
        ),
        CheckConstraint("cpu_per_replica > 0", name="cpu_per_replica_positive"),
        CheckConstraint("memory_per_replica_mb > 0", name="memory_per_replica_positive"),
        CheckConstraint("replicas > 0", name="replicas_positive"),
        Index("ix_resource_requests_status_created", "status_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("request_statuses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cpu_per_replica: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    memory_per_replica_mb: Mapped[int] = mapped_column(BigInteger, nullable=False)
    replicas: Mapped[int] = mapped_column(Integer, nullable=False)
    external_operation_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_owner: Mapped[str | None] = mapped_column(String(120))
    api_instance_id: Mapped[str | None] = mapped_column(String(120))
    worker_instance_id: Mapped[str | None] = mapped_column(String(120))
    provider_instance_id: Mapped[str | None] = mapped_column(String(120))
    last_error: Mapped[str | None] = mapped_column(String(500))
    simulated_scenario: Mapped[str] = mapped_column(
        String(30), nullable=False, default="healthy", server_default="healthy"
    )
    last_provider_scenario: Mapped[str | None] = mapped_column(String(30))

    application: Mapped[Application] = relationship(back_populates="resource_requests")
    status: Mapped[RequestStatus] = relationship(back_populates="resource_requests")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_department_created", "department_id", "created_at"),
        Index("ix_audit_events_entity_created", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_events_correlation", "correlation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"),
        nullable=True,
    )
    external_actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    previous_data: Mapped[dict | None] = mapped_column(JSON)
    new_data: Mapped[dict | None] = mapped_column(JSON)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    department: Mapped[Department] = relationship(back_populates="audit_events")
    application: Mapped[Application | None] = relationship(back_populates="audit_events")


class SimulationControl(Base):
    __tablename__ = "simulation_controls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1, server_default="1")
    worker_paused: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    degraded_mode: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

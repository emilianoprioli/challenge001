"""Create the initial compute provisioner schema.

Revision ID: 20261031_0001
Revises: None
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


STATUS_ROWS = [
    {
        "id": "a0000000-0000-0000-0000-000000000001",
        "code": "PENDING",
        "description": "Accepted locally and waiting to be processed.",
        "terminal": False,
        "allows_retry": False,
        "releases_quota": False,
    },
    {
        "id": "a0000000-0000-0000-0000-000000000002",
        "code": "PROVISIONING",
        "description": "The provider operation is in progress.",
        "terminal": False,
        "allows_retry": False,
        "releases_quota": False,
    },
    {
        "id": "a0000000-0000-0000-0000-000000000003",
        "code": "ACTIVE",
        "description": "The requested capacity is active.",
        "terminal": True,
        "allows_retry": False,
        "releases_quota": False,
    },
    {
        "id": "a0000000-0000-0000-0000-000000000004",
        "code": "UNKNOWN",
        "description": "The provider result is not currently known.",
        "terminal": False,
        "allows_retry": True,
        "releases_quota": False,
    },
    {
        "id": "a0000000-0000-0000-0000-000000000005",
        "code": "FAILED",
        "description": "Provisioning failed and no external resource remains.",
        "terminal": True,
        "allows_retry": False,
        "releases_quota": True,
    },
    {
        "id": "a0000000-0000-0000-0000-000000000006",
        "code": "CANCELLED",
        "description": "The operation was cancelled before completion.",
        "terminal": True,
        "allows_retry": False,
        "releases_quota": True,
    },
]


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("max_cpu", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("max_memory_mb", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("max_cpu > 0", name="max_cpu_positive"),
        sa.CheckConstraint("max_memory_mb > 0", name="max_memory_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
        sa.UniqueConstraint("name", name="uq_departments_name"),
    )

    op.create_table(
        "request_statuses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("terminal", sa.Boolean(), nullable=False),
        sa.Column("allows_retry", sa.Boolean(), nullable=False),
        sa.Column("releases_quota", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_request_statuses"),
        sa.UniqueConstraint("code", name="uq_request_statuses_code"),
    )

    request_statuses = sa.table(
        "request_statuses",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("terminal", sa.Boolean()),
        sa.column("allows_retry", sa.Boolean()),
        sa.column("releases_quota", sa.Boolean()),
    )
    op.bulk_insert(request_statuses, STATUS_ROWS)

    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("external_reference", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_applications_department_id_departments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_applications"),
        sa.UniqueConstraint(
            "department_id",
            "name",
            name="uq_applications_application_department_name",
        ),
        sa.UniqueConstraint(
            "external_reference",
            name="uq_applications_external_reference",
        ),
    )
    op.create_index("ix_applications_department_id", "applications", ["department_id"])

    op.create_table(
        "application_resource_policies",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("max_cpu_per_replica", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("max_memory_per_replica_mb", sa.BigInteger(), nullable=False),
        sa.Column("max_replicas", sa.Integer(), nullable=False),
        sa.Column("max_total_cpu", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("max_total_memory_mb", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "max_cpu_per_replica > 0",
            name="max_cpu_per_replica_positive",
        ),
        sa.CheckConstraint(
            "max_memory_per_replica_mb > 0",
            name="max_memory_per_replica_positive",
        ),
        sa.CheckConstraint(
            "max_replicas > 0",
            name="max_replicas_positive",
        ),
        sa.CheckConstraint(
            "max_total_cpu > 0",
            name="max_total_cpu_positive",
        ),
        sa.CheckConstraint(
            "max_total_memory_mb > 0",
            name="max_total_memory_positive",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_application_resource_policies_application_id_applications",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("application_id", name="pk_application_resource_policies"),
    )

    op.create_table(
        "application_resource_desired",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("cpu_per_replica", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("memory_per_replica_mb", sa.BigInteger(), nullable=False),
        sa.Column("replicas", sa.Integer(), nullable=False),
        sa.Column("reserved_cpu", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("reserved_memory_mb", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "cpu_per_replica > 0",
            name="cpu_per_replica_positive",
        ),
        sa.CheckConstraint(
            "memory_per_replica_mb > 0",
            name="memory_per_replica_positive",
        ),
        sa.CheckConstraint(
            "replicas > 0",
            name="replicas_positive",
        ),
        sa.CheckConstraint(
            "reserved_cpu >= 0",
            name="reserved_cpu_non_negative",
        ),
        sa.CheckConstraint(
            "reserved_memory_mb >= 0",
            name="reserved_memory_non_negative",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_application_resource_desired_application_id_applications",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("application_id", name="pk_application_resource_desired"),
    )

    op.create_table(
        "application_resource_observations",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("external_resource_id", sa.String(length=255), nullable=True),
        sa.Column(
            "observed_cpu", sa.Numeric(precision=12, scale=3), server_default="0", nullable=False
        ),
        sa.Column("observed_memory_mb", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("provisioned_replicas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ready_replicas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider_status", sa.String(length=50), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "observed_cpu >= 0",
            name="observed_cpu_non_negative",
        ),
        sa.CheckConstraint(
            "observed_memory_mb >= 0",
            name="observed_memory_non_negative",
        ),
        sa.CheckConstraint(
            "provisioned_replicas >= 0",
            name="provisioned_replicas_non_negative",
        ),
        sa.CheckConstraint(
            "ready_replicas >= 0",
            name="ready_replicas_non_negative",
        ),
        sa.CheckConstraint(
            "ready_replicas <= provisioned_replicas",
            name="ready_not_above_provisioned",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_resource_observations_application",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("application_id", name="pk_application_resource_observations"),
        sa.UniqueConstraint(
            "external_resource_id",
            name="uq_application_resource_observations_external_resource_id",
        ),
    )

    op.create_table(
        "resource_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("status_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("cpu_per_replica", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("memory_per_replica_mb", sa.BigInteger(), nullable=False),
        sa.Column("replicas", sa.Integer(), nullable=False),
        sa.Column("external_operation_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "cpu_per_replica > 0",
            name="cpu_per_replica_positive",
        ),
        sa.CheckConstraint(
            "memory_per_replica_mb > 0",
            name="memory_per_replica_positive",
        ),
        sa.CheckConstraint("replicas > 0", name="replicas_positive"),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_resource_requests_application_id_applications",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["status_id"],
            ["request_statuses.id"],
            name="fk_resource_requests_status_id_request_statuses",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resource_requests"),
        sa.UniqueConstraint(
            "application_id",
            "idempotency_key",
            name="uq_resource_requests_resource_request_application_idempotency",
        ),
        sa.UniqueConstraint(
            "external_operation_id",
            name="uq_resource_requests_external_operation_id",
        ),
    )
    op.create_index("ix_resource_requests_application_id", "resource_requests", ["application_id"])
    op.create_index(
        "ix_resource_requests_status_created",
        "resource_requests",
        ["status_id", "created_at"],
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("external_actor_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("previous_data", sa.JSON(), nullable=True),
        sa.Column("new_data", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_audit_events_application_id_applications",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_audit_events_department_id_departments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index(
        "ix_audit_events_department_created",
        "audit_events",
        ["department_id", "created_at"],
    )
    op.create_index(
        "ix_audit_events_entity_created",
        "audit_events",
        ["entity_type", "entity_id", "created_at"],
    )
    op.create_index("ix_audit_events_correlation", "audit_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("resource_requests")
    op.drop_table("application_resource_observations")
    op.drop_table("application_resource_desired")
    op.drop_table("application_resource_policies")
    op.drop_table("applications")
    op.drop_table("request_statuses")
    op.drop_table("departments")

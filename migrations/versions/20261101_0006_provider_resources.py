"""Persist provider resources for horizontal replicas.

Revision ID: 20261101_0006
Revises: 20261101_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261101_0006"
down_revision: str | None = "20261101_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_resources",
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("cpu_per_replica", sa.Numeric(12, 3), nullable=False),
        sa.Column("memory_per_replica_mb", sa.BigInteger(), nullable=False),
        sa.Column("replicas", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("provider_status", sa.String(50), nullable=False),
        sa.Column("provider_instance_id", sa.String(120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("idempotency_key"),
        sa.UniqueConstraint("resource_id"),
        sa.UniqueConstraint("operation_id"),
    )


def downgrade() -> None:
    op.drop_table("provider_resources")

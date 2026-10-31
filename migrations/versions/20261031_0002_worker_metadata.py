"""Add durable worker metadata to resource requests.

Revision ID: 20261031_0002
Revises: 20261031_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0002"
down_revision: str | None = "20261031_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "simulation_controls",
        sa.Column("id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("worker_paused", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("degraded_mode", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_simulation_controls"),
    )
    op.execute(
        sa.text(
            "INSERT INTO simulation_controls (id, worker_paused, degraded_mode) "
            "VALUES (1, false, false)"
        )
    )
    op.add_column(
        "resource_requests",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("resource_requests", sa.Column("next_retry_at", sa.DateTime(timezone=True)))
    op.add_column(
        "resource_requests", sa.Column("processing_started_at", sa.DateTime(timezone=True))
    )
    op.add_column("resource_requests", sa.Column("processing_owner", sa.String(length=120)))
    op.add_column("resource_requests", sa.Column("last_error", sa.String(length=500)))
    op.add_column(
        "resource_requests",
        sa.Column(
            "simulated_scenario",
            sa.String(length=30),
            server_default="healthy",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_resource_requests_retry_queue",
        "resource_requests",
        ["status_id", "next_retry_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_resource_requests_retry_queue", table_name="resource_requests")
    op.drop_column("resource_requests", "simulated_scenario")
    op.drop_column("resource_requests", "last_error")
    op.drop_column("resource_requests", "processing_owner")
    op.drop_column("resource_requests", "processing_started_at")
    op.drop_column("resource_requests", "next_retry_at")
    op.drop_column("resource_requests", "attempt_count")
    op.drop_table("simulation_controls")

"""Add replica identity to the resource request trace.

Revision ID: 20261101_0005
Revises: 20261031_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261101_0005"
down_revision: str | None = "20261031_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("resource_requests", sa.Column("api_instance_id", sa.String(120)))
    op.add_column("resource_requests", sa.Column("worker_instance_id", sa.String(120)))
    op.add_column("resource_requests", sa.Column("provider_instance_id", sa.String(120)))


def downgrade() -> None:
    op.drop_column("resource_requests", "provider_instance_id")
    op.drop_column("resource_requests", "worker_instance_id")
    op.drop_column("resource_requests", "api_instance_id")

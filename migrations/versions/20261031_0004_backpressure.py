"""Add department backpressure limit.

Revision ID: 20261031_0004
Revises: 20261031_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0004"
down_revision: str | None = "20261031_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "departments",
        sa.Column("max_pending_requests", sa.Integer(), server_default="100", nullable=False),
    )
    op.create_check_constraint(
        "max_pending_requests_positive",
        "departments",
        "max_pending_requests > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_departments_max_pending_requests_positive",
        "departments",
        type_="check",
    )
    op.drop_column("departments", "max_pending_requests")

"""Track the provider scenario selected by failure profiles.

Revision ID: 20261031_0003
Revises: 20261031_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0003"
down_revision: str | None = "20261031_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resource_requests",
        sa.Column("last_provider_scenario", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resource_requests", "last_provider_scenario")

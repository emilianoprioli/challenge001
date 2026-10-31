from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import configure_mappers

from compute_provisioner.db.base import Base
from compute_provisioner.db.models import ResourceRequest


def test_expected_tables_are_registered() -> None:
    expected_tables = {
        "departments",
        "applications",
        "application_resource_policies",
        "application_resource_desired",
        "application_resource_observations",
        "request_statuses",
        "resource_requests",
        "audit_events",
        "simulation_controls",
    }

    assert set(Base.metadata.tables) == expected_tables


def test_all_relationships_can_be_configured() -> None:
    configure_mappers()


def test_resource_request_idempotency_is_scoped_to_application() -> None:
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in ResourceRequest.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("application_id", "idempotency_key") in unique_column_sets

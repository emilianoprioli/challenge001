import uuid

from fastapi.testclient import TestClient

from compute_provisioner.provider_simulator import create_provider_app


def provision_payload() -> dict[str, object]:
    return {
        "application_id": str(uuid.uuid4()),
        "cpu_per_replica": 1.5,
        "memory_per_replica_mb": 1024,
        "replicas": 2,
    }


def test_provider_is_idempotent_for_the_same_key_and_payload() -> None:
    client = TestClient(create_provider_app())
    payload = provision_payload()

    first = client.put("/resources/same-operation", json=payload)
    second = client.put("/resources/same-operation", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()


def test_provider_rejects_reusing_a_key_with_another_payload() -> None:
    client = TestClient(create_provider_app())
    payload = provision_payload()
    client.put("/resources/reused-key", json=payload)
    payload["replicas"] = 3

    response = client.put("/resources/reused-key", json=payload)

    assert response.status_code == 409


def test_provider_can_simulate_an_outage() -> None:
    client = TestClient(create_provider_app())

    response = client.put(
        "/resources/outage",
        json=provision_payload(),
        headers={"X-Provider-Scenario": "error"},
    )

    assert response.status_code == 503

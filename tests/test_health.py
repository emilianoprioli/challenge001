from fastapi.testclient import TestClient

from compute_provisioner.main import create_app


def test_liveness_reports_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_ready() -> None:
    client = TestClient(create_app())

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_simulator_interface_is_served() -> None:
    client = TestClient(create_app())

    response = client.get("/simulator/")

    assert response.status_code == 200
    assert "Flujo de aprovisionamiento" in response.text

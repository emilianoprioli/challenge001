import json

import httpx

from compute_provisioner.services.railway import RailwayInfrastructureClient


def test_disabled_without_credentials() -> None:
    client = RailwayInfrastructureClient(token="", environment_id="")

    assert client.snapshot() == {"enabled": False, "connected": False, "services": []}


def test_normalizes_services_replicas_and_instance_metrics() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Project-Access-Token"] == "secret"
        payload = json.loads(request.content)
        assert payload["variables"]["environmentId"] == "env-1"
        return httpx.Response(
            200,
            json={
                "data": {
                    "environment": {
                        "id": "env-1",
                        "name": "production",
                        "serviceInstances": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "si-1",
                                        "serviceId": "service-1",
                                        "serviceName": "API",
                                        "region": "us-east",
                                        "numReplicas": 2,
                                        "latestDeployment": {
                                            "id": "deployment-1",
                                            "status": "SUCCESS",
                                            "createdAt": "2026-11-01T00:00:00Z",
                                        },
                                    }
                                }
                            ]
                        },
                    },
                    "metrics": [
                        {
                            "measurement": "CPU_USAGE",
                            "tags": {
                                "serviceId": "service-1",
                                "deploymentInstanceId": "abcdef12-3456",
                                "region": "us-east",
                            },
                            "values": [{"ts": 1, "value": 0.25}],
                        },
                        {
                            "measurement": "MEMORY_USAGE_GB",
                            "tags": {
                                "serviceId": "service-1",
                                "deploymentInstanceId": "abcdef12-3456",
                                "region": "us-east",
                            },
                            "values": [{"ts": 1, "value": 0.12}],
                        },
                    ],
                }
            },
        )

    client = RailwayInfrastructureClient(
        token="secret",
        environment_id="env-1",
        transport=httpx.MockTransport(handler),
    )

    snapshot = client.snapshot()

    assert snapshot["connected"] is True
    assert snapshot["services"][0]["replicas_configured"] == 2
    assert snapshot["environment"] == {"name": "production"}
    assert snapshot["services"][0]["instances"][0]["instance_id"] == "replica-abcdef12"
    assert snapshot["services"][0]["instances"][0]["cpu_usage"] == 0.25
    assert snapshot["services"][0]["instances"][0]["memory_usage_gb"] == 0.12

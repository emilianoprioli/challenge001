from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

RAILWAY_GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"

INFRASTRUCTURE_QUERY = """
query Infrastructure($environmentId: String!, $startDate: DateTime!) {
  environment(id: $environmentId) {
    id
    name
    serviceInstances {
      edges {
        node {
          id
          serviceId
          serviceName
          region
          numReplicas
          multiRegionConfig
          latestDeployment { id status createdAt }
        }
      }
    }
  }
  metrics(
    environmentId: $environmentId
    startDate: $startDate
    groupBy: [SERVICE_ID, DEPLOYMENT_INSTANCE_ID, REGION]
    measurements: [CPU_USAGE, CPU_LIMIT, MEMORY_USAGE_GB, MEMORY_LIMIT_GB]
  ) {
    measurement
    tags { serviceId deploymentId deploymentInstanceId region }
    values { ts value }
  }
}
"""


class RailwayInfrastructureClient:
    def __init__(
        self,
        token: str,
        environment_id: str,
        cache_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.token = token
        self.environment_id = environment_id
        self.cache_seconds = cache_seconds
        self.transport = transport
        self._lock = threading.Lock()
        self._cached_at = 0.0
        self._cached: dict[str, Any] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.environment_id)

    def snapshot(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "connected": False, "services": []}

        now = time.monotonic()
        with self._lock:
            if self._cached is not None and now - self._cached_at < self.cache_seconds:
                return {**self._cached, "cached": True}
            result = self._fetch()
            self._cached = result
            self._cached_at = now
            return {**result, "cached": False}

    def _fetch(self) -> dict[str, Any]:
        start_date = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        try:
            with httpx.Client(transport=self.transport, timeout=4.0) as client:
                response = client.post(
                    RAILWAY_GRAPHQL_URL,
                    headers={
                        "Project-Access-Token": self.token,
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": INFRASTRUCTURE_QUERY,
                        "variables": {
                            "environmentId": self.environment_id,
                            "startDate": start_date,
                        },
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return self._error(type(exc).__name__)

        if payload.get("errors"):
            message = payload["errors"][0].get("message", "GraphQL error")
            return self._error(message)

        data = payload.get("data") or {}
        environment = data.get("environment") or {}
        metric_index = self._metric_index(data.get("metrics") or [])
        services = []
        edges = (environment.get("serviceInstances") or {}).get("edges") or []
        for edge in edges:
            node = edge.get("node") or {}
            service_id = node.get("serviceId")
            instances = self._instances_for_service(metric_index, service_id)
            services.append(
                {
                    "name": node.get("serviceName"),
                    "region": node.get("region"),
                    "replicas_configured": self._configured_replicas(node),
                    "deployment": self._public_deployment(node.get("latestDeployment")),
                    "instances": instances,
                }
            )
        return {
            "enabled": True,
            "connected": True,
            "environment": {"name": environment.get("name")},
            "services": services,
            "observed_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _metric_index(metrics: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, float]]:
        index: dict[tuple[str, str], dict[str, float]] = {}
        for series in metrics:
            tags = series.get("tags") or {}
            service_id = tags.get("serviceId")
            instance_id = tags.get("deploymentInstanceId") or "aggregate"
            values = series.get("values") or []
            if not service_id or not values:
                continue
            latest = max(values, key=lambda value: value.get("ts", 0))
            item = index.setdefault(
                (service_id, instance_id),
                {"instance_id": f"replica-{instance_id[:8]}", "region": tags.get("region")},
            )
            item[series.get("measurement", "unknown").lower()] = latest.get("value", 0)
        return index

    @staticmethod
    def _instances_for_service(
        index: dict[tuple[str, str], dict[str, float]], service_id: str | None
    ) -> list[dict[str, float]]:
        return [value for (candidate, _), value in index.items() if candidate == service_id]

    @staticmethod
    def _public_deployment(deployment: dict[str, Any] | None) -> dict[str, Any] | None:
        if not deployment:
            return None
        return {"status": deployment.get("status"), "created_at": deployment.get("createdAt")}

    @staticmethod
    def _configured_replicas(service: dict[str, Any]) -> int:
        regions = service.get("multiRegionConfig") or {}
        configured = sum(
            region.get("numReplicas", 0)
            for region in regions.values()
            if isinstance(region, dict)
        )
        return configured or service.get("numReplicas") or 1

    @staticmethod
    def _error(message: str) -> dict[str, Any]:
        return {"enabled": True, "connected": False, "error": message, "services": []}

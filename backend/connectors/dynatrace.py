"""
Dynatrace connector — fetch problems, metrics, logs, and service topology.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import httpx
from connectors.base import BaseConnector, ConnectorConfig


class DynatraceConnector(BaseConnector):
    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self.base_url = cfg["base_url"].rstrip("/")
        self.headers = {
            "Authorization": f"Api-Token {cfg['api_token']}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v2/{path}"

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(self._url("settings/schemas"), headers=self.headers)
                return {"healthy": r.status_code == 200}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def fetch_alerts(self, severity: str = "all") -> list[dict]:
        """Fetch active Dynatrace problems."""
        params = {"problemSelector": "status(OPEN)", "pageSize": 50}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(self._url("problems"), headers=self.headers, params=params)
            r.raise_for_status()
            problems = r.json().get("problems", [])
            return [
                {
                    "id": p["problemId"],
                    "title": p["title"],
                    "severity": p["severityLevel"].lower(),
                    "status": p["status"],
                    "affected_entities": [e["name"] for e in p.get("affectedEntities", [])],
                    "root_cause_entity": p.get("rootCauseEntity", {}).get("name", ""),
                    "start_time": datetime.fromtimestamp(p["startTime"] / 1000, tz=timezone.utc).isoformat(),
                    "impact": p.get("impactLevel", ""),
                }
                for p in problems
            ]

    async def fetch_logs(self, query: str, window_minutes: int = 15) -> list[dict]:
        """Query Dynatrace Log Monitoring v2."""
        now = datetime.now(timezone.utc)
        params = {
            "query": query,
            "from": f"now-{window_minutes}m",
            "to": "now",
            "limit": 100,
            "sort": "-timestamp",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(self._url("logs/search"), headers=self.headers, params=params)
            r.raise_for_status()
            return r.json().get("results", [])

    async def get_metrics(self, metric_selector: str, entity_selector: str = "", window_minutes: int = 30) -> dict:
        """Fetch metric time-series from Dynatrace."""
        params = {
            "metricSelector": metric_selector,
            "resolution": "1m",
            "from": f"now-{window_minutes}m",
        }
        if entity_selector:
            params["entitySelector"] = entity_selector

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(self._url("metrics/query"), headers=self.headers, params=params)
            r.raise_for_status()
            return r.json()

    async def get_service_topology(self, service_name: str) -> dict:
        """Get service dependencies from Dynatrace Smartscape."""
        params = {"entitySelector": f'type("SERVICE"),entityName("{service_name}")', "fields": "+fromRelationships,+toRelationships"}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(self._url("entities"), headers=self.headers, params=params)
            r.raise_for_status()
            entities = r.json().get("entities", [])
            return entities[0] if entities else {}

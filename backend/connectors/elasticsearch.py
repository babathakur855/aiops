"""
Elasticsearch connector — query logs from ELK stack, OpenSearch, or any ES-compatible store.
Also works for Splunk with HTTP Event Collector (HEC) or ES-compatible API.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import httpx
from connectors.base import BaseConnector, ConnectorConfig


class ElasticsearchConnector(BaseConnector):
    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self.url = cfg["url"].rstrip("/")
        self.headers: dict = {"Content-Type": "application/json"}

        if cfg.get("api_key"):
            self.headers["Authorization"] = f"ApiKey {cfg['api_key']}"
            self.auth = None
        elif cfg.get("username") and cfg.get("password"):
            self.auth = (cfg["username"], cfg["password"])
        else:
            self.auth = None

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self.url}/_cluster/health",
                    headers=self.headers, auth=self.auth,
                )
                data = r.json()
                return {"healthy": data.get("status") in ("green", "yellow"), "status": data.get("status")}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def fetch_logs(self, query: str, window_minutes: int = 15, index: str = "logs-*") -> list[dict]:
        """Full-text log search across the specified index pattern."""
        now = datetime.now(timezone.utc)
        since = (now - timedelta(minutes=window_minutes)).isoformat()

        body = {
            "query": {
                "bool": {
                    "must": [{"query_string": {"query": query}}],
                    "filter": [{"range": {"@timestamp": {"gte": since}}}],
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}],
            "size": 100,
            "_source": ["@timestamp", "message", "level", "service", "host", "kubernetes.pod.name"],
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.url}/{index}/_search",
                headers=self.headers, auth=self.auth, json=body,
            )
            r.raise_for_status()
            hits = r.json().get("hits", {}).get("hits", [])
            return [h["_source"] for h in hits]

    async def fetch_alerts(self, severity: str = "all") -> list[dict]:
        """Fetch Watcher alerts or alerting rules from Kibana/OpenSearch."""
        body = {
            "query": {"term": {"kibana.alert.status": "active"}},
            "sort": [{"kibana.alert.start": {"order": "desc"}}],
            "size": 50,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{self.url}/.alerts-*/_search",
                headers=self.headers, auth=self.auth, json=body,
            )
            if r.status_code == 404:
                return []
            r.raise_for_status()
            hits = r.json().get("hits", {}).get("hits", [])
            return [h["_source"] for h in hits]

    async def get_error_rate(self, service: str, window_minutes: int = 15) -> dict:
        """Aggregate error rate for a service over the window."""
        now = datetime.now(timezone.utc)
        since = (now - timedelta(minutes=window_minutes)).isoformat()
        body = {
            "query": {"bool": {"must": [
                {"term": {"service.name": service}},
                {"range": {"@timestamp": {"gte": since}}},
            ]}},
            "aggs": {
                "total": {"value_count": {"field": "@timestamp"}},
                "errors": {"filter": {"terms": {"level": ["error", "ERROR", "critical", "CRITICAL"]}}},
            },
            "size": 0,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{self.url}/logs-*/_search",
                headers=self.headers, auth=self.auth, json=body,
            )
            r.raise_for_status()
            aggs = r.json().get("aggregations", {})
            total = aggs.get("total", {}).get("value", 0)
            errors = aggs.get("errors", {}).get("doc_count", 0)
            return {
                "service": service,
                "total_logs": total,
                "error_count": errors,
                "error_rate_pct": round((errors / total * 100) if total > 0 else 0, 2),
            }

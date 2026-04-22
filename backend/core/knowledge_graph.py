"""
Service Knowledge Graph — maps dependencies, incident history, and institutional memory.
This powers OpsBrain's context-aware RCA.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


class ServiceKnowledgeGraph:
    """
    In-memory service graph. In production this would be backed by a graph DB (Neo4j / Neptune).
    """

    def __init__(self) -> None:
        self._services: dict[str, dict] = {}
        self._incidents: list[dict] = []
        self._dependencies: dict[str, list[str]] = {}
        self._bootstrap()

    def _bootstrap(self) -> None:
        services = [
            {"name": "api-gateway", "team": "platform", "language": "Go", "criticality": "P0"},
            {"name": "auth-service", "team": "identity", "language": "Python", "criticality": "P0"},
            {"name": "payment-service", "team": "payments", "language": "Java", "criticality": "P0"},
            {"name": "order-service", "team": "commerce", "language": "Go", "criticality": "P1"},
            {"name": "orders-db", "team": "data", "language": "PostgreSQL", "criticality": "P0"},
            {"name": "notification-svc", "team": "platform", "language": "Node.js", "criticality": "P2"},
            {"name": "inventory-service", "team": "commerce", "language": "Python", "criticality": "P1"},
        ]
        for svc in services:
            self._services[svc["name"]] = svc

        self._dependencies = {
            "api-gateway": ["auth-service", "payment-service", "order-service"],
            "order-service": ["orders-db", "inventory-service", "notification-svc"],
            "payment-service": ["payments-db"],
            "auth-service": ["users-db", "redis-cache"],
        }

        self._incidents = [
            {
                "id": "INC-2024-089",
                "title": "orders-db connection pool exhaustion",
                "service": "order-service",
                "root_cause": "Connection pool size not increased when migrating to new pool library",
                "resolved_at": "2024-11-15T14:32:00Z",
                "duration_minutes": 47,
                "recurrence_count": 1,
            },
            {
                "id": "INC-2025-023",
                "title": "payment-service OOM crash loop",
                "service": "payment-service",
                "root_cause": "Memory leak in webhook handler — unbounded queue",
                "resolved_at": "2025-02-08T09:15:00Z",
                "duration_minutes": 23,
                "recurrence_count": 0,
            },
        ]

    def get_service(self, name: str) -> dict | None:
        return self._services.get(name)

    def get_downstream(self, service: str) -> list[str]:
        return self._dependencies.get(service, [])

    def get_upstream(self, service: str) -> list[str]:
        return [s for s, deps in self._dependencies.items() if service in deps]

    def get_blast_radius(self, service: str) -> dict:
        upstream = self.get_upstream(service)
        svc_info = self.get_service(service)
        return {
            "service": service,
            "criticality": svc_info.get("criticality", "unknown") if svc_info else "unknown",
            "directly_impacted_upstream": upstream,
            "cascade_risk": "HIGH" if svc_info and svc_info.get("criticality") == "P0" else "MEDIUM",
        }

    def get_incident_history(self, service: str) -> list[dict]:
        return [i for i in self._incidents if i["service"] == service]

    def add_incident(self, incident: dict) -> None:
        self._incidents.append({**incident, "recorded_at": datetime.utcnow().isoformat()})

    def get_context_for_rca(self, service: str) -> dict:
        """Returns all relevant context for Claude to perform better RCA."""
        return {
            "service_info": self.get_service(service),
            "downstream_dependencies": self.get_downstream(service),
            "upstream_callers": self.get_upstream(service),
            "blast_radius": self.get_blast_radius(service),
            "past_incidents": self.get_incident_history(service),
            "related_services": {
                s: self.get_service(s)
                for s in self.get_downstream(service) + self.get_upstream(service)
                if self.get_service(s)
            },
        }

    def summary(self) -> dict:
        return {
            "total_services": len(self._services),
            "total_incidents_tracked": len(self._incidents),
            "services": list(self._services.keys()),
        }

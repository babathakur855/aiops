"""
Base connector — all integration connectors implement this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from pydantic import BaseModel
from typing import Any


class ConnectorType(str, Enum):
    SERVICENOW = "servicenow"
    CONFLUENCE = "confluence"
    DYNATRACE = "dynatrace"
    ELASTICSEARCH = "elasticsearch"
    SPLUNK = "splunk"
    LOKI = "loki"
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"
    PAGERDUTY = "pagerduty"
    JIRA = "jira"
    PROMETHEUS = "prometheus"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class ConnectorConfig(BaseModel):
    id: str
    name: str
    type: ConnectorType
    enabled: bool = True
    config: dict[str, Any] = {}
    connection_type: str = "data_source"  # "hosting" | "data_source"


class ConnectorStatus(BaseModel):
    id: str
    name: str
    type: str
    enabled: bool
    healthy: bool
    last_checked: str
    error: str | None = None


class BaseConnector(ABC):
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config

    @abstractmethod
    async def test_connection(self) -> dict[str, Any]:
        """Verify connectivity. Returns {healthy: bool, message: str}."""
        pass

    async def fetch_incidents(self, limit: int = 20, **kwargs) -> list[dict]:
        """Fetch open incidents/alerts."""
        return []

    async def create_incident(self, data: dict) -> dict:
        """Create an incident/ticket."""
        return {}

    async def update_incident(self, incident_id: str, data: dict) -> dict:
        """Update an existing incident (e.g. add work notes)."""
        return {}

    async def fetch_documents(self, query: str, limit: int = 5) -> list[dict]:
        """Search for documents/runbooks/SOPs (Confluence, etc.)."""
        return []

    async def fetch_logs(self, query: str, window_minutes: int = 15) -> list[dict]:
        """Fetch log entries matching a query."""
        return []

    async def fetch_alerts(self, severity: str = "all") -> list[dict]:
        """Fetch active monitoring alerts."""
        return []

    async def send_notification(self, message: str, channel: str = "", **kwargs) -> dict:
        """Send a notification (Slack, Teams, email)."""
        return {}

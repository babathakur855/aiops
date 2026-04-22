"""
Connector registry — manages all configured connectors at runtime.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from connectors.base import BaseConnector, ConnectorConfig, ConnectorStatus, ConnectorType
from config.settings import settings


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, BaseConnector] = {}
        self._configs: dict[str, ConnectorConfig] = {}
        self._auto_register()

    def _auto_register(self) -> None:
        """Auto-register connectors from environment variables."""
        if settings.snow_instance_url:
            self.register(ConnectorConfig(
                id="snow-default", name="ServiceNow", type=ConnectorType.SERVICENOW,
                config={"instance_url": settings.snow_instance_url,
                        "username": settings.snow_username, "password": settings.snow_password,
                        "client_id": settings.snow_client_id, "client_secret": settings.snow_client_secret},
            ))
        if settings.confluence_base_url:
            self.register(ConnectorConfig(
                id="confluence-default", name="Confluence", type=ConnectorType.CONFLUENCE,
                config={"base_url": settings.confluence_base_url,
                        "username": settings.confluence_username, "api_token": settings.confluence_api_token},
            ))
        if settings.dynatrace_base_url:
            self.register(ConnectorConfig(
                id="dynatrace-default", name="Dynatrace", type=ConnectorType.DYNATRACE,
                config={"base_url": settings.dynatrace_base_url, "api_token": settings.dynatrace_api_token},
            ))
        if settings.elasticsearch_url:
            self.register(ConnectorConfig(
                id="elasticsearch-default", name="Elasticsearch", type=ConnectorType.ELASTICSEARCH,
                config={"url": settings.elasticsearch_url, "api_key": settings.elasticsearch_api_key,
                        "username": settings.elasticsearch_username, "password": settings.elasticsearch_password},
            ))
        if settings.slack_webhook_url or settings.slack_bot_token:
            self.register(ConnectorConfig(
                id="slack-default", name="Slack", type=ConnectorType.SLACK,
                config={"webhook_url": settings.slack_webhook_url, "bot_token": settings.slack_bot_token},
            ))
        if settings.teams_webhook_url:
            self.register(ConnectorConfig(
                id="teams-default", name="Microsoft Teams", type=ConnectorType.TEAMS,
                config={"webhook_url": settings.teams_webhook_url},
            ))
        if settings.smtp_host:
            self.register(ConnectorConfig(
                id="email-default", name="Email (SMTP)", type=ConnectorType.EMAIL,
                config={"host": settings.smtp_host, "port": settings.smtp_port,
                        "username": settings.smtp_username, "password": settings.smtp_password,
                        "from_email": settings.smtp_from_email},
            ))

    def register(self, config: ConnectorConfig) -> BaseConnector:
        connector = self._build(config)
        self._connectors[config.id] = connector
        self._configs[config.id] = config
        return connector

    def _build(self, config: ConnectorConfig) -> BaseConnector:
        from connectors.snow import ServiceNowConnector
        from connectors.confluence import ConfluenceConnector
        from connectors.dynatrace import DynatraceConnector
        from connectors.elasticsearch import ElasticsearchConnector
        from connectors.slack import SlackConnector
        from connectors.teams import TeamsConnector
        from connectors.email_connector import EmailConnector
        from connectors.aws import AWSConnector
        from connectors.azure import AzureConnector
        from connectors.gcp import GCPConnector

        mapping = {
            ConnectorType.SERVICENOW: ServiceNowConnector,
            ConnectorType.CONFLUENCE: ConfluenceConnector,
            ConnectorType.DYNATRACE: DynatraceConnector,
            ConnectorType.ELASTICSEARCH: ElasticsearchConnector,
            ConnectorType.SLACK: SlackConnector,
            ConnectorType.TEAMS: TeamsConnector,
            ConnectorType.EMAIL: EmailConnector,
            ConnectorType.AWS: AWSConnector,
            ConnectorType.AZURE: AzureConnector,
            ConnectorType.GCP: GCPConnector,
        }
        cls = mapping.get(config.type)
        if not cls:
            raise ValueError(f"No connector implementation for type: {config.type}")
        return cls(config)

    def get(self, connector_id: str) -> BaseConnector | None:
        return self._connectors.get(connector_id)

    def get_by_type(self, connector_type: ConnectorType) -> list[BaseConnector]:
        return [c for cid, c in self._connectors.items()
                if self._configs[cid].type == connector_type and self._configs[cid].enabled]

    def get_hosting_cloud(self) -> ConnectorConfig | None:
        """Return the single connector marked as 'hosting' (where OpsBrain is deployed)."""
        cloud_types = {ConnectorType.AWS, ConnectorType.AZURE, ConnectorType.GCP}
        for cfg in self._configs.values():
            if cfg.type in cloud_types and cfg.connection_type == "hosting":
                return cfg
        return None

    def get_data_sources(self, cloud_type: ConnectorType | None = None) -> list[ConnectorConfig]:
        """Return all data-source cloud connectors, optionally filtered by cloud type."""
        cloud_types = {ConnectorType.AWS, ConnectorType.AZURE, ConnectorType.GCP}
        return [
            cfg for cfg in self._configs.values()
            if cfg.type in cloud_types
            and cfg.connection_type == "data_source"
            and (cloud_type is None or cfg.type == cloud_type)
        ]

    def list_configs(self) -> list[ConnectorConfig]:
        return list(self._configs.values())

    def remove(self, connector_id: str) -> bool:
        if connector_id in self._connectors:
            del self._connectors[connector_id]
            del self._configs[connector_id]
            return True
        return False

    async def health_check_all(self) -> list[ConnectorStatus]:
        results = []
        for cid, connector in self._connectors.items():
            cfg = self._configs[cid]
            try:
                result = await connector.test_connection()
                results.append(ConnectorStatus(
                    id=cid, name=cfg.name, type=cfg.type,
                    enabled=cfg.enabled, healthy=result.get("healthy", False),
                    last_checked=datetime.now(timezone.utc).isoformat(),
                    error=result.get("error"),
                ))
            except Exception as e:
                results.append(ConnectorStatus(
                    id=cid, name=cfg.name, type=cfg.type,
                    enabled=cfg.enabled, healthy=False,
                    last_checked=datetime.now(timezone.utc).isoformat(),
                    error=str(e),
                ))
        return results


registry = ConnectorRegistry()

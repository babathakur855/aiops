"""
Microsoft Teams connector — send adaptive cards and incident notifications.
"""
from __future__ import annotations

import httpx
from connectors.base import BaseConnector, ConnectorConfig


class TeamsConnector(BaseConnector):
    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self.webhook_url = config.config.get("webhook_url", "")

    async def test_connection(self) -> dict:
        try:
            payload = {"text": "OpsBrain connection test ✅"}
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(self.webhook_url, json=payload)
                return {"healthy": r.status_code == 200}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def send_notification(self, message: str, channel: str = "", **kwargs) -> dict:
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": kwargs.get("color", "0076D7"),
            "summary": message[:100],
            "sections": [{"activityText": message}],
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(self.webhook_url, json=payload)
            return {"ok": r.status_code == 200}

    async def send_incident_alert(self, incident: dict, analysis: str) -> dict:
        """Send a formatted Teams adaptive card for an incident."""
        severity = incident.get("severity", "info")
        color = {"critical": "FF0000", "warning": "FFA500", "info": "0076D7"}.get(severity, "0076D7")

        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": f"OpsBrain: {incident.get('alert_name', 'Incident')}",
            "sections": [
                {
                    "activityTitle": f"🔔 OpsBrain Incident — {incident.get('alert_name', '')}",
                    "activitySubtitle": f"Service: **{incident.get('service', '')}** | Severity: **{severity.upper()}**",
                    "facts": [
                        {"name": "Namespace", "value": incident.get("namespace", "")},
                        {"name": "Status", "value": incident.get("status", "Firing")},
                    ],
                },
                {
                    "activityTitle": "AI Analysis",
                    "activityText": analysis[:800],
                },
            ],
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(self.webhook_url, json=payload)
            return {"ok": r.status_code == 200}

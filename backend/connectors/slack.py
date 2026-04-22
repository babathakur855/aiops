"""
Slack connector — send notifications, alerts, and AI analysis summaries.
"""
from __future__ import annotations

import httpx
from connectors.base import BaseConnector, ConnectorConfig


class SlackConnector(BaseConnector):
    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self.webhook_url = cfg.get("webhook_url", "")
        self.bot_token = cfg.get("bot_token", "")

    async def test_connection(self) -> dict:
        try:
            if self.bot_token:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(
                        "https://slack.com/api/auth.test",
                        headers={"Authorization": f"Bearer {self.bot_token}"},
                    )
                    data = r.json()
                    return {"healthy": data.get("ok", False), "team": data.get("team")}
            elif self.webhook_url:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.post(self.webhook_url, json={"text": "OpsBrain connection test"})
                    return {"healthy": r.status_code == 200}
            return {"healthy": False, "error": "No webhook_url or bot_token configured"}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def send_notification(self, message: str, channel: str = "", **kwargs) -> dict:
        """Send a plain text or Block Kit message."""
        blocks = kwargs.get("blocks")
        payload: dict = {}

        if blocks:
            payload["blocks"] = blocks
        else:
            payload["text"] = message

        if channel:
            payload["channel"] = channel

        if self.bot_token and channel:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {self.bot_token}",
                              "Content-Type": "application/json"},
                    json=payload,
                )
                return r.json()
        elif self.webhook_url:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(self.webhook_url, json=payload)
                return {"ok": r.status_code == 200}
        return {"ok": False, "error": "Not configured"}

    async def send_incident_alert(self, incident: dict, analysis: str, channel: str = "#incidents") -> dict:
        """Send a formatted incident alert with AI analysis summary."""
        severity_emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(
            incident.get("severity", "info"), "⚪"
        )
        blocks = [
            {"type": "header", "text": {"type": "plain_text",
             "text": f"{severity_emoji} OpsBrain Incident Alert"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Service:*\n{incident.get('service', 'Unknown')}"},
                {"type": "mrkdwn", "text": f"*Severity:*\n{incident.get('severity', 'Unknown').upper()}"},
                {"type": "mrkdwn", "text": f"*Alert:*\n{incident.get('alert_name', 'Unknown')}"},
            ]},
            {"type": "section", "text": {"type": "mrkdwn",
             "text": f"*AI Analysis Summary:*\n{analysis[:500]}..."}},
            {"type": "divider"},
        ]
        return await self.send_notification("", channel=channel, blocks=blocks)

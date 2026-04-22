"""
ServiceNow connector — bidirectional ITIL integration.
Fetches incidents, writes RCA as work notes, updates priority.
"""
from __future__ import annotations

from typing import Any
import httpx
from connectors.base import BaseConnector, ConnectorConfig


class ServiceNowConnector(BaseConnector):
    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self.instance_url = cfg["instance_url"].rstrip("/")
        self.auth = (cfg["username"], cfg["password"])
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self.instance_url}/api/now/{path}"

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    self._url("table/incident?sysparm_limit=1"),
                    auth=self.auth, headers=self.headers,
                )
                return {"healthy": r.status_code == 200, "status_code": r.status_code}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def fetch_incidents(self, limit: int = 20, state: str = "1,2", **kwargs) -> list[dict]:
        """Fetch open SNOW incidents. state=1 (New), 2 (In Progress)."""
        params = {
            "sysparm_limit": limit,
            "sysparm_query": f"state={state}^ORDERBYDESCsys_created_on",
            "sysparm_fields": "sys_id,number,short_description,description,priority,state,assigned_to,assignment_group,sys_created_on,category",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                self._url("table/incident"),
                auth=self.auth, headers=self.headers, params=params,
            )
            r.raise_for_status()
            return r.json().get("result", [])

    async def get_incident(self, sys_id: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                self._url(f"table/incident/{sys_id}"),
                auth=self.auth, headers=self.headers,
            )
            r.raise_for_status()
            return r.json().get("result", {})

    async def update_incident(self, sys_id: str, data: dict) -> dict:
        """Write RCA back to SNOW — adds work notes, updates priority."""
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.patch(
                self._url(f"table/incident/{sys_id}"),
                auth=self.auth, headers=self.headers, json=data,
            )
            r.raise_for_status()
            return r.json().get("result", {})

    async def add_work_note(self, sys_id: str, note: str) -> dict:
        """Add OpsBrain RCA as a work note in SNOW."""
        return await self.update_incident(sys_id, {
            "work_notes": f"[OpsBrain AI Analysis]\n{note}",
        })

    async def create_incident(self, data: dict) -> dict:
        payload = {
            "short_description": data.get("short_description", "OpsBrain Alert"),
            "description": data.get("description", ""),
            "priority": data.get("priority", "2"),
            "category": data.get("category", "infrastructure"),
            "assignment_group": data.get("assignment_group", ""),
            "work_notes": data.get("work_notes", ""),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                self._url("table/incident"),
                auth=self.auth, headers=self.headers, json=payload,
            )
            r.raise_for_status()
            return r.json().get("result", {})

    async def resolve_incident(self, sys_id: str, resolution_notes: str) -> dict:
        return await self.update_incident(sys_id, {
            "state": "6",  # Resolved
            "close_code": "Solved (Permanently)",
            "close_notes": resolution_notes,
            "work_notes": f"[OpsBrain] Auto-resolved: {resolution_notes}",
        })

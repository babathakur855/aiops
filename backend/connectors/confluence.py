"""
Confluence connector — fetch SOPs, runbooks, and knowledge base articles.
Allows OpsBrain to surface relevant documentation during incident analysis.
"""
from __future__ import annotations

import httpx
from connectors.base import BaseConnector, ConnectorConfig


class ConfluenceConnector(BaseConnector):
    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self.base_url = cfg["base_url"].rstrip("/")
        self.auth = (cfg["username"], cfg["api_token"])
        self.headers = {"Accept": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self.base_url}/wiki/rest/api/{path}"

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(self._url("space?limit=1"), auth=self.auth, headers=self.headers)
                return {"healthy": r.status_code == 200}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def fetch_documents(self, query: str, limit: int = 5, space_key: str = "") -> list[dict]:
        """Search Confluence for SOPs, runbooks, and knowledge articles."""
        cql = f'type=page AND text~"{query}"'
        if space_key:
            cql += f' AND space.key="{space_key}"'

        params = {
            "cql": cql,
            "limit": limit,
            "expand": "body.storage,version,space",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                self._url("content/search"),
                auth=self.auth, headers=self.headers, params=params,
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            return [
                {
                    "id": p["id"],
                    "title": p["title"],
                    "space": p.get("space", {}).get("name", ""),
                    "url": f"{self.base_url}/wiki{p['_links']['webui']}",
                    "excerpt": p.get("body", {}).get("storage", {}).get("value", "")[:500],
                    "last_modified": p.get("version", {}).get("when", ""),
                }
                for p in results
            ]

    async def get_page_content(self, page_id: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                self._url(f"content/{page_id}?expand=body.storage"),
                auth=self.auth, headers=self.headers,
            )
            r.raise_for_status()
            data = r.json()
            return {
                "id": data["id"],
                "title": data["title"],
                "content": data.get("body", {}).get("storage", {}).get("value", ""),
                "url": f"{self.base_url}/wiki{data['_links']['webui']}",
            }

    async def create_page(self, space_key: str, title: str, content: str, parent_id: str = "") -> dict:
        """Publish a generated post-mortem or runbook to Confluence."""
        payload: dict = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": content, "representation": "wiki"}},
        }
        if parent_id:
            payload["ancestors"] = [{"id": parent_id}]

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                self._url("content"), auth=self.auth,
                headers={**self.headers, "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return {"id": data["id"], "title": data["title"],
                    "url": f"{self.base_url}/wiki{data['_links']['webui']}"}

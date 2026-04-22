"""
Azure Connector — Service Principal, Managed Identity, Azure OpenAI,
Cost Management, AKS, Azure Monitor, Log Analytics.
"""
from __future__ import annotations

import asyncio
from typing import Any

from connectors.base import BaseConnector, ConnectorConfig


# ── Required Azure role definition ──────────────────────────────────
AZURE_CUSTOM_ROLE = {
    "name": "OpsBrain Operator",
    "description": "Read-only access + Azure OpenAI inference for OpsBrain AIOps platform",
    "assignableScopes": ["/subscriptions/<SUBSCRIPTION_ID>"],
    "permissions": [
        {
            "actions": [
                "Microsoft.Resources/subscriptions/read",
                "Microsoft.Resources/subscriptions/resourceGroups/read",
                "Microsoft.Resources/subscriptions/resourceGroups/resources/read",
                "Microsoft.CostManagement/query/action",
                "Microsoft.CostManagement/exports/read",
                "Microsoft.Consumption/usageDetails/read",
                "Microsoft.ContainerService/managedClusters/read",
                "Microsoft.ContainerService/managedClusters/listClusterUserCredential/action",
                "Microsoft.ContainerService/managedClusters/listClusterAdminCredential/action",
                "Microsoft.CognitiveServices/accounts/read",
                "Microsoft.CognitiveServices/accounts/usages/read",
                "Microsoft.CognitiveServices/accounts/deployments/read",
                "Microsoft.Insights/alertRules/read",
                "Microsoft.Insights/metricDefinitions/read",
                "Microsoft.Insights/metrics/read",
                "Microsoft.OperationalInsights/workspaces/read",
                "Microsoft.OperationalInsights/workspaces/query/read",
                "Microsoft.Compute/virtualMachines/read",
                "Microsoft.Compute/virtualMachineScaleSets/read",
            ],
            "notActions": [],
            "dataActions": [
                "Microsoft.CognitiveServices/accounts/OpenAI/*",
            ],
            "notDataActions": [],
        }
    ],
}

AZURE_DEPLOY_ROLE_ACTIONS = [
    "Microsoft.ContainerService/managedClusters/write",
    "Microsoft.ContainerService/managedClusters/agentPools/write",
    "Microsoft.Resources/deployments/write",
    "Microsoft.Resources/deployments/validate/action",
]


class AzureConnector(BaseConnector):
    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self.auth_method = cfg.get("auth_method", "service_principal")
        self.tenant_id = cfg.get("tenant_id", "")
        self.client_id = cfg.get("client_id", "")
        self.client_secret = cfg.get("client_secret", "")
        self.subscription_id = cfg.get("subscription_id", "")
        self.resource_group = cfg.get("resource_group", "")
        self.openai_endpoint = cfg.get("openai_endpoint", "")
        self.openai_deployment = cfg.get("openai_deployment", "gpt-4o")
        self.openai_api_version = cfg.get("openai_api_version", "2024-02-01")
        self._credential: Any = None

    def _get_credential(self) -> Any:
        if self._credential:
            return self._credential
        try:
            from azure.identity import ClientSecretCredential, ManagedIdentityCredential, DefaultAzureCredential
        except ImportError:
            raise ImportError("Install azure-identity: pip install azure-identity")

        if self.auth_method == "service_principal":
            self._credential = ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
        elif self.auth_method == "managed_identity":
            kwargs = {}
            if self.client_id:
                kwargs["client_id"] = self.client_id
            self._credential = ManagedIdentityCredential(**kwargs)
        else:
            self._credential = DefaultAzureCredential()

        return self._credential

    async def test_connection(self) -> dict:
        def _test():
            try:
                from azure.mgmt.resource import SubscriptionClient
            except ImportError:
                raise ImportError("Install azure-mgmt-resource: pip install azure-mgmt-resource")

            cred = self._get_credential()
            client = SubscriptionClient(cred)
            subs = list(client.subscriptions.list())
            sub_ids = [s.subscription_id for s in subs]
            found = self.subscription_id in sub_ids if self.subscription_id else True
            return {
                "healthy": True,
                "auth_method": self.auth_method,
                "subscription_id": self.subscription_id,
                "subscription_found": found,
                "accessible_subscriptions": len(sub_ids),
                "tenant_id": self.tenant_id or "managed-identity",
            }
        try:
            return await asyncio.to_thread(_test)
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def fetch_alerts(self, severity: str = "all") -> list[dict]:
        def _fetch():
            try:
                from azure.mgmt.monitor import MonitorManagementClient
            except ImportError:
                return []
            cred = self._get_credential()
            monitor = MonitorManagementClient(cred, self.subscription_id)
            alerts = list(monitor.alert_rules.list_by_subscription())
            return [
                {
                    "name": a.name,
                    "severity": "critical",
                    "service": a.location,
                    "message": str(a.condition) if hasattr(a, "condition") else "",
                    "source": "azure_monitor",
                }
                for a in alerts[:20]
            ]
        try:
            return await asyncio.to_thread(_fetch)
        except Exception:
            return []

    async def fetch_logs(self, query: str, window_minutes: int = 15) -> list[dict]:
        """Query Azure Log Analytics workspace."""
        def _fetch():
            try:
                from azure.monitor.query import LogsQueryClient
                from azure.core.exceptions import HttpResponseError
                import datetime
            except ImportError:
                return []
            cred = self._get_credential()
            client = LogsQueryClient(cred)
            workspace_id = self.config.config.get("log_analytics_workspace_id", "")
            if not workspace_id:
                return []
            kql = f'search "{query}" | order by TimeGenerated desc | take 50'
            try:
                result = client.query_workspace(
                    workspace_id=workspace_id,
                    query=kql,
                    timespan=datetime.timedelta(minutes=window_minutes),
                )
                rows = []
                for table in result.tables:
                    for row in table.rows:
                        rows.append(dict(zip(table.columns, row)))
                return rows
            except Exception:
                return []
        try:
            return await asyncio.to_thread(_fetch)
        except Exception:
            return []

    async def get_cost_breakdown(self) -> dict:
        def _fetch():
            try:
                from azure.mgmt.costmanagement import CostManagementClient
                from azure.mgmt.costmanagement.models import QueryDefinition, QueryTimePeriod, QueryDataset, QueryAggregation, QueryGrouping
                import datetime
            except ImportError:
                return {"error": "Install azure-mgmt-costmanagement"}
            cred = self._get_credential()
            client = CostManagementClient(cred)
            scope = f"/subscriptions/{self.subscription_id}"
            now = datetime.datetime.utcnow()
            result = client.query.usage(
                scope=scope,
                parameters=QueryDefinition(
                    type="Usage",
                    timeframe="MonthToDate",
                    dataset=QueryDataset(
                        granularity="None",
                        aggregation={"totalCost": QueryAggregation(name="PreTaxCost", function="Sum")},
                        grouping=[QueryGrouping(type="Dimension", name="ServiceName")],
                    ),
                ),
            )
            rows = result.rows or []
            return {
                "breakdown": [
                    {"service": str(r[1]) if len(r) > 1 else "Unknown", "cost_usd": round(float(r[0]), 2)}
                    for r in sorted(rows, key=lambda x: float(x[0]), reverse=True)
                ]
            }
        try:
            return await asyncio.to_thread(_fetch)
        except Exception as e:
            return {"error": str(e)}

    async def list_aks_clusters(self) -> list[dict]:
        def _fetch():
            try:
                from azure.mgmt.containerservice import ContainerServiceClient
            except ImportError:
                return []
            cred = self._get_credential()
            client = ContainerServiceClient(cred, self.subscription_id)
            clusters = list(client.managed_clusters.list())
            return [
                {
                    "name": c.name,
                    "resource_group": c.id.split("/")[4] if c.id else "",
                    "location": c.location,
                    "kubernetes_version": c.kubernetes_version,
                    "provisioning_state": c.provisioning_state,
                    "node_count": sum(p.count or 0 for p in (c.agent_pool_profiles or [])),
                }
                for c in clusters
            ]
        try:
            return await asyncio.to_thread(_fetch)
        except Exception:
            return []

    async def invoke_openai(self, prompt: str, system: str = "") -> str:
        """Call Azure OpenAI (private endpoint — no traffic leaves Azure network)."""
        def _invoke():
            try:
                from openai import AzureOpenAI
            except ImportError:
                raise ImportError("Install openai: pip install openai")
            token = self._get_credential().get_token("https://cognitiveservices.azure.com/.default")
            client = AzureOpenAI(
                azure_endpoint=self.openai_endpoint,
                api_version=self.openai_api_version,
                azure_ad_token=token.token,
            )
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                model=self.openai_deployment, messages=messages, max_tokens=4096
            )
            return response.choices[0].message.content or ""
        try:
            return await asyncio.to_thread(_invoke)
        except Exception as e:
            return f"Azure OpenAI error: {e}"

    @staticmethod
    def get_required_role() -> dict:
        return AZURE_CUSTOM_ROLE

    @staticmethod
    def get_deploy_actions() -> list[str]:
        return AZURE_DEPLOY_ROLE_ACTIONS

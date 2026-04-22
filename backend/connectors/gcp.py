"""
GCP Connector — Service Account, Workload Identity, Vertex AI,
Cloud Billing, GKE, Cloud Monitoring, Cloud Logging.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from connectors.base import BaseConnector, ConnectorConfig


# ── Required GCP IAM roles ────────────────────────────────────────
GCP_REQUIRED_ROLES = [
    "roles/viewer",
    "roles/aiplatform.user",
    "roles/container.clusterViewer",
    "roles/monitoring.viewer",
    "roles/logging.viewer",
    "roles/bigquery.dataViewer",
    "roles/billing.viewer",
]

GCP_DEPLOY_ROLES = [
    "roles/container.developer",
    "roles/cloudfunctions.developer",
    "roles/run.developer",
    "roles/deploymentmanager.editor",
]

GCP_SA_SETUP_COMMANDS = """
# 1. Create service account
gcloud iam service-accounts create opsbrain \\
  --display-name="OpsBrain AIOps" \\
  --project={PROJECT_ID}

# 2. Grant required roles
for ROLE in roles/viewer roles/aiplatform.user roles/container.clusterViewer \\
            roles/monitoring.viewer roles/logging.viewer roles/billing.viewer; do
  gcloud projects add-iam-policy-binding {PROJECT_ID} \\
    --member="serviceAccount:opsbrain@{PROJECT_ID}.iam.gserviceaccount.com" \\
    --role="$ROLE"
done

# 3. Create and download key (for Service Account JSON auth)
gcloud iam service-accounts keys create opsbrain-key.json \\
  --iam-account=opsbrain@{PROJECT_ID}.iam.gserviceaccount.com

# 4. For Workload Identity (GKE — no key file needed)
gcloud iam service-accounts add-iam-policy-binding \\
  opsbrain@{PROJECT_ID}.iam.gserviceaccount.com \\
  --role roles/iam.workloadIdentityUser \\
  --member "serviceAccount:{PROJECT_ID}.svc.id.goog[opsbrain/opsbrain]"
"""


class GCPConnector(BaseConnector):
    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self.auth_method = cfg.get("auth_method", "service_account")
        self.project_id = cfg.get("project_id", "")
        self.region = cfg.get("region", "us-central1")
        self.service_account_json = cfg.get("service_account_json", "")
        self.workload_identity_provider = cfg.get("workload_identity_provider", "")
        self.service_account_email = cfg.get("service_account_email", "")
        self.vertex_ai_location = cfg.get("vertex_ai_location", "us-central1")
        self._credentials: Any = None

    def _get_credentials(self) -> Any:
        if self._credentials:
            return self._credentials
        try:
            import google.auth
            from google.oauth2 import service_account
        except ImportError:
            raise ImportError("Install google-auth: pip install google-auth google-cloud-resource-manager")

        if self.auth_method == "service_account" and self.service_account_json:
            info = json.loads(self.service_account_json) if isinstance(self.service_account_json, str) else self.service_account_json
            self._credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        elif self.auth_method == "workload_identity":
            from google.auth import identity_pool
            self._credentials, _ = identity_pool.Credentials.from_service_account_info(
                {
                    "type": "external_account",
                    "audience": self.workload_identity_provider,
                    "service_account_impersonation_url": f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{self.service_account_email}:generateAccessToken",
                    "token_url": "https://sts.googleapis.com/v1/token",
                    "credential_source": {"file": "/var/run/secrets/token"},
                }
            )
        else:
            self._credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )

        return self._credentials

    async def test_connection(self) -> dict:
        def _test():
            try:
                from google.cloud import resourcemanager_v3
            except ImportError:
                raise ImportError("Install: pip install google-cloud-resource-manager")
            creds = self._get_credentials()
            client = resourcemanager_v3.ProjectsClient(credentials=creds)
            project = client.get_project(name=f"projects/{self.project_id}")
            return {
                "healthy": True,
                "project_id": self.project_id,
                "project_name": project.display_name,
                "project_state": project.state.name,
                "auth_method": self.auth_method,
                "region": self.region,
            }
        try:
            return await asyncio.to_thread(_test)
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def fetch_alerts(self, severity: str = "all") -> list[dict]:
        def _fetch():
            try:
                from google.cloud import monitoring_v3
            except ImportError:
                return []
            creds = self._get_credentials()
            client = monitoring_v3.AlertPolicyServiceClient(credentials=creds)
            name = f"projects/{self.project_id}"
            policies = list(client.list_alert_policies(name=name))
            return [
                {
                    "name": p.display_name,
                    "severity": "critical",
                    "enabled": p.enabled.value if hasattr(p.enabled, "value") else p.enabled,
                    "conditions": len(p.conditions),
                    "source": "gcp_monitoring",
                }
                for p in policies[:20]
            ]
        try:
            return await asyncio.to_thread(_fetch)
        except Exception:
            return []

    async def fetch_logs(self, query: str, window_minutes: int = 15) -> list[dict]:
        def _fetch():
            try:
                from google.cloud import logging as gcloud_logging
            except ImportError:
                return []
            creds = self._get_credentials()
            client = gcloud_logging.Client(project=self.project_id, credentials=creds)
            from datetime import datetime, timedelta, timezone
            since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
            filter_str = f'textPayload:"{query}" AND timestamp>="{since}"'
            entries = list(client.list_entries(filter_=filter_str, max_results=50, order_by="timestamp desc"))
            return [
                {
                    "timestamp": str(e.timestamp),
                    "severity": str(e.severity),
                    "resource": str(e.resource.type if e.resource else ""),
                    "message": str(e.payload) if e.payload else "",
                    "source": "gcp_logging",
                }
                for e in entries
            ]
        try:
            return await asyncio.to_thread(_fetch)
        except Exception:
            return []

    async def get_cost_breakdown(self) -> dict:
        def _fetch():
            try:
                from google.cloud import billing_v1
            except ImportError:
                return {"error": "Install: pip install google-cloud-billing"}
            creds = self._get_credentials()
            client = billing_v1.CloudBillingClient(credentials=creds)
            name = f"projects/{self.project_id}"
            info = client.get_project_billing_info(name=name)
            return {
                "billing_account": info.billing_account_name,
                "billing_enabled": info.billing_enabled,
                "note": "Detailed cost breakdown requires BigQuery billing export — configure at: console.cloud.google.com/billing",
            }
        try:
            return await asyncio.to_thread(_fetch)
        except Exception as e:
            return {"error": str(e)}

    async def list_gke_clusters(self) -> list[dict]:
        def _fetch():
            try:
                from google.cloud import container_v1
            except ImportError:
                return []
            creds = self._get_credentials()
            client = container_v1.ClusterManagerClient(credentials=creds)
            parent = f"projects/{self.project_id}/locations/-"
            clusters = client.list_clusters(parent=parent).clusters
            return [
                {
                    "name": c.name,
                    "location": c.location,
                    "status": c.status.name,
                    "k8s_version": c.current_master_version,
                    "node_count": c.current_node_count,
                    "endpoint": c.endpoint,
                }
                for c in clusters
            ]
        try:
            return await asyncio.to_thread(_fetch)
        except Exception:
            return []

    async def invoke_vertex_ai(self, prompt: str, model: str = "gemini-1.5-pro") -> str:
        """Call Vertex AI (traffic stays inside GCP network)."""
        def _invoke():
            try:
                import vertexai
                from vertexai.generative_models import GenerativeModel
            except ImportError:
                raise ImportError("Install: pip install google-cloud-aiplatform")
            creds = self._get_credentials()
            vertexai.init(project=self.project_id, location=self.vertex_ai_location, credentials=creds)
            model_obj = GenerativeModel(model)
            response = model_obj.generate_content(prompt)
            return response.text
        try:
            return await asyncio.to_thread(_invoke)
        except Exception as e:
            return f"Vertex AI error: {e}"

    @staticmethod
    def get_required_roles() -> list[str]:
        return GCP_REQUIRED_ROLES

    @staticmethod
    def get_deploy_roles() -> list[str]:
        return GCP_DEPLOY_ROLES

    @staticmethod
    def get_sa_setup_commands(project_id: str = "{PROJECT_ID}") -> str:
        return GCP_SA_SETUP_COMMANDS.replace("{PROJECT_ID}", project_id)

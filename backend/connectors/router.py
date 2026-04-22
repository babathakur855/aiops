"""
Connector management API — list, add, remove, test, and query connectors.
"""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any

from auth.rbac import require_admin, require_any
from connectors.base import ConnectorConfig, ConnectorType
from connectors.registry import registry

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


class ConnectorCreateRequest(BaseModel):
    name: str
    type: ConnectorType
    config: dict[str, Any]
    enabled: bool = True
    connection_type: str = "data_source"  # "hosting" | "data_source"


class ConnectorQueryRequest(BaseModel):
    connector_id: str
    action: str
    params: dict[str, Any] = {}


@router.get("", dependencies=[Depends(require_any)])
async def list_connectors():
    return [
        {"id": c.id, "name": c.name, "type": c.type, "enabled": c.enabled}
        for c in registry.list_configs()
    ]


@router.get("/health", dependencies=[Depends(require_any)])
async def connectors_health():
    return await registry.health_check_all()


@router.post("", dependencies=[Depends(require_admin)], status_code=201)
async def add_connector(body: ConnectorCreateRequest):
    # Enforce one hosting connector per cloud type
    if body.connection_type == "hosting":
        existing_hosting = registry.get_hosting_cloud()
        if existing_hosting and existing_hosting.type == body.type:
            raise HTTPException(400, f"A hosting connector for {body.type} already exists. Remove it first.")

    connector_id = str(uuid.uuid4())[:8]
    config = ConnectorConfig(
        id=connector_id, name=body.name, type=body.type,
        config=body.config, enabled=body.enabled,
        connection_type=body.connection_type,
    )
    try:
        registry.register(config)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"id": connector_id, "name": body.name, "type": body.type, "connection_type": body.connection_type}


@router.delete("/{connector_id}", dependencies=[Depends(require_admin)])
async def remove_connector(connector_id: str):
    if not registry.remove(connector_id):
        raise HTTPException(404, "Connector not found")
    return {"status": "removed"}


@router.post("/{connector_id}/test", dependencies=[Depends(require_any)])
async def test_connector(connector_id: str):
    connector = registry.get(connector_id)
    if not connector:
        raise HTTPException(404, "Connector not found")
    return await connector.test_connection()


@router.post("/query", dependencies=[Depends(require_any)])
async def query_connector(body: ConnectorQueryRequest):
    """Generic connector query — call any connector action by name."""
    connector = registry.get(body.connector_id)
    if not connector:
        raise HTTPException(404, "Connector not found")

    action_map = {
        "fetch_incidents": connector.fetch_incidents,
        "fetch_alerts": connector.fetch_alerts,
        "fetch_logs": connector.fetch_logs,
        "fetch_documents": connector.fetch_documents,
        "send_notification": connector.send_notification,
    }
    fn = action_map.get(body.action)
    if not fn:
        raise HTTPException(400, f"Unknown action: {body.action}")

    try:
        result = await fn(**body.params)
        return {"result": result}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Typed endpoints for common connector actions ──────────────────

@router.get("/snow/incidents", dependencies=[Depends(require_any)])
async def snow_incidents(limit: int = 20):
    connectors = registry.get_by_type(ConnectorType.SERVICENOW)
    if not connectors:
        raise HTTPException(404, "No ServiceNow connector configured")
    return await connectors[0].fetch_incidents(limit=limit)


@router.post("/snow/incidents/{sys_id}/work-note", dependencies=[Depends(require_any)])
async def snow_add_work_note(sys_id: str, note: str):
    connectors = registry.get_by_type(ConnectorType.SERVICENOW)
    if not connectors:
        raise HTTPException(404, "No ServiceNow connector configured")
    from connectors.snow import ServiceNowConnector
    snow: ServiceNowConnector = connectors[0]  # type: ignore
    return await snow.add_work_note(sys_id, note)


@router.get("/confluence/search", dependencies=[Depends(require_any)])
async def confluence_search(query: str, limit: int = 5):
    connectors = registry.get_by_type(ConnectorType.CONFLUENCE)
    if not connectors:
        raise HTTPException(404, "No Confluence connector configured")
    return await connectors[0].fetch_documents(query=query, limit=limit)


@router.get("/dynatrace/alerts", dependencies=[Depends(require_any)])
async def dynatrace_alerts():
    connectors = registry.get_by_type(ConnectorType.DYNATRACE)
    if not connectors:
        raise HTTPException(404, "No Dynatrace connector configured")
    return await connectors[0].fetch_alerts()


@router.get("/logs/search", dependencies=[Depends(require_any)])
async def search_logs(query: str, window_minutes: int = 15):
    connectors = (
        registry.get_by_type(ConnectorType.ELASTICSEARCH)
        or registry.get_by_type(ConnectorType.SPLUNK)
        or registry.get_by_type(ConnectorType.LOKI)
    )
    if not connectors:
        raise HTTPException(404, "No log connector configured")
    return await connectors[0].fetch_logs(query=query, window_minutes=window_minutes)


# ── Cloud provider endpoints ──────────────────────────────────────

@router.get("/aws/iam-policy", dependencies=[Depends(require_admin)])
async def aws_iam_policy():
    """Return the required AWS IAM policy JSON for OpsBrain."""
    from connectors.aws import AWSConnector
    return {
        "read_policy": AWSConnector.get_required_iam_policy(),
        "deploy_policy": AWSConnector.get_deploy_iam_policy(),
        "trust_policy_template": AWSConnector.get_trust_policy_template(),
    }


@router.get("/aws/cost", dependencies=[Depends(require_any)])
async def aws_cost():
    connectors = registry.get_by_type(ConnectorType.AWS)
    if not connectors:
        raise HTTPException(404, "No AWS connector configured")
    from connectors.aws import AWSConnector
    return await connectors[0].get_cost_breakdown()  # type: ignore


@router.get("/aws/eks-clusters", dependencies=[Depends(require_any)])
async def aws_eks_clusters():
    connectors = registry.get_by_type(ConnectorType.AWS)
    if not connectors:
        raise HTTPException(404, "No AWS connector configured")
    from connectors.aws import AWSConnector
    return await connectors[0].list_eks_clusters()  # type: ignore


@router.get("/azure/required-role", dependencies=[Depends(require_admin)])
async def azure_required_role():
    """Return the required Azure custom role definition for OpsBrain."""
    from connectors.azure import AzureConnector
    return {
        "custom_role": AzureConnector.get_required_role(),
        "deploy_actions": AzureConnector.get_deploy_actions(),
    }


@router.get("/azure/cost", dependencies=[Depends(require_any)])
async def azure_cost():
    connectors = registry.get_by_type(ConnectorType.AZURE)
    if not connectors:
        raise HTTPException(404, "No Azure connector configured")
    from connectors.azure import AzureConnector
    return await connectors[0].get_cost_breakdown()  # type: ignore


@router.get("/azure/aks-clusters", dependencies=[Depends(require_any)])
async def azure_aks_clusters():
    connectors = registry.get_by_type(ConnectorType.AZURE)
    if not connectors:
        raise HTTPException(404, "No Azure connector configured")
    from connectors.azure import AzureConnector
    return await connectors[0].list_aks_clusters()  # type: ignore


@router.get("/gcp/required-roles", dependencies=[Depends(require_admin)])
async def gcp_required_roles():
    """Return required GCP IAM roles and service account setup commands."""
    from connectors.gcp import GCPConnector
    connectors = registry.get_by_type(ConnectorType.GCP)
    project_id = connectors[0].config.config.get("project_id", "{PROJECT_ID}") if connectors else "{PROJECT_ID}"
    return {
        "required_roles": GCPConnector.get_required_roles(),
        "deploy_roles": GCPConnector.get_deploy_roles(),
        "setup_commands": GCPConnector.get_sa_setup_commands(project_id),
    }


@router.get("/gcp/gke-clusters", dependencies=[Depends(require_any)])
async def gcp_gke_clusters():
    connectors = registry.get_by_type(ConnectorType.GCP)
    if not connectors:
        raise HTTPException(404, "No GCP connector configured")
    from connectors.gcp import GCPConnector
    return await connectors[0].list_gke_clusters()  # type: ignore


# ── Cloud architecture summary ────────────────────────────────────

@router.get("/cloud/summary", dependencies=[Depends(require_any)])
async def cloud_summary():
    """
    Returns the full cloud architecture:
    - hosting: where OpsBrain itself is deployed (one cloud, workload identity)
    - data_sources: all monitored cloud accounts/subscriptions (any cloud, any number)
    This separation means OpsBrain deployed on AWS can still monitor Azure + GCP.
    """
    hosting = registry.get_hosting_cloud()
    data_sources = registry.get_data_sources()

    return {
        "hosting": {
            "configured": hosting is not None,
            "cloud": hosting.type if hosting else None,
            "name": hosting.name if hosting else None,
            "id": hosting.id if hosting else None,
            "region": hosting.config.get("region", "") if hosting else None,
            "auth_method": hosting.config.get("auth_method", "") if hosting else None,
        },
        "data_sources": [
            {
                "id": ds.id,
                "name": ds.name,
                "cloud": ds.type,
                "auth_method": ds.config.get("auth_method", ""),
                "account_id": ds.config.get("account_id") or ds.config.get("subscription_id") or ds.config.get("project_id") or "",
                "region": ds.config.get("region", ""),
                "enabled": ds.enabled,
            }
            for ds in data_sources
        ],
        "note": "OpsBrain monitors all data_sources regardless of which cloud it is hosted on.",
    }

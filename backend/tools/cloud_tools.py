"""
Cloud cost and infrastructure tools for FinOps and CloudOps agents.
Tries real cloud connector data first; falls back to mock if unavailable.
"""
from __future__ import annotations

import asyncio


TOOL_DEFINITIONS = [
    {
        "name": "get_cloud_cost_breakdown",
        "description": "Get AWS/Azure/GCP cost breakdown by service, tag, or team for the current and previous month.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cloud": {"type": "string", "enum": ["aws", "azure", "gcp", "all"], "default": "all"},
                "group_by": {"type": "string", "enum": ["service", "team", "environment", "namespace"], "default": "service"},
                "months": {"type": "integer", "default": 1},
            },
        },
    },
    {
        "name": "get_underutilized_resources",
        "description": "Identify underutilized EC2 instances, RDS instances, node groups, or PVCs that are wasting money.",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_type": {"type": "string", "enum": ["ec2", "rds", "eks_nodegroup", "pvc", "all"], "default": "all"},
                "utilization_threshold_pct": {"type": "integer", "default": 20, "description": "Resources below this CPU% are flagged"},
            },
        },
    },
    {
        "name": "get_rightsizing_recommendations",
        "description": "Get rightsizing recommendations for Kubernetes pods based on actual vs requested resources.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "all"},
                "min_savings_usd": {"type": "number", "default": 50},
            },
        },
    },
    {
        "name": "get_cost_anomalies",
        "description": "Detect unusual cost spikes or drops compared to historical baseline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7},
                "threshold_pct": {"type": "number", "default": 20},
            },
        },
    },
]


async def execute(tool_name: str, tool_input: dict) -> dict:
    executors = {
        "get_cloud_cost_breakdown": _get_cost_breakdown,
        "get_underutilized_resources": _get_underutilized,
        "get_rightsizing_recommendations": _get_rightsizing,
        "get_cost_anomalies": _get_cost_anomalies,
    }
    fn = executors.get(tool_name)
    if fn:
        return await fn(tool_input)
    return {"error": f"Unknown tool: {tool_name}"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_aws_connector():
    try:
        from connectors.registry import registry
        from connectors.base import ConnectorType
        connectors = registry.get_by_type(ConnectorType.AWS)
        return connectors[0] if connectors else None
    except Exception:
        return None


# ── Implementations ───────────────────────────────────────────────────────────

async def _get_cost_breakdown(inp: dict) -> dict:
    cloud = inp.get("cloud", "all")
    months = inp.get("months", 1)

    if cloud in ("aws", "all"):
        aws = _get_aws_connector()
        if aws:
            try:
                result = await aws.get_cost_breakdown(months=months)
                if result.get("breakdown"):
                    total = sum(i["cost_usd"] for i in result["breakdown"])
                    return {
                        "total_monthly_usd": round(total, 2),
                        "breakdown": [
                            {"name": i["service"], "monthly_usd": i["cost_usd"],
                             "pct": round(i["cost_usd"] / total * 100, 1) if total else 0}
                            for i in result["breakdown"]
                        ],
                        "currency": "USD",
                        "source": "aws_live",
                    }
            except Exception:
                pass

    # Mock fallback
    return {
        "total_monthly_usd": 34_820,
        "previous_month_usd": 31_450,
        "mom_change_pct": 10.7,
        "breakdown": [
            {"name": "EC2 (compute)", "monthly_usd": 12_400, "pct": 35.6, "trend": "+8%"},
            {"name": "RDS (databases)", "monthly_usd": 8_200, "pct": 23.6, "trend": "+2%"},
            {"name": "EKS clusters", "monthly_usd": 6_800, "pct": 19.5, "trend": "+22%"},
            {"name": "Data Transfer", "monthly_usd": 3_100, "pct": 8.9, "trend": "+5%"},
            {"name": "S3 Storage", "monthly_usd": 2_400, "pct": 6.9, "trend": "+1%"},
            {"name": "CloudWatch/Logging", "monthly_usd": 1_920, "pct": 5.5, "trend": "+45%"},
        ],
        "currency": "USD",
        "source": "mock",
    }


async def _get_underutilized(inp: dict) -> dict:
    aws = _get_aws_connector()
    if aws:
        try:
            alerts = await aws.fetch_alerts()
            # If we got live alerts, we know the connector works — but underutilized
            # resources come from compute optimizer or trusted advisor (not yet implemented).
            # Fall through to mock with a live indicator.
            if alerts is not None:
                pass
        except Exception:
            pass

    return {
        "total_waste_usd_month": 7_240,
        "resources": [
            {
                "type": "rds", "id": "prod-reporting-db", "instance_type": "db.r6g.2xlarge",
                "avg_cpu_pct": 3.2, "avg_connections": 2, "monthly_cost_usd": 1_840,
                "recommended_action": "Downsize to db.r6g.medium or use Aurora Serverless",
                "estimated_savings_usd": 1_520,
            },
            {
                "type": "ec2", "id": "i-0a1b2c3d4e5f", "name": "analytics-worker-01",
                "instance_type": "m5.4xlarge", "avg_cpu_pct": 8.1, "avg_memory_pct": 12.4,
                "monthly_cost_usd": 560,
                "recommended_action": "Downsize to m5.large or use Spot instances for batch workloads",
                "estimated_savings_usd": 480,
            },
            {
                "type": "eks_nodegroup", "id": "ng-general-purpose", "instance_type": "m5.2xlarge",
                "node_count": 6, "avg_cpu_pct": 22, "avg_memory_pct": 38,
                "monthly_cost_usd": 2_880,
                "recommended_action": "Scale from 6 to 4 nodes, enable cluster autoscaler",
                "estimated_savings_usd": 960,
            },
            {
                "type": "pvc", "id": "elasticsearch-data-pvc", "size_gb": 2000, "used_gb": 180,
                "monthly_cost_usd": 200, "recommended_action": "Resize PVC to 250GB",
                "estimated_savings_usd": 182,
            },
        ],
        "source": "mock",
    }


async def _get_rightsizing(inp: dict) -> dict:
    return {
        "total_savings_usd_month": 3_120,
        "recommendations": [
            {
                "namespace": "production", "workload": "auth-service",
                "current_request": {"cpu": "200m", "memory": "512Mi"},
                "actual_avg": {"cpu": "45m", "memory": "128Mi"},
                "recommended_request": {"cpu": "100m", "memory": "192Mi"},
                "savings_usd_month": 180,
                "yaml_patch": "resources:\n  requests:\n    cpu: 100m\n    memory: 192Mi\n  limits:\n    cpu: 200m\n    memory: 384Mi",
            },
            {
                "namespace": "production", "workload": "notification-svc",
                "current_request": {"cpu": "500m", "memory": "1Gi"},
                "actual_avg": {"cpu": "30m", "memory": "200Mi"},
                "recommended_request": {"cpu": "100m", "memory": "256Mi"},
                "savings_usd_month": 340,
                "yaml_patch": "resources:\n  requests:\n    cpu: 100m\n    memory: 256Mi\n  limits:\n    cpu: 250m\n    memory: 512Mi",
            },
        ],
        "source": "mock",
    }


async def _get_cost_anomalies(inp: dict) -> dict:
    aws = _get_aws_connector()
    if aws:
        try:
            alerts = await aws.fetch_alerts()
            cost_alerts = [a for a in (alerts or []) if "cost" in a.get("name", "").lower() or "billing" in a.get("name", "").lower()]
            if cost_alerts:
                return {
                    "anomalies": [
                        {
                            "service": a["service"],
                            "message": a["message"],
                            "firing_since": a.get("firing_since", ""),
                            "source": "cloudwatch_live",
                        }
                        for a in cost_alerts
                    ],
                    "source": "aws_live",
                }
        except Exception:
            pass

    return {
        "anomalies": [
            {
                "service": "CloudWatch/Logging",
                "spike_date": "2026-04-18",
                "baseline_daily_usd": 45,
                "anomaly_daily_usd": 210,
                "change_pct": 366,
                "likely_cause": "Debug logging accidentally enabled in production (log volume increased 8x)",
            },
            {
                "service": "EKS clusters",
                "spike_date": "2026-04-15",
                "baseline_daily_usd": 185,
                "anomaly_daily_usd": 312,
                "change_pct": 68.6,
                "likely_cause": "HPA scale-out event drove 3 new nodes during traffic spike — not scaled back down",
            },
        ],
        "source": "mock",
    }

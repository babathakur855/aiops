"""
Cloud API Poller — agentless metric collection from AWS, Azure, GCP cloud APIs.
Runs on a schedule (default every 5 minutes) inside the OpsBrain backend.
Covers IaaS, PaaS, and SaaS health for all connected accounts.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from collector.metrics_store import metrics_store
from connectors.base import ConnectorType
from connectors.registry import registry

log = logging.getLogger(__name__)


# ── IaaS ─────────────────────────────────────────────────────────
# Compute, storage, network, container nodes

AWS_IAAS_METRICS = [
    # EC2
    ("AWS/EC2", "CPUUtilization", "Percent"),
    ("AWS/EC2", "NetworkIn", "Bytes"),
    ("AWS/EC2", "NetworkOut", "Bytes"),
    # EBS
    ("AWS/EBS", "VolumeReadOps", "Count"),
    ("AWS/EBS", "VolumeWriteOps", "Count"),
    ("AWS/EBS", "VolumeThroughputPercentage", "Percent"),
    # ELB/ALB
    ("AWS/ApplicationELB", "RequestCount", "Count"),
    ("AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "Count"),
    ("AWS/ApplicationELB", "TargetResponseTime", "Seconds"),
    # EKS nodes (via CloudWatch Container Insights)
    ("ContainerInsights", "node_cpu_utilization", "Percent"),
    ("ContainerInsights", "node_memory_utilization", "Percent"),
    ("ContainerInsights", "node_filesystem_utilization", "Percent"),
    ("ContainerInsights", "pod_cpu_utilization", "Percent"),
    ("ContainerInsights", "pod_memory_utilization", "Percent"),
]

AWS_PAAS_METRICS = [
    # RDS
    ("AWS/RDS", "CPUUtilization", "Percent"),
    ("AWS/RDS", "DatabaseConnections", "Count"),
    ("AWS/RDS", "ReadLatency", "Seconds"),
    ("AWS/RDS", "WriteLatency", "Seconds"),
    ("AWS/RDS", "FreeStorageSpace", "Bytes"),
    ("AWS/RDS", "ReplicaLag", "Seconds"),
    # ElastiCache
    ("AWS/ElastiCache", "CacheHits", "Count"),
    ("AWS/ElastiCache", "CacheMisses", "Count"),
    ("AWS/ElastiCache", "CurrConnections", "Count"),
    ("AWS/ElastiCache", "EngineCPUUtilization", "Percent"),
    # Lambda
    ("AWS/Lambda", "Invocations", "Count"),
    ("AWS/Lambda", "Errors", "Count"),
    ("AWS/Lambda", "Duration", "Milliseconds"),
    ("AWS/Lambda", "Throttles", "Count"),
    # SQS
    ("AWS/SQS", "NumberOfMessagesSent", "Count"),
    ("AWS/SQS", "NumberOfMessagesReceived", "Count"),
    ("AWS/SQS", "ApproximateAgeOfOldestMessage", "Seconds"),
    ("AWS/SQS", "ApproximateNumberOfMessagesNotVisible", "Count"),
    # API Gateway
    ("AWS/ApiGateway", "Count", "Count"),
    ("AWS/ApiGateway", "5XXError", "Count"),
    ("AWS/ApiGateway", "Latency", "Milliseconds"),
]

AZURE_METRICS = {
    "iaas": [
        # VMs
        ("Microsoft.Compute/virtualMachines", "Percentage CPU", "iaas"),
        ("Microsoft.Compute/virtualMachines", "Network In Total", "iaas"),
        ("Microsoft.Compute/virtualMachines", "Network Out Total", "iaas"),
        ("Microsoft.Compute/virtualMachines", "OS Disk Read Bytes/sec", "iaas"),
        # AKS nodes
        ("Microsoft.ContainerService/managedClusters", "node_cpu_usage_percentage", "iaas"),
        ("Microsoft.ContainerService/managedClusters", "node_memory_working_set_percentage", "iaas"),
        ("Microsoft.ContainerService/managedClusters", "pod_count", "iaas"),
    ],
    "paas": [
        # Azure SQL
        ("Microsoft.Sql/servers/databases", "cpu_percent", "paas"),
        ("Microsoft.Sql/servers/databases", "dtu_consumption_percent", "paas"),
        ("Microsoft.Sql/servers/databases", "connection_successful", "paas"),
        ("Microsoft.Sql/servers/databases", "storage_percent", "paas"),
        # App Service
        ("Microsoft.Web/sites", "Requests", "paas"),
        ("Microsoft.Web/sites", "Http5xx", "paas"),
        ("Microsoft.Web/sites", "AverageResponseTime", "paas"),
        ("Microsoft.Web/sites", "MemoryWorkingSet", "paas"),
        # Service Bus
        ("Microsoft.ServiceBus/namespaces", "IncomingMessages", "paas"),
        ("Microsoft.ServiceBus/namespaces", "OutgoingMessages", "paas"),
        ("Microsoft.ServiceBus/namespaces", "DeadletteredMessages", "paas"),
        # Azure Functions
        ("Microsoft.Web/sites", "FunctionExecutionCount", "paas"),
        ("Microsoft.Web/sites", "FunctionExecutionUnits", "paas"),
    ],
}

GCP_METRICS = {
    "iaas": [
        "compute.googleapis.com/instance/cpu/utilization",
        "compute.googleapis.com/instance/network/received_bytes_count",
        "compute.googleapis.com/instance/network/sent_bytes_count",
        "compute.googleapis.com/instance/disk/read_bytes_count",
        "kubernetes.io/node/cpu/allocatable_utilization",
        "kubernetes.io/node/memory/allocatable_utilization",
        "kubernetes.io/pod/volume/used_bytes",
    ],
    "paas": [
        "cloudsql.googleapis.com/database/cpu/utilization",
        "cloudsql.googleapis.com/database/memory/utilization",
        "cloudsql.googleapis.com/database/network/connections",
        "run.googleapis.com/request_count",
        "run.googleapis.com/request_latencies",
        "cloudfunctions.googleapis.com/function/execution_count",
        "cloudfunctions.googleapis.com/function/execution_times",
        "pubsub.googleapis.com/subscription/num_undelivered_messages",
        "pubsub.googleapis.com/subscription/oldest_unacked_message_age",
    ],
}


async def collect_all() -> dict[str, Any]:
    """
    Main scheduled collection entry point.
    Collects from all configured cloud data-source connectors.
    Returns a summary of what was collected.
    """
    summary: dict[str, Any] = {"started_at": datetime.now(timezone.utc).isoformat(), "results": []}
    data_sources = registry.get_data_sources()

    if not data_sources:
        log.debug("No cloud data sources configured — skipping collection")
        return summary

    tasks = []
    for cfg in data_sources:
        connector = registry.get(cfg.id)
        if not connector or not cfg.enabled:
            continue
        if cfg.type == ConnectorType.AWS:
            tasks.append(_collect_aws(cfg.id, cfg.name, connector))
        elif cfg.type == ConnectorType.AZURE:
            tasks.append(_collect_azure(cfg.id, cfg.name, connector))
        elif cfg.type == ConnectorType.GCP:
            tasks.append(_collect_gcp(cfg.id, cfg.name, connector))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            log.warning("Collection error: %s", result)
        elif isinstance(result, dict):
            summary["results"].append(result)

    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    summary["total_sources"] = len(tasks)
    return summary


_DIMENSION_PRIORITY = (
    "InstanceId", "DBInstanceIdentifier", "FunctionName", "QueueName",
    "LoadBalancer", "ClusterName", "CacheClusterId", "ApiName",
)

_MAX_RESOURCES_PER_METRIC = 20  # avoid runaway API calls on large accounts


async def _collect_aws(env_id: str, env_name: str, connector: Any) -> dict:
    """Collect IaaS + PaaS metrics from AWS CloudWatch.

    Uses list_metrics to discover per-resource dimensions first, then queries
    each resource individually. Without dimensions CloudWatch returns no
    datapoints for instance-scoped metrics (EC2, RDS, Lambda, etc.).
    """
    collected = 0
    errors = []

    def _fetch_cw_metrics():
        session = connector._session_or_new()
        cw = session.client("cloudwatch")
        now = datetime.utcnow()
        start = now - timedelta(minutes=10)
        metrics = []

        for namespace, metric_name, unit in AWS_IAAS_METRICS + AWS_PAAS_METRICS:
            try:
                # Discover all instances of this metric with their dimensions
                paginator = cw.get_paginator("list_metrics")
                discovered = []
                for page in paginator.paginate(Namespace=namespace, MetricName=metric_name):
                    discovered.extend(page.get("Metrics", []))
                    if len(discovered) >= _MAX_RESOURCES_PER_METRIC:
                        break
                discovered = discovered[:_MAX_RESOURCES_PER_METRIC]

                # If no dimensions found the metric doesn't exist in this account
                if not discovered:
                    continue

                service_label = (
                    namespace.replace("AWS/", "")
                    .replace("ContainerInsights", "k8s")
                    .lower()
                )

                for metric_def in discovered:
                    dimensions = metric_def.get("Dimensions", [])
                    resource_id = next(
                        (d["Value"] for d in dimensions if d["Name"] in _DIMENSION_PRIORITY),
                        "aggregate",
                    )
                    resp = cw.get_metric_statistics(
                        Namespace=namespace,
                        MetricName=metric_name,
                        Dimensions=dimensions,
                        StartTime=start,
                        EndTime=now,
                        Period=300,
                        Statistics=["Average"],
                    )
                    for dp in resp.get("Datapoints", []):
                        metrics.append({
                            "service": service_label,
                            "metric": metric_name.lower().replace(" ", "_"),
                            "value": dp["Average"],
                            "timestamp": dp["Timestamp"].isoformat(),
                            "labels": {"unit": unit, "namespace": namespace, "resource": resource_id},
                        })
            except Exception as e:
                errors.append(f"{namespace}/{metric_name}: {e}")

        return metrics

    try:
        raw_metrics = await asyncio.to_thread(_fetch_cw_metrics)
        collected = metrics_store.store_batch(env_id, raw_metrics)
        metrics_store.log_collection(env_id, "aws_cloudwatch", collected)
        log.info("AWS [%s]: collected %d metrics", env_name, collected)
    except Exception as e:
        error_msg = str(e)
        metrics_store.log_collection(env_id, "aws_cloudwatch", 0, error=error_msg)
        log.warning("AWS collection failed [%s]: %s", env_name, error_msg)

    return {"env": env_name, "cloud": "aws", "collected": collected, "errors": errors[:5]}


async def _collect_azure(env_id: str, env_name: str, connector: Any) -> dict:
    """Collect IaaS + PaaS metrics from Azure Monitor."""
    collected = 0
    errors = []

    def _fetch_azure_metrics():
        try:
            from azure.mgmt.monitor import MonitorManagementClient
            from azure.mgmt.resource import ResourceManagementClient
        except ImportError:
            return []

        cred = connector._get_credential()
        sub_id = connector.config.config.get("subscription_id", "")
        if not sub_id:
            return []

        resource_client = ResourceManagementClient(cred, sub_id)
        monitor_client = MonitorManagementClient(cred, sub_id)

        metrics = []
        now = datetime.utcnow()
        start = now - timedelta(minutes=10)

        for resource_type, metric_name, layer in AZURE_METRICS["iaas"] + AZURE_METRICS["paas"]:
            try:
                resources = list(resource_client.resources.list(
                    filter=f"resourceType eq '{resource_type}'",
                    top=20,
                ))
                for resource in resources[:5]:
                    resp = monitor_client.metrics.list(
                        resource.id,
                        timespan=f"{start.isoformat()}Z/{now.isoformat()}Z",
                        interval="PT5M",
                        metricnames=metric_name,
                        aggregation="Average",
                    )
                    for metric in resp.value:
                        for ts_data in metric.timeseries:
                            for dp in ts_data.data:
                                if dp.average is not None:
                                    metrics.append({
                                        "service": resource_type.split("/")[-1].lower(),
                                        "metric": metric_name.lower().replace(" ", "_"),
                                        "value": dp.average,
                                        "timestamp": dp.time_stamp.isoformat() if dp.time_stamp else now.isoformat(),
                                        "labels": {"resource": resource.name, "layer": layer},
                                    })
            except Exception as e:
                errors.append(f"{resource_type}/{metric_name}: {e}")

        return metrics

    try:
        raw_metrics = await asyncio.to_thread(_fetch_azure_metrics)
        collected = metrics_store.store_batch(env_id, raw_metrics)
        metrics_store.log_collection(env_id, "azure_monitor", collected)
        log.info("Azure [%s]: collected %d metrics", env_name, collected)
    except Exception as e:
        error_msg = str(e)
        metrics_store.log_collection(env_id, "azure_monitor", 0, error=error_msg)
        log.warning("Azure collection failed [%s]: %s", env_name, error_msg)

    return {"env": env_name, "cloud": "azure", "collected": collected, "errors": errors[:5]}


async def _collect_gcp(env_id: str, env_name: str, connector: Any) -> dict:
    """Collect IaaS + PaaS metrics from GCP Cloud Monitoring."""
    collected = 0
    errors = []

    def _fetch_gcp_metrics():
        try:
            from google.cloud import monitoring_v3
            import google.protobuf.duration_pb2 as duration_pb2
        except ImportError:
            return []

        creds = connector._get_credentials()
        project = connector.project_id
        client = monitoring_v3.MetricServiceClient(credentials=creds)
        project_name = f"projects/{project}"
        now = datetime.utcnow()
        interval = monitoring_v3.TimeInterval(
            end_time={"seconds": int(now.timestamp())},
            start_time={"seconds": int((now - timedelta(minutes=10)).timestamp())},
        )

        metrics = []
        all_metric_types = GCP_METRICS["iaas"] + GCP_METRICS["paas"]

        for metric_type in all_metric_types:
            try:
                results = client.list_time_series(
                    name=project_name,
                    filter=f'metric.type = "{metric_type}"',
                    interval=interval,
                    view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                )
                service = metric_type.split("/")[0].replace(".googleapis.com", "")
                metric_name = metric_type.split("/")[-1]

                for ts in results:
                    for point in ts.points:
                        val = (point.value.double_value or point.value.int64_value or
                               point.value.distribution_value.mean or 0)
                        metrics.append({
                            "service": service,
                            "metric": metric_name,
                            "value": float(val),
                            "timestamp": point.interval.end_time.isoformat(),
                            "labels": {k: v for k, v in ts.metric.labels.items()},
                        })
            except Exception as e:
                errors.append(f"{metric_type}: {e}")

        return metrics

    try:
        raw_metrics = await asyncio.to_thread(_fetch_gcp_metrics)
        collected = metrics_store.store_batch(env_id, raw_metrics)
        metrics_store.log_collection(env_id, "gcp_monitoring", collected)
        log.info("GCP [%s]: collected %d metrics", env_name, collected)
    except Exception as e:
        error_msg = str(e)
        metrics_store.log_collection(env_id, "gcp_monitoring", 0, error=error_msg)
        log.warning("GCP collection failed [%s]: %s", env_name, error_msg)

    return {"env": env_name, "cloud": "gcp", "collected": collected, "errors": errors[:5]}


async def collect_saas_health(health_endpoints: list[dict]) -> list[dict]:
    """
    Check SaaS / HTTP endpoint health.
    health_endpoints: [{"name": "My API", "url": "https://...", "expected_status": 200}]
    """
    import httpx
    results = []
    async with httpx.AsyncClient(timeout=10) as client:
        for ep in health_endpoints:
            try:
                start = datetime.now(timezone.utc)
                resp = await client.get(ep["url"])
                latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                healthy = resp.status_code == ep.get("expected_status", 200)
                results.append({
                    "name": ep["name"], "url": ep["url"],
                    "status_code": resp.status_code, "latency_ms": round(latency_ms, 1),
                    "healthy": healthy,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                })
                env_id = ep.get("env_id", "saas")
                metrics_store.store(env_id, ep["name"], "latency_ms", latency_ms)
                metrics_store.store(env_id, ep["name"], "status_code", resp.status_code)
                metrics_store.store(env_id, ep["name"], "healthy", 1.0 if healthy else 0.0)
            except Exception as e:
                results.append({"name": ep["name"], "url": ep["url"], "healthy": False, "error": str(e)})
    return results

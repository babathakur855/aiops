"""
OTLP/HTTP receiver — accepts metrics pushed by the OpsBrain Collector agent
deployed as a DaemonSet inside customer Kubernetes clusters.

Implements a subset of the OpenTelemetry Protocol (OTLP) HTTP/JSON spec.
The OTel Collector in each cluster sends to: POST /v1/metrics
"""
from __future__ import annotations

import logging
from datetime import timezone, datetime
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from collector.metrics_store import metrics_store

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["otlp"])


@router.post("/metrics")
async def receive_otlp_metrics(request: Request) -> JSONResponse:
    """
    Accepts OTLP/JSON metrics payload from remote OTel Collector agents.
    Auth: X-OpsBrain-Token header (enrollment token issued at environment creation)
    """
    token = request.headers.get("X-OpsBrain-Token", "")
    env_id = request.headers.get("X-OpsBrain-Env-ID", "")

    # Validate enrollment token
    if token:
        try:
            from collector.enrollment import validate_enrollment_token, enrollment_registry
            payload = validate_enrollment_token(token)
            env_id = payload["env_id"]
            # Check revocation
            if enrollment_registry.is_revoked(payload.get("jti", "")):
                return JSONResponse({"error": "Token revoked"}, status_code=401)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=401)
    elif not env_id:
        return JSONResponse({"error": "Missing X-OpsBrain-Token header"}, status_code=401)

    content_type = request.headers.get("content-type", "")

    try:
        if "protobuf" in content_type:
            raise HTTPException(415, "Use OTLP/JSON (set Content-Type: application/json in OTel Collector)")
        body = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid payload: {e}")

    count = _process_otlp_metrics(env_id, body)
    metrics_store.log_collection(env_id, "otlp_agent", count)
    log.debug("OTLP received %d metrics from env=%s", count, env_id)
    return JSONResponse({"accepted": count}, status_code=200)


@router.post("/logs")
async def receive_otlp_logs(request: Request) -> JSONResponse:
    """Accept OTLP log records from remote collectors (stored for AI analysis)."""
    env_id = request.headers.get("X-OpsBrain-Env-ID", "unknown")
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(400, str(e))

    count = _process_otlp_logs(env_id, body)
    return JSONResponse({"accepted": count})


@router.post("/traces")
async def receive_otlp_traces(request: Request) -> JSONResponse:
    env_id = request.headers.get("X-OpsBrain-Env-ID", "unknown")
    return JSONResponse({"accepted": 0, "note": "Trace storage not yet implemented"})


def _process_otlp_metrics(env_id: str, body: dict[str, Any]) -> int:
    """
    Parse OTLP/JSON ExportMetricsServiceRequest.
    https://opentelemetry.io/docs/specs/otlp/#otlphttp
    """
    count = 0
    resource_metrics = body.get("resourceMetrics", [])

    for rm in resource_metrics:
        # Extract resource labels (pod name, node, namespace, etc.)
        resource_labels: dict[str, str] = {}
        for attr in rm.get("resource", {}).get("attributes", []):
            resource_labels[attr.get("key", "")] = _extract_attr_value(attr.get("value", {}))

        service = resource_labels.get("k8s.deployment.name") or resource_labels.get("service.name") or "unknown"
        namespace = resource_labels.get("k8s.namespace.name", "")

        for scope_metrics in rm.get("scopeMetrics", []):
            for metric in scope_metrics.get("metrics", []):
                metric_name = metric.get("name", "")
                points = (
                    metric.get("gauge", {}).get("dataPoints", [])
                    or metric.get("sum", {}).get("dataPoints", [])
                    or metric.get("histogram", {}).get("dataPoints", [])
                )
                for dp in points:
                    value = (
                        dp.get("asDouble")
                        or dp.get("asInt")
                        or dp.get("sum")
                        or 0
                    )
                    ts_nanos = dp.get("timeUnixNano", 0)
                    ts = (
                        datetime.fromtimestamp(int(ts_nanos) / 1e9, tz=timezone.utc).isoformat()
                        if ts_nanos else None
                    )
                    labels = {**resource_labels}
                    for attr in dp.get("attributes", []):
                        labels[attr.get("key", "")] = _extract_attr_value(attr.get("value", {}))

                    metrics_store.store(
                        env_id=env_id,
                        service=service,
                        metric=metric_name,
                        value=float(value),
                        labels=labels,
                        timestamp=ts,
                    )
                    count += 1

    return count


def _process_otlp_logs(env_id: str, body: dict[str, Any]) -> int:
    count = 0
    for rl in body.get("resourceLogs", []):
        for scope_logs in rl.get("scopeLogs", []):
            count += len(scope_logs.get("logRecords", []))
    return count


def _extract_attr_value(value: dict[str, Any]) -> str:
    return str(
        value.get("stringValue")
        or value.get("intValue")
        or value.get("doubleValue")
        or value.get("boolValue")
        or ""
    )

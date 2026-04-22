"""
Kubernetes tool definitions for Claude tool use.
Uses the real kubernetes Python client when a cluster is reachable;
falls back gracefully to realistic mock data so the app works without k8s.
"""
from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

# ── Try to initialise the k8s client ─────────────────────────────────────────

_k8s_available = False
_core_v1: Any = None
_apps_v1: Any = None
_autoscaling_v1: Any = None
_custom_objects: Any = None


def _init_k8s() -> None:
    global _k8s_available, _core_v1, _apps_v1, _autoscaling_v1, _custom_objects
    try:
        from kubernetes import client, config  # type: ignore

        kubeconfig_path = os.getenv("KUBECONFIG", "")
        if os.getenv("KUBERNETES_SERVICE_HOST"):
            config.load_incluster_config()
        elif kubeconfig_path:
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            config.load_kube_config()

        _core_v1 = client.CoreV1Api()
        _apps_v1 = client.AppsV1Api()
        _autoscaling_v1 = client.AutoscalingV1Api()
        _custom_objects = client.CustomObjectsApi()
        _k8s_available = True
    except Exception:
        _k8s_available = False


_init_k8s()


# ── Tool schemas (unchanged — only executors differ) ──────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_pod_status",
        "description": "Get the status of pods in a namespace. Returns running, pending, failed, crashloopbackoff pods with resource usage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Kubernetes namespace"},
                "label_selector": {"type": "string", "description": "Optional label selector, e.g. app=payment-service"},
            },
            "required": ["namespace"],
        },
    },
    {
        "name": "get_pod_logs",
        "description": "Fetch recent logs from a pod, with optional filtering for errors and warnings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string"},
                "pod_name": {"type": "string"},
                "lines": {"type": "integer", "description": "Number of recent lines to fetch", "default": 100},
                "filter_errors": {"type": "boolean", "description": "Only return error/warning lines"},
            },
            "required": ["namespace", "pod_name"],
        },
    },
    {
        "name": "get_recent_deployments",
        "description": "Get deployment events from the last N hours to correlate with incidents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string"},
                "hours": {"type": "integer", "default": 6},
            },
            "required": ["namespace"],
        },
    },
    {
        "name": "get_resource_usage",
        "description": "Get CPU and memory usage for pods or nodes. Useful for identifying resource pressure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string"},
                "resource_type": {"type": "string", "enum": ["pods", "nodes"]},
            },
            "required": ["namespace", "resource_type"],
        },
    },
    {
        "name": "describe_service",
        "description": "Describe a Kubernetes service including its endpoints, load balancer status, and events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string"},
                "service_name": {"type": "string"},
            },
            "required": ["namespace", "service_name"],
        },
    },
    {
        "name": "scale_deployment",
        "description": "Scale a deployment to a specific replica count. Requires approval for production namespaces.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string"},
                "deployment_name": {"type": "string"},
                "replicas": {"type": "integer"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["namespace", "deployment_name", "replicas"],
        },
    },
    {
        "name": "get_hpa_status",
        "description": "Get HorizontalPodAutoscaler status, current/target replicas, and scaling events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string"},
            },
            "required": ["namespace"],
        },
    },
]


# ── Router ────────────────────────────────────────────────────────────────────

async def execute(tool_name: str, tool_input: dict) -> dict:
    executors = {
        "get_pod_status": _get_pod_status,
        "get_pod_logs": _get_pod_logs,
        "get_recent_deployments": _get_recent_deployments,
        "get_resource_usage": _get_resource_usage,
        "describe_service": _describe_service,
        "scale_deployment": _scale_deployment,
        "get_hpa_status": _get_hpa_status,
    }
    fn = executors.get(tool_name)
    if fn:
        return await fn(tool_input)
    return {"error": f"Unknown tool: {tool_name}"}


# ── Real implementations ──────────────────────────────────────────────────────

async def _get_pod_status(inp: dict) -> dict:
    if not _k8s_available:
        return await _mock_pod_status(inp)

    ns = inp["namespace"]
    selector = inp.get("label_selector")

    def _fetch():
        kwargs: dict = {"namespace": ns}
        if selector:
            kwargs["label_selector"] = selector
        pod_list = _core_v1.list_namespaced_pod(**kwargs)

        pods = []
        summary = {"running": 0, "pending": 0, "failed": 0, "crashloopbackoff": 0, "total": 0}
        for p in pod_list.items:
            phase = (p.status.phase or "Unknown").lower()
            restarts = 0
            status_str = p.status.phase or "Unknown"

            # Check for CrashLoopBackOff in container statuses
            if p.status.container_statuses:
                for cs in p.status.container_statuses:
                    restarts += cs.restart_count or 0
                    if cs.state and cs.state.waiting and cs.state.waiting.reason == "CrashLoopBackOff":
                        status_str = "CrashLoopBackOff"
                        phase = "crashloopbackoff"

            ready_containers = 0
            total_containers = len(p.spec.containers) if p.spec.containers else 1
            if p.status.container_statuses:
                ready_containers = sum(1 for cs in p.status.container_statuses if cs.ready)

            age_seconds = int((datetime.now(timezone.utc) - p.metadata.creation_timestamp.replace(tzinfo=timezone.utc)).total_seconds())
            age_str = f"{age_seconds // 60}m" if age_seconds < 3600 else f"{age_seconds // 3600}h"

            pods.append({
                "name": p.metadata.name,
                "status": status_str,
                "restarts": restarts,
                "age": age_str,
                "ready": f"{ready_containers}/{total_containers}",
                "node": p.spec.node_name,
                "namespace": ns,
            })

            if phase == "running":
                summary["running"] += 1
            elif phase == "pending":
                summary["pending"] += 1
            elif phase == "failed":
                summary["failed"] += 1
            elif phase == "crashloopbackoff":
                summary["crashloopbackoff"] += 1
            summary["total"] += 1

        return {"namespace": ns, "pods": pods, "summary": summary,
                "timestamp": datetime.now(timezone.utc).isoformat(), "source": "live"}

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        return {**await _mock_pod_status(inp), "warning": f"Live k8s failed ({e}), showing mock data"}


async def _get_pod_logs(inp: dict) -> dict:
    if not _k8s_available:
        return await _mock_pod_logs(inp)

    ns = inp["namespace"]
    pod = inp["pod_name"]
    lines = inp.get("lines", 100)
    filter_errors = inp.get("filter_errors", False)

    def _fetch():
        log_text = _core_v1.read_namespaced_pod_log(
            name=pod, namespace=ns, tail_lines=lines, timestamps=True
        )
        log_lines = log_text.splitlines() if log_text else []
        if filter_errors:
            log_lines = [l for l in log_lines if any(w in l.upper() for w in ("ERROR", "FATAL", "WARN", "PANIC", "EXCEPTION"))]
        error_count = sum(1 for l in log_lines if any(w in l.upper() for w in ("ERROR", "FATAL", "PANIC")))
        return {"pod": pod, "logs": log_lines, "error_count": error_count, "source": "live"}

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        return {**await _mock_pod_logs(inp), "warning": f"Live logs failed ({e}), showing mock"}


async def _get_recent_deployments(inp: dict) -> dict:
    if not _k8s_available:
        return await _mock_recent_deployments(inp)

    ns = inp["namespace"]
    hours = inp.get("hours", 6)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    def _fetch():
        deploys = _apps_v1.list_namespaced_deployment(namespace=ns)
        results = []
        for d in deploys.items:
            created = d.metadata.creation_timestamp
            if created and created.replace(tzinfo=timezone.utc) > cutoff:
                continue  # too old — skip
            results.append({
                "name": d.metadata.name,
                "replicas_desired": d.spec.replicas,
                "replicas_ready": d.status.ready_replicas or 0,
                "image": d.spec.template.spec.containers[0].image if d.spec.template.spec.containers else "unknown",
                "updated_at": d.metadata.creation_timestamp.isoformat() if d.metadata.creation_timestamp else None,
                "rollout_status": "success" if (d.status.ready_replicas or 0) == (d.spec.replicas or 0) else "in_progress",
            })
        return {"namespace": ns, "deployments": results[:10], "source": "live"}

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        return {**await _mock_recent_deployments(inp), "warning": f"Live deployments failed ({e}), showing mock"}


async def _get_resource_usage(inp: dict) -> dict:
    if not _k8s_available:
        return await _mock_resource_usage(inp)

    ns = inp["namespace"]
    rtype = inp.get("resource_type", "pods")

    def _fetch_nodes():
        nodes = _core_v1.list_node()
        result = []
        for n in nodes.items:
            allocatable = n.status.allocatable or {}
            conditions = {c.type: c.status for c in (n.status.conditions or [])}
            result.append({
                "name": n.metadata.name,
                "ready": conditions.get("Ready", "Unknown") == "True",
                "cpu_allocatable": allocatable.get("cpu", "unknown"),
                "memory_allocatable": allocatable.get("memory", "unknown"),
                "pods_allocatable": int(allocatable.get("pods", 110)),
            })
        return {"nodes": result, "source": "live"}

    def _fetch_pods():
        try:
            metrics = _custom_objects.list_namespaced_custom_object(
                "metrics.k8s.io", "v1beta1", ns, "pods"
            )
            pods = []
            for item in metrics.get("items", []):
                containers = item.get("containers", [])
                total_cpu = sum(_parse_cpu(c["usage"].get("cpu", "0")) for c in containers)
                total_mem = sum(_parse_mem(c["usage"].get("memory", "0")) for c in containers)
                pods.append({
                    "name": item["metadata"]["name"],
                    "cpu_m": total_cpu,
                    "memory_mi": total_mem,
                })
            return {"pods": pods, "source": "live_metrics"}
        except Exception:
            pod_list = _core_v1.list_namespaced_pod(namespace=ns)
            pods = []
            for p in pod_list.items:
                pods.append({
                    "name": p.metadata.name,
                    "cpu_request": _get_resource_field(p, "cpu", "requests"),
                    "memory_request": _get_resource_field(p, "memory", "requests"),
                    "cpu_limit": _get_resource_field(p, "cpu", "limits"),
                    "memory_limit": _get_resource_field(p, "memory", "limits"),
                })
            return {"pods": pods, "source": "live_requests_only"}

    try:
        if rtype == "nodes":
            return await asyncio.to_thread(_fetch_nodes)
        return await asyncio.to_thread(_fetch_pods)
    except Exception as e:
        return {**await _mock_resource_usage(inp), "warning": f"Live metrics failed ({e}), showing mock"}


async def _describe_service(inp: dict) -> dict:
    if not _k8s_available:
        return await _mock_describe_service(inp)

    ns = inp["namespace"]
    svc_name = inp["service_name"]

    def _fetch():
        svc = _core_v1.read_namespaced_service(name=svc_name, namespace=ns)
        try:
            ep = _core_v1.read_namespaced_endpoints(name=svc_name, namespace=ns)
            endpoint_ips = []
            for subset in (ep.subsets or []):
                for addr in (subset.addresses or []):
                    endpoint_ips.append(addr.ip)
        except Exception:
            endpoint_ips = []

        events_resp = _core_v1.list_namespaced_event(
            namespace=ns, field_selector=f"involvedObject.name={svc_name}"
        )
        events = [
            {"type": e.type, "reason": e.reason, "message": e.message,
             "time": e.last_timestamp.isoformat() if e.last_timestamp else None}
            for e in (events_resp.items or [])[-5:]
        ]

        ports = [{"port": p.port, "target_port": str(p.target_port), "protocol": p.protocol}
                 for p in (svc.spec.ports or [])]

        return {
            "name": svc_name,
            "namespace": ns,
            "type": svc.spec.type,
            "cluster_ip": svc.spec.cluster_ip,
            "ports": ports,
            "selector": svc.spec.selector,
            "endpoints": endpoint_ips,
            "ready": len(endpoint_ips) > 0,
            "events": events,
            "source": "live",
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        return {**await _mock_describe_service(inp), "warning": f"Live service info failed ({e}), showing mock"}


async def _scale_deployment(inp: dict) -> dict:
    if not _k8s_available or inp.get("dry_run", True):
        return await _mock_scale_deployment(inp)

    ns = inp["namespace"]
    name = inp["deployment_name"]
    replicas = inp["replicas"]

    def _scale():
        from kubernetes import client as k8s_client  # type: ignore
        body = {"spec": {"replicas": replicas}}
        _apps_v1.patch_namespaced_deployment_scale(name=name, namespace=ns, body=body)
        return {
            "deployment": name,
            "namespace": ns,
            "to_replicas": replicas,
            "dry_run": False,
            "status": "scaled",
            "source": "live",
        }

    try:
        return await asyncio.to_thread(_scale)
    except Exception as e:
        return {"error": str(e), "deployment": name, "namespace": ns}


async def _get_hpa_status(inp: dict) -> dict:
    if not _k8s_available:
        return await _mock_hpa_status(inp)

    ns = inp["namespace"]

    def _fetch():
        hpa_list = _autoscaling_v1.list_namespaced_horizontal_pod_autoscaler(namespace=ns)
        hpas = []
        for h in hpa_list.items:
            hpas.append({
                "name": h.metadata.name,
                "min_replicas": h.spec.min_replicas,
                "max_replicas": h.spec.max_replicas,
                "current_replicas": h.status.current_replicas,
                "desired_replicas": h.status.desired_replicas,
                "current_cpu_pct": h.status.current_cpu_utilization_percentage,
                "target_cpu_pct": h.spec.target_cpu_utilization_percentage,
            })
        return {"hpas": hpas, "namespace": ns, "source": "live"}

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        return {**await _mock_hpa_status(inp), "warning": f"Live HPA failed ({e}), showing mock"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_cpu(cpu_str: str) -> int:
    if cpu_str.endswith("n"):
        return int(cpu_str[:-1]) // 1_000_000
    if cpu_str.endswith("u"):
        return int(cpu_str[:-1]) // 1_000
    if cpu_str.endswith("m"):
        return int(cpu_str[:-1])
    return int(float(cpu_str) * 1000)


def _parse_mem(mem_str: str) -> int:
    if mem_str.endswith("Ki"):
        return int(mem_str[:-2]) // 1024
    if mem_str.endswith("Mi"):
        return int(mem_str[:-2])
    if mem_str.endswith("Gi"):
        return int(mem_str[:-2]) * 1024
    return int(mem_str) // (1024 * 1024)


def _get_resource_field(pod: Any, resource: str, field: str) -> str:
    try:
        for c in pod.spec.containers:
            if c.resources and getattr(c.resources, field):
                return getattr(c.resources, field).get(resource, "?")
    except Exception:
        pass
    return "?"


# ── Mock fallbacks (identical to original) ────────────────────────────────────

async def _mock_pod_status(inp: dict) -> dict:
    ns = inp["namespace"]
    now = datetime.now(timezone.utc)
    pods = [
        {"name": f"payment-service-7d9f8b-{s}", "status": "Running", "restarts": r, "age": f"{a}m",
         "ready": "1/1", "node": f"node-{n}"}
        for s, r, a, n in [("xk2p9", 0, 12, 1), ("mn4q7", 0, 12, 2), ("bv3r1", 14, 3, 3)]
    ] + [
        {"name": "auth-service-5c6d7e-abc12", "status": "Running", "restarts": 0, "age": "45m", "ready": "1/1", "node": "node-1"},
        {"name": "order-service-8f9g0h-def34", "status": "CrashLoopBackOff", "restarts": 23, "age": "8m", "ready": "0/1", "node": "node-2"},
        {"name": "notification-svc-2b3c4d-ghi56", "status": "Pending", "restarts": 0, "age": "2m", "ready": "0/1", "node": None},
    ]
    return {
        "namespace": ns, "pods": pods,
        "summary": {"running": 4, "pending": 1, "crashloopbackoff": 1, "total": 6},
        "timestamp": now.isoformat(), "source": "mock",
    }


async def _mock_pod_logs(inp: dict) -> dict:
    pod = inp["pod_name"]
    lines = inp.get("lines", 100)
    filter_errors = inp.get("filter_errors", False)
    now = datetime.now(timezone.utc)

    if "order-service" in pod:
        log_lines = [
            f"[{(now - timedelta(minutes=8)).isoformat()}] INFO  Starting order-service v2.4.1",
            f"[{(now - timedelta(minutes=7, seconds=58)).isoformat()}] INFO  Connecting to postgres://orders-db:5432/orders",
            f"[{(now - timedelta(minutes=7, seconds=55)).isoformat()}] ERROR Failed to connect to database: connection refused (host=orders-db, port=5432)",
            f"[{(now - timedelta(minutes=7, seconds=54)).isoformat()}] ERROR FATAL: database connection pool exhausted after 3 retries",
            f"[{(now - timedelta(minutes=7, seconds=54)).isoformat()}] ERROR panic: runtime error: nil pointer dereference",
            f"[{(now - timedelta(minutes=4)).isoformat()}] INFO  Starting order-service v2.4.1",
            f"[{(now - timedelta(minutes=3, seconds=58)).isoformat()}] ERROR Failed to connect to database: connection refused",
            f"[{(now - timedelta(minutes=3, seconds=57)).isoformat()}] ERROR FATAL: database connection pool exhausted after 3 retries",
        ]
        if filter_errors:
            log_lines = [l for l in log_lines if "ERROR" in l or "FATAL" in l]
        return {"pod": pod, "logs": log_lines[-lines:], "error_count": 6, "source": "mock"}

    return {
        "pod": pod,
        "logs": [f"[{(now - timedelta(minutes=i)).isoformat()}] INFO  Healthy - processing requests" for i in range(min(lines, 10))],
        "error_count": 0, "source": "mock",
    }


async def _mock_recent_deployments(inp: dict) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "namespace": inp["namespace"],
        "deployments": [
            {
                "name": "order-service", "image_from": "order-service:v2.4.0", "image_to": "order-service:v2.4.1",
                "deployed_at": (now - timedelta(minutes=9)).isoformat(), "deployed_by": "ci-pipeline/github-actions",
                "commit": "a3f8b2c", "commit_message": "feat: migrate to connection pool v3",
                "rollout_status": "failed",
            },
            {
                "name": "payment-service", "image_from": "payment-service:v1.9.5", "image_to": "payment-service:v1.9.6",
                "deployed_at": (now - timedelta(hours=2)).isoformat(), "deployed_by": "alice@company.com",
                "commit": "f1e2d3c", "commit_message": "fix: handle stripe webhook timeout",
                "rollout_status": "success",
            },
        ],
        "source": "mock",
    }


async def _mock_resource_usage(inp: dict) -> dict:
    if inp.get("resource_type") == "nodes":
        return {
            "nodes": [
                {"name": "node-1", "cpu_pct": 71, "memory_pct": 83, "pods": 18, "capacity_pods": 30},
                {"name": "node-2", "cpu_pct": 45, "memory_pct": 92, "pods": 22, "capacity_pods": 30},
                {"name": "node-3", "cpu_pct": 12, "memory_pct": 34, "pods": 9, "capacity_pods": 30},
            ],
            "source": "mock",
        }
    return {
        "pods": [
            {"name": "payment-service-7d9f8b-xk2p9", "cpu_m": 380, "cpu_limit_m": 500, "memory_mi": 512, "memory_limit_mi": 1024},
            {"name": "payment-service-7d9f8b-mn4q7", "cpu_m": 420, "cpu_limit_m": 500, "memory_mi": 890, "memory_limit_mi": 1024},
            {"name": "payment-service-7d9f8b-bv3r1", "cpu_m": 498, "cpu_limit_m": 500, "memory_mi": 1021, "memory_limit_mi": 1024},
            {"name": "auth-service-5c6d7e-abc12", "cpu_m": 45, "cpu_limit_m": 200, "memory_mi": 128, "memory_limit_mi": 512},
        ],
        "source": "mock",
    }


async def _mock_describe_service(inp: dict) -> dict:
    return {
        "name": inp["service_name"], "namespace": inp["namespace"],
        "type": "ClusterIP", "cluster_ip": "10.96.14.23", "port": 5432,
        "selector": {"app": "orders-db"}, "endpoints": [],
        "events": [{"type": "Warning", "reason": "FailedMount",
                    "message": "Unable to attach volume 'orders-db-pvc': volume not found", "time": "8m ago"}],
        "ready": False, "source": "mock",
    }


async def _mock_scale_deployment(inp: dict) -> dict:
    dry_run = inp.get("dry_run", True)
    return {
        "deployment": inp["deployment_name"], "namespace": inp["namespace"],
        "from_replicas": 1, "to_replicas": inp["replicas"], "dry_run": dry_run,
        "status": "dry_run_success" if dry_run else "scaled",
        "kubectl_command": f"kubectl scale deployment/{inp['deployment_name']} --replicas={inp['replicas']} -n {inp['namespace']}" + (" --dry-run=client" if dry_run else ""),
        "source": "mock",
    }


async def _mock_hpa_status(inp: dict) -> dict:
    return {
        "hpas": [{
            "name": "payment-service-hpa", "min_replicas": 2, "max_replicas": 10,
            "current_replicas": 3, "desired_replicas": 5,
            "current_cpu_pct": 84, "target_cpu_pct": 60,
            "scaling_event": "ScaleUp triggered 2m ago",
        }],
        "source": "mock",
    }


def k8s_status() -> dict:
    return {"available": _k8s_available, "mode": "live" if _k8s_available else "mock"}

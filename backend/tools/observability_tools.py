"""
Observability tool definitions — metrics, logs, traces for Claude tool use.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


TOOL_DEFINITIONS = [
    {
        "name": "query_metrics",
        "description": "Query Prometheus-style metrics for a service. Returns time-series data for latency, error rate, throughput.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "metric": {"type": "string", "enum": ["latency_p99", "latency_p50", "error_rate", "rps", "memory_usage", "cpu_usage"]},
                "window_minutes": {"type": "integer", "default": 30},
            },
            "required": ["service", "metric"],
        },
    },
    {
        "name": "query_logs",
        "description": "Search logs across services using a keyword or regex pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "query": {"type": "string", "description": "Search term or regex"},
                "severity": {"type": "string", "enum": ["ERROR", "WARN", "INFO", "DEBUG", "ALL"], "default": "ERROR"},
                "window_minutes": {"type": "integer", "default": 15},
            },
            "required": ["service", "query"],
        },
    },
    {
        "name": "get_service_dependencies",
        "description": "Get the dependency graph for a service — what it calls and what calls it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "depth": {"type": "integer", "default": 2},
            },
            "required": ["service"],
        },
    },
    {
        "name": "get_active_alerts",
        "description": "List all currently firing alerts with severity and duration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity_filter": {"type": "string", "enum": ["critical", "warning", "all"], "default": "all"},
            },
        },
    },
]


async def execute(tool_name: str, tool_input: dict) -> dict:
    executors = {
        "query_metrics": _query_metrics,
        "query_logs": _query_logs,
        "get_service_dependencies": _get_service_dependencies,
        "get_active_alerts": _get_active_alerts,
    }
    fn = executors.get(tool_name)
    if fn:
        return await fn(tool_input)
    return {"error": f"Unknown tool: {tool_name}"}


async def _query_metrics(inp: dict) -> dict:
    service = inp["service"]
    metric = inp["metric"]
    window = inp.get("window_minutes", 30)
    now = datetime.now(timezone.utc)

    if "order" in service:
        baselines = {
            "latency_p99": [45, 48, 52, 49, 51, 880, 1240, 2100, 3800, 4200],
            "error_rate": [0.1, 0.2, 0.1, 0.0, 0.2, 12.4, 45.8, 89.2, 97.8, 100.0],
            "rps": [120, 118, 125, 122, 119, 98, 67, 34, 12, 3],
        }
    else:
        baselines = {
            "latency_p99": [42, 44, 43, 45, 44, 46, 43, 45, 44, 43],
            "error_rate": [0.1, 0.0, 0.2, 0.1, 0.0, 0.1, 0.2, 0.1, 0.0, 0.1],
            "rps": [200, 198, 205, 201, 199, 203, 200, 197, 202, 204],
        }

    values = baselines.get(metric, [50] * 10)
    step = window / len(values)
    datapoints = [
        {"ts": (now - timedelta(minutes=window - i * step)).isoformat(), "value": v}
        for i, v in enumerate(values)
    ]
    return {
        "service": service,
        "metric": metric,
        "unit": "ms" if "latency" in metric else ("%" if "rate" in metric or "usage" in metric else "req/s"),
        "datapoints": datapoints,
        "current": values[-1],
        "avg": round(sum(values) / len(values), 2),
        "max": max(values),
    }


async def _query_logs(inp: dict) -> dict:
    service = inp["service"]
    query = inp["query"]
    now = datetime.now(timezone.utc)
    if "order" in service or "database" in query.lower() or "connection" in query.lower():
        return {
            "service": service,
            "query": query,
            "matches": [
                {"ts": (now - timedelta(minutes=8)).isoformat(), "level": "ERROR", "msg": "Failed to connect to database: connection refused (host=orders-db port=5432)"},
                {"ts": (now - timedelta(minutes=7, seconds=55)).isoformat(), "level": "ERROR", "msg": "connection pool exhausted: max_open=10 in_use=10 idle=0"},
                {"ts": (now - timedelta(minutes=7, seconds=54)).isoformat(), "level": "ERROR", "msg": "FATAL: nil pointer dereference in db.QueryRow() — orders-db service unreachable"},
            ],
            "total_matches": 47,
            "window_minutes": inp.get("window_minutes", 15),
        }
    return {"service": service, "query": query, "matches": [], "total_matches": 0}


async def _get_service_dependencies(inp: dict) -> dict:
    graph = {
        "order-service": {
            "upstream": ["api-gateway", "payment-service"],
            "downstream": ["orders-db", "inventory-service", "notification-svc", "shipping-service"],
        },
        "payment-service": {
            "upstream": ["api-gateway", "order-service"],
            "downstream": ["payments-db", "stripe-api (external)", "fraud-detection"],
        },
        "auth-service": {
            "upstream": ["api-gateway"],
            "downstream": ["users-db", "redis-cache"],
        },
    }
    svc = inp["service"]
    deps = graph.get(svc, {"upstream": [], "downstream": []})
    return {
        "service": svc,
        "upstream_callers": deps["upstream"],
        "downstream_dependencies": deps["downstream"],
        "blast_radius": f"An outage in {svc} affects: {', '.join(deps['upstream'])} (upstream callers)",
    }


async def _get_active_alerts(inp: dict) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "alerts": [
            {
                "name": "PodCrashLoopBackOff",
                "severity": "critical",
                "service": "order-service",
                "namespace": "production",
                "message": "Pod order-service-8f9g0h-def34 is in CrashLoopBackOff (23 restarts)",
                "firing_since": (now - timedelta(minutes=8)).isoformat(),
                "runbook": "https://runbooks.internal/order-service/crash-loop",
            },
            {
                "name": "HighErrorRate",
                "severity": "critical",
                "service": "order-service",
                "namespace": "production",
                "message": "Error rate 97.8% (threshold: 5%)",
                "firing_since": (now - timedelta(minutes=7)).isoformat(),
            },
            {
                "name": "HPAMaxReplicas",
                "severity": "warning",
                "service": "payment-service",
                "namespace": "production",
                "message": "HPA scaling toward max replicas (3/10), CPU at 84%",
                "firing_since": (now - timedelta(minutes=4)).isoformat(),
            },
            {
                "name": "NodeMemoryPressure",
                "severity": "warning",
                "service": "node-2",
                "namespace": "kube-system",
                "message": "Node node-2 memory at 92%",
                "firing_since": (now - timedelta(minutes=15)).isoformat(),
            },
        ]
    }

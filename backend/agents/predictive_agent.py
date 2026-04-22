"""
Predictive Intelligence Agent — anomaly forecasting and capacity planning.
Key differentiator vs NudgeBee: proactive prediction before incidents happen.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from core.claude_client import ClaudeClient
from tools import observability_tools, kubernetes_tools


_SYSTEM_PROMPT = """You are OpsBrain's Predictive Intelligence engine.
Your job is NOT to analyze current incidents — it is to predict future ones
before they happen. You have access to metrics tools.

When analyzing trends:
1. Look for gradual degradation patterns (error rate creeping up, latency 99th % rising)
2. Identify resource exhaustion trajectories (memory leak patterns, disk fill rate)
3. Spot traffic-driven capacity risks (RPS growing toward breaking point)
4. Flag deployment-correlated anomalies even if not yet critical

Always return structured JSON predictions with:
- service, risk_type, confidence_pct (0-100), eta_minutes (when it will become critical),
  current_value, threshold_value, trend_description, recommended_action

Be conservative — only flag real signals, not noise. Confidence below 60% = skip it.
"""


class PredictiveAgent:
    SERVICES = ["order-service", "payment-service", "auth-service", "notification-svc", "api-gateway"]
    METRICS = ["error_rate", "latency_p99", "rps", "memory_usage", "cpu_usage"]

    def __init__(self, claude: ClaudeClient) -> None:
        self.claude = claude

    async def predict_anomalies(self, services: list[str] | None = None) -> dict:
        """
        Analyse recent metric trends across services and predict upcoming anomalies.
        Returns structured predictions sorted by risk priority.
        """
        target_services = services or self.SERVICES
        collected: list[dict] = []

        async def tool_executor(tool_name: str, tool_input: dict) -> dict:
            return await observability_tools.execute(tool_name, tool_input)

        # Gather metrics for all services
        metrics_summary = []
        for svc in target_services:
            svc_data: dict = {"service": svc, "metrics": {}}
            for metric in self.METRICS:
                result = await observability_tools.execute("query_metrics", {
                    "service": svc, "metric": metric, "window_minutes": 60
                })
                if "error" not in result:
                    svc_data["metrics"][metric] = {
                        "current": result.get("current"),
                        "avg": result.get("avg"),
                        "max": result.get("max"),
                        "datapoints": result.get("datapoints", []),
                    }
            metrics_summary.append(svc_data)

        prompt = f"""
Analyze the following 60-minute metric trends across our services and predict which
services are heading toward an incident in the next 15-120 minutes.

METRIC DATA:
{json.dumps(metrics_summary, indent=2)}

Return a JSON object with this exact structure:
{{
  "predictions": [
    {{
      "service": "service-name",
      "risk_type": "memory_exhaustion|error_rate_spike|latency_degradation|capacity_limit|cascading_failure",
      "confidence_pct": 85,
      "eta_minutes": 45,
      "current_value": 78.4,
      "threshold_value": 100.0,
      "unit": "% memory",
      "trend_description": "Memory growing at 2.1% per minute over past 45 minutes — linear projection hits OOM in ~45 minutes",
      "recommended_action": "Restart pod or investigate memory leak in payment reconciliation worker"
    }}
  ],
  "services_analyzed": {len(target_services)},
  "highest_risk_service": "service-name or null",
  "analysis_timestamp": "{datetime.now(timezone.utc).isoformat()}"
}}

Only include predictions with confidence >= 60%. Return ONLY the JSON, no extra text.
"""
        result = await self.claude.analyze_with_tools(
            agent_type="sre",
            user_message=prompt,
            tools=[],
            tool_executor=tool_executor,
            system_override=_SYSTEM_PROMPT,
        )

        try:
            text = result["text"].strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            parsed = json.loads(text)
        except Exception:
            parsed = {
                "predictions": [],
                "services_analyzed": len(target_services),
                "highest_risk_service": None,
                "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
                "parse_error": result.get("text", "")[:500],
            }

        parsed["predictions"] = sorted(
            parsed.get("predictions", []),
            key=lambda p: (-p.get("confidence_pct", 0), p.get("eta_minutes", 999))
        )
        return parsed

    async def forecast_capacity(self, namespace: str = "production") -> dict:
        """
        Project resource consumption forward and predict when nodes/pods will hit limits.
        """
        nodes_data = await kubernetes_tools.execute("get_resource_usage", {
            "namespace": namespace, "resource_type": "nodes"
        })
        pods_data = await kubernetes_tools.execute("get_resource_usage", {
            "namespace": namespace, "resource_type": "pods"
        })
        hpa_data = await kubernetes_tools.execute("get_hpa_status", {
            "namespace": namespace
        })
        alerts = await observability_tools.execute("get_active_alerts", {})

        prompt = f"""
Forecast infrastructure capacity for namespace '{namespace}'.

CURRENT NODE UTILIZATION:
{json.dumps(nodes_data, indent=2)}

CURRENT POD RESOURCE USAGE:
{json.dumps(pods_data, indent=2)}

HPA STATUS:
{json.dumps(hpa_data, indent=2)}

ACTIVE ALERTS:
{json.dumps(alerts, indent=2)}

Produce a capacity forecast JSON:
{{
  "overall_health_score": 72,
  "runway": {{
    "cpu_days": 14,
    "memory_days": 3,
    "pod_slots_days": 21
  }},
  "bottlenecks": [
    {{
      "resource": "node-2 memory",
      "current_pct": 92,
      "projected_exhaustion_days": 3,
      "recommendation": "Add node or evict low-priority workloads"
    }}
  ],
  "hpa_risks": [
    {{
      "service": "payment-service",
      "current_replicas": 3,
      "max_replicas": 10,
      "pct_of_max": 30,
      "risk": "low|medium|high"
    }}
  ],
  "recommendations": [
    "Add a node to node group before memory exhaustion in 3 days",
    "Enable cluster autoscaler on ng-general-purpose"
  ],
  "namespace": "{namespace}",
  "forecast_timestamp": "{datetime.now(timezone.utc).isoformat()}"
}}

Return ONLY the JSON.
"""
        result = await self.claude.analyze_with_tools(
            agent_type="k8s",
            user_message=prompt,
            tools=[],
            tool_executor=lambda n, i: kubernetes_tools.execute(n, i),
            system_override=_SYSTEM_PROMPT,
        )

        try:
            text = result["text"].strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception:
            return {
                "namespace": namespace,
                "raw_analysis": result.get("text", ""),
                "forecast_timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def proactive_sweep(self) -> dict:
        """
        Run full anomaly detection + capacity forecast in one call.
        Used by the scheduled background job.
        """
        anomalies = await self.predict_anomalies()
        capacity = await self.forecast_capacity()

        critical_predictions = [p for p in anomalies.get("predictions", []) if p.get("eta_minutes", 999) < 30]
        return {
            "sweep_timestamp": datetime.now(timezone.utc).isoformat(),
            "anomaly_predictions": anomalies,
            "capacity_forecast": capacity,
            "critical_count": len(critical_predictions),
            "urgent_actions": [p["recommended_action"] for p in critical_predictions],
        }

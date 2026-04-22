"""
CheckoutPlan — compiled execution plan generated once from SOPs.

A plan encodes:
  1. tool_steps   — exact tool calls to make (deterministic, 0 LLM tokens at runtime)
  2. thresholds   — rules for auto-detecting critical/warning findings (0 LLM tokens)
  3. narrative_prompt — SHORT compressed prompt Claude uses to write the analysis
  4. report_template  — compact template snapshot Claude fills in

Runtime execution:
  1. Execute tool_steps mechanically → collected_data          (0 LLM)
  2. Evaluate thresholds against collected_data → auto_findings (0 LLM)
  3. Claude call: narrative_prompt + data + auto_findings       (~2k tokens)
  4. Claude fills report_template with real values              (included in above)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolStep:
    step: int
    tool: str
    params: dict          # may contain "{namespace}" placeholder
    purpose: str
    connector: str = ""   # "" | "aws" | "observability" | "kubernetes" | "cloud"


@dataclass
class CheckoutPlan:
    version: str
    compiled_at: str
    compiled_from: list[str]              # doc names used during compilation
    tool_steps: list[ToolStep]
    thresholds: dict[str, list[str]]      # {"critical": [...], "warning": [...]}
    narrative_prompt: str                 # SHORT ~200-word prompt reused every run
    report_template: str                  # compact template with {placeholders}
    estimated_tokens_saved_pct: int = 78  # vs full SOP approach

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "compiled_at": self.compiled_at,
            "compiled_from": self.compiled_from,
            "tool_steps": [
                {"step": s.step, "tool": s.tool, "params": s.params,
                 "purpose": s.purpose, "connector": s.connector}
                for s in self.tool_steps
            ],
            "thresholds": self.thresholds,
            "narrative_prompt": self.narrative_prompt,
            "report_template": self.report_template,
            "estimated_tokens_saved_pct": self.estimated_tokens_saved_pct,
        }

    @staticmethod
    def from_dict(d: dict) -> "CheckoutPlan":
        return CheckoutPlan(
            version=d.get("version", "1.0"),
            compiled_at=d.get("compiled_at", ""),
            compiled_from=d.get("compiled_from", []),
            tool_steps=[
                ToolStep(
                    step=s["step"], tool=s["tool"], params=s["params"],
                    purpose=s["purpose"], connector=s.get("connector", ""),
                )
                for s in d.get("tool_steps", [])
            ],
            thresholds=d.get("thresholds", {"critical": [], "warning": []}),
            narrative_prompt=d.get("narrative_prompt", ""),
            report_template=d.get("report_template", ""),
            estimated_tokens_saved_pct=d.get("estimated_tokens_saved_pct", 78),
        )


# ── Tool routing ──────────────────────────────────────────────────────────────

_K8S_TOOLS  = {"get_pod_status","get_pod_logs","get_recent_deployments",
               "get_resource_usage","describe_service","scale_deployment","get_hpa_status"}
_OBS_TOOLS  = {"query_metrics","query_logs","get_service_dependencies","get_active_alerts"}
_CLOUD_TOOLS= {"get_cloud_cost_breakdown","get_underutilized_resources",
               "get_rightsizing_recommendations","get_cost_anomalies"}


async def _run_step(step: ToolStep, namespace: str) -> Any:
    """Execute one tool step, resolving {namespace} placeholders."""
    params = {
        k: v.replace("{namespace}", namespace) if isinstance(v, str) else v
        for k, v in step.params.items()
    }

    connector = step.connector or _infer_connector(step.tool)

    if connector == "aws":
        return await _call_aws(step.tool, params)

    from tools import kubernetes_tools as k8s, observability_tools as obs, cloud_tools as cloud

    if step.tool in _K8S_TOOLS:
        return await k8s.execute(step.tool, params)
    if step.tool in _OBS_TOOLS:
        return await obs.execute(step.tool, params)
    if step.tool in _CLOUD_TOOLS:
        return await cloud.execute(step.tool, params)

    return {"error": f"Unknown tool: {step.tool}"}


def _infer_connector(tool: str) -> str:
    if tool in _K8S_TOOLS:   return "kubernetes"
    if tool in _OBS_TOOLS:   return "observability"
    if tool in _CLOUD_TOOLS: return "cloud"
    if "aws" in tool.lower(): return "aws"
    return ""


async def _call_aws(method: str, params: dict) -> Any:
    try:
        from connectors.registry import registry
        from connectors.base import ConnectorType
        aws = registry.get_by_type(ConnectorType.AWS)
        if not aws:
            return {"error": "AWS connector not configured"}
        conn = aws[0]
        if method == "fetch_alerts":
            return await conn.fetch_alerts()
        if method == "get_cost_breakdown":
            return await conn.get_cost_breakdown(**params)
        if method == "list_eks_clusters":
            return await conn.list_eks_clusters()
        return {"error": f"Unknown AWS method: {method}"}
    except Exception as e:
        return {"error": str(e)}


# ── Plan executor ─────────────────────────────────────────────────────────────

async def execute_plan(plan: CheckoutPlan, checkout, claude) -> dict:
    """
    Execute a compiled plan.  Three phases:
      Phase 1 — tool calls (0 LLM tokens)
      Phase 2 — threshold evaluation (0 LLM tokens)
      Phase 3 — one small Claude call for narrative + report (~2k tokens)
    """
    from datetime import datetime, timezone

    namespace = checkout.namespace
    frequency = checkout.frequency
    run_date  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    # ── Phase 1: execute tool calls ───────────────────────────────────────────
    collected: dict[str, Any] = {}
    step_errors: list[str] = []

    for step in plan.tool_steps:
        try:
            result = await _run_step(step, namespace)
            collected[step.purpose] = {"tool": step.tool, "data": result}
        except Exception as e:
            step_errors.append(f"Step {step.step} ({step.tool}): {e}")
            collected[step.purpose] = {"tool": step.tool, "error": str(e)}

    # ── Phase 2: threshold evaluation (rule-based, no LLM) ───────────────────
    auto_findings: dict[str, list[str]] = {"critical": [], "warning": []}
    auto_findings = _evaluate_thresholds(plan.thresholds, collected)

    # ── Phase 3: small Claude call ────────────────────────────────────────────
    narrative = plan.narrative_prompt.replace("{frequency}", frequency).replace("{namespace}", namespace)
    template  = plan.report_template.replace("{date}", run_date).replace("{namespace}", namespace).replace("{frequency}", frequency)

    analysis_prompt = f"""{narrative}

COLLECTED DATA (from {len(plan.tool_steps)} tool calls):
{json.dumps({k: v.get("data", v) for k, v in collected.items()}, indent=2, default=str)}

AUTO-DETECTED FINDINGS (from compiled thresholds — do not contradict these):
Critical: {auto_findings['critical'] or ['None']}
Warning:  {auto_findings['warning'] or ['None']}

REPORT TEMPLATE TO FOLLOW:
{template}

Return ONLY this JSON:
{{
  "status": "passed|warning|failed",
  "health_score": 85,
  "summary": "1-2 sentence executive summary with specific metric values",
  "key_findings": ["finding with specific number"],
  "critical_issues": ["critical issue — include service and metric"],
  "recommendations": [
    {{"priority": "P0|P1|P2", "action": "specific step", "impact": "expected outcome", "effort": "low|medium|high"}}
  ],
  "report_markdown": "COMPLETE REPORT following the template — replace all placeholders with real values from the data"
}}

Status rules (use auto-detected findings):
- failed  = any critical finding OR auto critical_count > 0
- warning = any warning finding
- passed  = no findings
"""
    result = await claude.analyze(agent_type="sre", user_message=analysis_prompt)

    text = result.get("text", "{}").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        analysis = json.loads(text)
    except Exception:
        analysis = {
            "status": "warning" if auto_findings["critical"] or auto_findings["warning"] else "passed",
            "health_score": None,
            "summary": "Plan executed — manual review recommended.",
            "key_findings": auto_findings["critical"] + auto_findings["warning"],
            "critical_issues": auto_findings["critical"],
            "recommendations": [],
            "report_markdown": result.get("text", ""),
        }

    # Override status with auto-detected findings if Claude was too lenient
    if auto_findings["critical"] and analysis.get("status") == "passed":
        analysis["status"] = "failed"
    elif auto_findings["warning"] and analysis.get("status") == "passed":
        analysis["status"] = "warning"

    return {
        "analysis": analysis,
        "collected": collected,
        "auto_findings": auto_findings,
        "step_errors": step_errors,
        "phases_used": {"tool_calls": len(plan.tool_steps), "llm_calls": 1},
    }


def _evaluate_thresholds(thresholds: dict[str, list[str]], collected: dict) -> dict[str, list[str]]:
    """
    Evaluate threshold rules against collected data.
    Rules are plain-English strings we match against data keys/values.
    This is best-effort — Claude's final analysis is the authoritative status.
    """
    findings: dict[str, list[str]] = {"critical": [], "warning": []}

    # Flatten all data for simple key scanning
    all_data_str = json.dumps(collected, default=str).lower()

    # Pod status checks
    for purpose, step_data in collected.items():
        data = step_data.get("data", {}) if isinstance(step_data, dict) else {}
        if isinstance(data, dict):
            pods = data.get("pods", [])
            for pod in (pods if isinstance(pods, list) else []):
                status = str(pod.get("status", "")).lower()
                restarts = int(pod.get("restarts", 0))
                name = pod.get("name", "unknown")
                if "crashloopbackoff" in status:
                    findings["critical"].append(f"Pod {name} in CrashLoopBackOff ({restarts} restarts)")
                elif "oomkilled" in status:
                    findings["critical"].append(f"Pod {name} OOMKilled")
                elif restarts > 50:
                    findings["critical"].append(f"Pod {name} has {restarts} restarts")
                elif restarts > 10:
                    findings["warning"].append(f"Pod {name} has {restarts} restarts")

            nodes = data.get("nodes", [])
            for node in (nodes if isinstance(nodes, list) else []):
                mem = int(node.get("memory_pct", 0))
                cpu = int(node.get("cpu_pct", 0))
                nname = node.get("name", "unknown")
                if mem > 90:
                    findings["critical"].append(f"Node {nname} memory at {mem}% (>90% threshold)")
                elif mem > 80:
                    findings["warning"].append(f"Node {nname} memory at {mem}% (>80% threshold)")
                if cpu > 90:
                    findings["critical"].append(f"Node {nname} CPU at {cpu}% (>90% threshold)")

            hpas = data.get("hpas", [])
            for hpa in (hpas if isinstance(hpas, list) else []):
                current = int(hpa.get("current_replicas", 0))
                maximum = int(hpa.get("max_replicas", 1))
                ratio = current / max(maximum, 1)
                hname = hpa.get("name", "unknown")
                if ratio >= 1.0:
                    findings["critical"].append(f"HPA {hname} at max replicas ({current}/{maximum})")
                elif ratio >= 0.8:
                    findings["warning"].append(f"HPA {hname} at {current}/{maximum} replicas ({ratio*100:.0f}% of max)")

            alerts = data.get("alerts", [])
            for alert in (alerts if isinstance(alerts, list) else []):
                sev = str(alert.get("severity", "")).lower()
                aname = alert.get("name", "alert")
                svc = alert.get("service", "")
                if sev == "critical":
                    findings["warning"].append(f"Alert {aname} firing on {svc}")

    return findings

"""
Checkout runner — real data gathering per checkout type, then Claude analysis.

Flow per checkout:
  1. _gather_*(checkout)   → collects raw data from k8s/AWS/observability tools
  2. _analyze(data, claude) → Claude adds narrative, root causes, recommendations
  3. _render_report(type, data, analysis) → structured markdown report
  4. save + notify
"""
from __future__ import annotations

import json
import textwrap
import uuid
from datetime import datetime, timezone
from typing import Any

from checkouts.models import Checkout, CheckoutStatus, RunHistory, WEEKDAYS
from checkouts.store import save_run, update_checkout_after_run, compute_next_run

# ── Type labels & display helpers ─────────────────────────────────────────────

TYPE_LABELS = {
    "infra_health":    "Infrastructure Health",
    "cost_review":     "Cost Review",
    "capacity_review": "Capacity Planning",
    "slo_review":      "SLO Review",
    "incident_review": "Incident Review",
    "custom":          "Custom",
}

_STATUS_EMOJI = {"passed": "✅", "warning": "⚠️", "failed": "🔴", "running": "⚙️", "pending": "⏳"}


# ── Data gathering — one function per checkout type ───────────────────────────

async def _gather_infra_health(checkout: Checkout) -> dict[str, Any]:
    """Collect K8s pod/node/HPA/deployment data + AWS CloudWatch alarms."""
    from tools import kubernetes_tools as k8s, observability_tools as obs

    data: dict[str, Any] = {"source": {}}

    data["pods"]        = await k8s.execute("get_pod_status",        {"namespace": checkout.namespace})
    data["nodes"]       = await k8s.execute("get_resource_usage",    {"namespace": checkout.namespace, "resource_type": "nodes"})
    data["pods_usage"]  = await k8s.execute("get_resource_usage",    {"namespace": checkout.namespace, "resource_type": "pods"})
    data["hpa"]         = await k8s.execute("get_hpa_status",        {"namespace": checkout.namespace})
    data["deployments"] = await k8s.execute("get_recent_deployments",{"namespace": checkout.namespace, "hours": 48})
    data["alerts"]      = await obs.execute("get_active_alerts",     {})

    data["source"]["k8s"]  = data["pods"].get("source", "unknown")

    # AWS: CloudWatch alarms + EKS cluster list
    try:
        from connectors.registry import registry
        from connectors.base import ConnectorType
        for conn in registry.get_by_type(ConnectorType.AWS)[:1]:
            data["aws_alarms"]   = await conn.fetch_alerts()
            data["eks_clusters"] = await conn.list_eks_clusters()
            data["source"]["aws"] = "live"
    except Exception as e:
        data["aws_note"] = f"AWS connector not configured or failed: {e}"
        data["source"]["aws"] = "not_configured"

    return data


async def _gather_cost_review(checkout: Checkout) -> dict[str, Any]:
    """Collect cloud cost data — real AWS Cost Explorer if configured, mock otherwise."""
    from tools import cloud_tools as cloud

    data: dict[str, Any] = {"source": {}}

    data["cost_breakdown"] = await cloud.execute("get_cloud_cost_breakdown",        {"cloud": "all", "months": 1})
    data["underutilized"]  = await cloud.execute("get_underutilized_resources",     {"resource_type": "all"})
    data["anomalies"]      = await cloud.execute("get_cost_anomalies",              {"days": 30, "threshold_pct": 15})
    data["rightsizing"]    = await cloud.execute("get_rightsizing_recommendations", {"namespace": checkout.namespace})

    data["source"]["cost"] = data["cost_breakdown"].get("source", "mock")

    # Real AWS Cost Explorer override
    try:
        from connectors.registry import registry
        from connectors.base import ConnectorType
        for conn in registry.get_by_type(ConnectorType.AWS)[:1]:
            real = await conn.get_cost_breakdown(months=1)
            if real.get("breakdown"):
                data["cost_breakdown"] = real
                data["source"]["cost"] = "aws_live"
            data["aws_alarms"] = await conn.fetch_alerts(severity="all")
    except Exception as e:
        data["aws_note"] = f"AWS connector not configured: {e}"

    return data


async def _gather_capacity_review(checkout: Checkout) -> dict[str, Any]:
    """Collect resource utilization + HPA headroom + per-service metrics."""
    from tools import kubernetes_tools as k8s, observability_tools as obs

    data: dict[str, Any] = {"source": {}}

    data["nodes"]      = await k8s.execute("get_resource_usage", {"namespace": checkout.namespace, "resource_type": "nodes"})
    data["pods"]       = await k8s.execute("get_resource_usage", {"namespace": checkout.namespace, "resource_type": "pods"})
    data["pod_status"] = await k8s.execute("get_pod_status",     {"namespace": checkout.namespace})
    data["hpa"]        = await k8s.execute("get_hpa_status",     {"namespace": checkout.namespace})

    # Per-service CPU + memory trends
    services = ["order-service", "payment-service", "auth-service", "notification-svc"]
    data["service_metrics"] = {}
    for svc in services:
        data["service_metrics"][svc] = {
            "cpu":    await obs.execute("query_metrics", {"service": svc, "metric": "cpu_usage",    "window_minutes": 60}),
            "memory": await obs.execute("query_metrics", {"service": svc, "metric": "memory_usage", "window_minutes": 60}),
        }

    data["source"]["k8s"] = data["nodes"].get("source", "unknown")
    return data


async def _gather_slo_review(checkout: Checkout) -> dict[str, Any]:
    """Collect error rate, latency, RPS per service + active alerts."""
    from tools import observability_tools as obs, kubernetes_tools as k8s

    data: dict[str, Any] = {"source": {}}
    data["alerts"]     = await obs.execute("get_active_alerts", {})
    data["pod_status"] = await k8s.execute("get_pod_status", {"namespace": checkout.namespace})

    services = ["order-service", "payment-service", "auth-service", "notification-svc", "api-gateway"]
    data["slo_metrics"] = {}
    for svc in services:
        data["slo_metrics"][svc] = {
            "error_rate":   await obs.execute("query_metrics", {"service": svc, "metric": "error_rate",   "window_minutes": 1440}),
            "latency_p99":  await obs.execute("query_metrics", {"service": svc, "metric": "latency_p99",  "window_minutes": 1440}),
            "rps":          await obs.execute("query_metrics", {"service": svc, "metric": "rps",          "window_minutes": 1440}),
        }

    data["source"]["obs"] = "live" if not data["alerts"].get("source") else data["alerts"].get("source", "mock")
    return data


async def _gather_incident_review(checkout: Checkout) -> dict[str, Any]:
    """Collect active alerts + error logs + recent deployments for incident retrospective."""
    from tools import observability_tools as obs, kubernetes_tools as k8s

    data: dict[str, Any] = {"source": {}}

    data["alerts"]      = await obs.execute("get_active_alerts",      {})
    data["pod_status"]  = await k8s.execute("get_pod_status",         {"namespace": checkout.namespace})
    data["deployments"] = await k8s.execute("get_recent_deployments", {"namespace": checkout.namespace, "hours": 72})

    # Error logs per service
    services = ["order-service", "payment-service", "auth-service"]
    data["error_logs"] = {}
    for svc in services:
        data["error_logs"][svc] = await obs.execute("query_logs", {
            "service": svc, "query": "ERROR|FATAL|panic",
            "severity": "ERROR", "window_minutes": 4320,  # 3 days
        })

    data["source"]["k8s"] = data["pod_status"].get("source", "unknown")
    return data


async def _gather_custom(checkout: Checkout) -> dict[str, Any]:
    """For custom checkouts: gather all available data so Claude has full context."""
    from tools import kubernetes_tools as k8s, observability_tools as obs, cloud_tools as cloud

    data: dict[str, Any] = {}
    data["pods"]           = await k8s.execute("get_pod_status",         {"namespace": checkout.namespace})
    data["nodes"]          = await k8s.execute("get_resource_usage",     {"namespace": checkout.namespace, "resource_type": "nodes"})
    data["hpa"]            = await k8s.execute("get_hpa_status",         {"namespace": checkout.namespace})
    data["alerts"]         = await obs.execute("get_active_alerts",      {})
    data["cost_breakdown"] = await cloud.execute("get_cloud_cost_breakdown", {"cloud": "all"})
    return data


_GATHERERS = {
    "infra_health":    _gather_infra_health,
    "cost_review":     _gather_cost_review,
    "capacity_review": _gather_capacity_review,
    "slo_review":      _gather_slo_review,
    "incident_review": _gather_incident_review,
    "custom":          _gather_custom,
}


# ── Claude analysis prompt (type-specific) ────────────────────────────────────

def _load_knowledge(checkout) -> tuple[str, str, str]:
    """
    Load SOP, report template, and context docs for this checkout run.

    Priority:
      1. Checkout has an explicitly assigned Knowledge Set → use exactly those docs
      2. A default Knowledge Set exists for this checkout type → use it
      3. Legacy fallback: query all docs tagged for this checkout type

    Returns (sop_text, template_text, set_name_used)
    """
    try:
        from knowledge.set_store import resolve_set
        from knowledge.store import get_doc, get_docs_for_checkout

        ks = resolve_set(checkout)

        if ks:
            # ── Set-based loading (unambiguous) ──────────────────────────────
            sop_text, template_text = "", ""
            if ks.sop_doc_id:
                sop_doc = get_doc(ks.sop_doc_id)
                if sop_doc:
                    sop_text = f"## SOP: {sop_doc.name}\n\n{sop_doc.content}"

            ctx_parts: list[str] = []
            for ctx_id in ks.context_doc_ids:
                ctx_doc = get_doc(ctx_id)
                if ctx_doc:
                    ctx_parts.append(f"## Context: {ctx_doc.name}\n\n{ctx_doc.content}")
            if ctx_parts:
                sop_text = (sop_text + "\n\n---\n\n" + "\n\n---\n\n".join(ctx_parts)).strip()

            if ks.template_doc_id:
                tpl_doc = get_doc(ks.template_doc_id)
                if tpl_doc:
                    template_text = f"## Report Template: {tpl_doc.name}\n\n{tpl_doc.content}"

            set_name = f'Knowledge Set: "{ks.name}"'
            return sop_text, template_text, set_name

        else:
            # ── Legacy fallback: type-based lookup ───────────────────────────
            checkout_type = getattr(checkout, "checkout_type", str(checkout))
            docs     = get_docs_for_checkout(checkout_type)
            sops     = [d for d in docs if d.doc_type == "sop"]
            templates= [d for d in docs if d.doc_type == "report_template"]
            context  = [d for d in docs if d.doc_type == "context"]

            sop_text = "\n\n---\n\n".join(f"## SOP: {s.name}\n\n{s.content}" for s in sops)
            if context:
                ctx_text = "\n\n---\n\n".join(f"## Context: {c.name}\n\n{c.content}" for c in context)
                sop_text = (sop_text + "\n\n---\n\n" + ctx_text).strip()
            template_text = "\n\n---\n\n".join(f"## Report Template: {t.name}\n\n{t.content}" for t in templates)
            return sop_text, template_text, "type-based lookup (no set assigned)"

    except Exception as exc:
        return "", "", f"error loading knowledge: {exc}"


def _build_analysis_prompt(checkout: Checkout, data: dict) -> str:
    """
    Build the Claude analysis prompt.
    Loads the correct SOP + template from the assigned Knowledge Set (or falls back).
    """
    sop_text, template_text, set_name = _load_knowledge(checkout)
    label = TYPE_LABELS.get(checkout.checkout_type, "Infrastructure")

    # ── SOP context block ─────────────────────────────────────────────────────
    if sop_text:
        sop_block = f"""
══════════════════════════════════════════════════════════
STANDARD OPERATING PROCEDURE — follow these steps exactly
══════════════════════════════════════════════════════════

{sop_text}

══════════════════════════════════════════════════════════
"""
    else:
        sop_block = f"""
No SOP loaded for {label}. Apply professional engineering judgment.
Check: pod health, resource utilization, active alerts, recent deployments.
"""

    # ── Template context block ────────────────────────────────────────────────
    if template_text:
        template_block = f"""
══════════════════════════════════════════════════════════
REPORT FORMAT — your output must follow this structure exactly
Replace placeholder values (in {{{{braces}}}}) with actual data.
Preserve all table headers and section headings.
══════════════════════════════════════════════════════════

{template_text}

══════════════════════════════════════════════════════════
"""
    else:
        template_block = """
No report template loaded. Use professional Markdown with:
- Executive summary
- Per-component status tables with actual values
- Prioritized recommendations (P0/P1/P2)
"""

    # ── Custom prompt override ────────────────────────────────────────────────
    custom_block = ""
    if checkout.custom_prompt:
        custom_block = f"""
══════════════════════════════════════════════════════════
ADDITIONAL INSTRUCTIONS FROM OPERATOR
══════════════════════════════════════════════════════════
{checkout.custom_prompt}
══════════════════════════════════════════════════════════
"""

    return f"""You are OpsBrain's AI analyst running a {checkout.frequency} {label} checkout.

Checkout configuration:
- Namespace: {checkout.namespace}
- Run date: See data timestamps
- Checkout name: {checkout.name}

{sop_block}

{custom_block}

══════════════════════════════════════════════════════════
COLLECTED DATA (from tools — this is real infrastructure data)
══════════════════════════════════════════════════════════

{json.dumps(data, indent=2, default=str)}

══════════════════════════════════════════════════════════
{template_block}

══════════════════════════════════════════════════════════
RESPONSE FORMAT — return ONLY this JSON, no extra text:
══════════════════════════════════════════════════════════

{{
  "status": "passed|warning|failed",
  "health_score": 85,
  "summary": "1-2 sentence executive summary — include the most important metric or finding with actual numbers",
  "key_findings": ["finding with specific value", "finding with specific value"],
  "critical_issues": ["issue description — include service name and metric"],
  "recommendations": [
    {{"priority": "P0|P1|P2", "action": "specific actionable step", "impact": "expected outcome with metric", "effort": "low|medium|high"}}
  ],
  "analysis_narrative": "Full analysis following the SOP. Reference actual values from the collected data. Use the report template structure.",
  "report_markdown": "COMPLETE FORMATTED REPORT following the template above. Replace all {{{{placeholders}}}} with real data. This is what gets sent to users."
}}

Rules:
- "failed" = critical issue requiring immediate action (outage, breach, runaway cost)
- "warning" = issue requiring attention within 24-48 hours
- "passed" = healthy, all checks within normal bounds
- report_markdown MUST follow the template structure if one was provided
- Every number must come from the collected data — no fabrication
"""


# ── Report renderer — builds the final markdown report ────────────────────────

def _render_report(checkout: Checkout, data: dict, analysis: dict, run_date: str) -> str:
    label   = TYPE_LABELS.get(checkout.checkout_type, checkout.checkout_type)
    status  = analysis.get("status", "warning")
    emoji   = _STATUS_EMOJI.get(status, "ℹ️")
    score   = analysis.get("health_score", "N/A")
    sources = data.get("source", {})

    header = textwrap.dedent(f"""\
        # {emoji} {checkout.name}
        **Type:** {label} &nbsp;·&nbsp; **Frequency:** {checkout.frequency.title()} &nbsp;·&nbsp; **Namespace:** {checkout.namespace}
        **Run date:** {run_date} UTC &nbsp;·&nbsp; **Status:** {status.upper()}
        **Data sources:** {', '.join(f'{k}:{v}' for k,v in sources.items()) or 'mock/demo'}

        ---

        ## Executive Summary
        {analysis.get('summary', 'No summary generated.')}
    """)

    # Key findings
    findings = analysis.get("key_findings", [])
    findings_md = "\n".join(f"- {f}" for f in findings) if findings else "- No findings."
    findings_section = f"\n## Key Findings\n{findings_md}\n"

    # Critical issues
    critical = analysis.get("critical_issues", [])
    critical_md = ""
    if critical:
        items = "\n".join(f"- 🔴 {c}" for c in critical)
        critical_md = f"\n## 🔴 Critical Issues\n{items}\n"

    # Type-specific data tables
    data_section = _render_data_tables(checkout.checkout_type, data)

    # Analysis narrative
    narrative = analysis.get("analysis_narrative", "")
    narrative_md = f"\n## Detailed Analysis\n{narrative}\n" if narrative else ""

    # Recommendations table
    recs = analysis.get("recommendations", [])
    rec_md = ""
    if recs:
        rows = "\n".join(
            f"| {r.get('priority','P2')} | {r.get('action','')} | {r.get('impact','')} | {r.get('effort','')} |"
            for r in recs
        )
        rec_md = f"\n## Recommendations\n| Priority | Action | Expected Impact | Effort |\n|----------|--------|-----------------|--------|\n{rows}\n"

    # Health score (where applicable)
    score_md = f"\n## Health Score: {score}/100\n" if isinstance(score, (int, float)) else ""

    return header + score_md + findings_section + critical_md + data_section + narrative_md + rec_md


def _render_data_tables(checkout_type: str, data: dict) -> str:
    """Build type-specific data tables from raw gathered data."""
    sections = []

    if checkout_type == "infra_health":
        # Pod status table
        pods = data.get("pods", {}).get("pods", [])
        if pods:
            rows = "\n".join(
                f"| {p.get('name','')} | {p.get('status','')} | {p.get('restarts',0)} | {p.get('ready','')} | {p.get('node','—')} |"
                for p in pods[:20]
            )
            sections.append(
                f"\n## Pod Status ({data.get('pods',{}).get('summary',{}).get('total',0)} pods)\n"
                f"| Pod | Status | Restarts | Ready | Node |\n|-----|--------|----------|-------|------|\n{rows}\n"
            )
        # Node utilization
        nodes = data.get("nodes", {}).get("nodes", [])
        if nodes:
            rows = "\n".join(
                f"| {n.get('name','')} | {n.get('cpu_pct','?')}% | {n.get('memory_pct','?')}% | {n.get('pods','?')}/{n.get('capacity_pods','?')} |"
                for n in nodes
            )
            sections.append(
                f"\n## Node Utilization\n| Node | CPU | Memory | Pods |\n|------|-----|--------|------|\n{rows}\n"
            )
        # Alerts
        alerts = data.get("alerts", {}).get("alerts", [])
        if alerts:
            rows = "\n".join(
                f"| {a.get('severity','').upper()} | {a.get('name','')} | {a.get('service','')} | {a.get('message','')[:80]} |"
                for a in alerts
            )
            sections.append(
                f"\n## Active Alerts ({len(alerts)})\n| Severity | Name | Service | Message |\n|----------|------|---------|----------|\n{rows}\n"
            )
        # AWS
        aws_alarms = data.get("aws_alarms", [])
        if aws_alarms:
            rows = "\n".join(f"| {a.get('name','')} | {a.get('severity','')} | {a.get('message','')[:80]} |" for a in aws_alarms)
            sections.append(f"\n## AWS CloudWatch Alarms ({len(aws_alarms)})\n| Alarm | Severity | Reason |\n|-------|----------|--------|\n{rows}\n")
        elif data.get("aws_note"):
            sections.append(f"\n## AWS Status\n> {data['aws_note']}\n")

    elif checkout_type == "cost_review":
        breakdown = data.get("cost_breakdown", {})
        total = breakdown.get("total_monthly_usd", 0)
        prev  = breakdown.get("previous_month_usd", 0)
        mom   = breakdown.get("mom_change_pct", 0)
        if total:
            sections.append(f"\n## Spend Summary\n**This month:** ${total:,.0f} &nbsp;·&nbsp; **Last month:** ${prev:,.0f} &nbsp;·&nbsp; **MoM change:** {mom:+.1f}%\n")
        items = breakdown.get("breakdown", [])
        if items:
            rows = "\n".join(
                f"| {i.get('name','')} | ${i.get('monthly_usd',0):,.0f} | {i.get('pct',0):.1f}% | {i.get('trend','')} |"
                for i in items
            )
            sections.append(f"\n## Cost by Service\n| Service | Monthly Cost | % of Total | MoM Trend |\n|---------|-------------|------------|----------|\n{rows}\n")
        waste_total = data.get("underutilized", {}).get("total_waste_usd_month", 0)
        waste_items = data.get("underutilized", {}).get("resources", [])
        if waste_items:
            rows = "\n".join(
                f"| {r.get('type','').upper()} | {r.get('id','') or r.get('name','')} | ${r.get('monthly_cost_usd',0):,.0f} | {r.get('avg_cpu_pct','?')}% | ${r.get('estimated_savings_usd',0):,.0f} |"
                for r in waste_items
            )
            sections.append(
                f"\n## Waste & Underutilized Resources (${waste_total:,.0f}/mo total)\n"
                f"| Type | Resource | Monthly Cost | Avg CPU | Est. Savings |\n|------|----------|-------------|---------|---------------|\n{rows}\n"
            )
        anomalies = data.get("anomalies", {}).get("anomalies", [])
        if anomalies:
            rows = "\n".join(
                f"| {a.get('service','')} | {a.get('spike_date','')} | ${a.get('baseline_daily_usd',0):,.0f} | ${a.get('anomaly_daily_usd',0):,.0f} | +{a.get('change_pct',0):.0f}% |"
                for a in anomalies
            )
            sections.append(
                f"\n## Cost Anomalies\n| Service | Date | Baseline/day | Spike/day | Change |\n|---------|------|-------------|-----------|--------|\n{rows}\n"
            )

    elif checkout_type == "capacity_review":
        nodes = data.get("nodes", {}).get("nodes", [])
        if nodes:
            rows = "\n".join(
                f"| {n.get('name','')} | {n.get('cpu_pct','?')}% | {n.get('memory_pct','?')}% | {n.get('pods','?')}/{n.get('capacity_pods','?')} |"
                for n in nodes
            )
            sections.append(f"\n## Node Utilization\n| Node | CPU | Memory | Pod Slots |\n|------|-----|--------|----------|\n{rows}\n")
        hpas = data.get("hpa", {}).get("hpas", [])
        if hpas:
            rows = "\n".join(
                f"| {h.get('name','')} | {h.get('current_replicas',0)} | {h.get('max_replicas',0)} | {round(h.get('current_replicas',0)/max(h.get('max_replicas',1),1)*100)}% | {h.get('current_cpu_pct','?')}% |"
                for h in hpas
            )
            sections.append(f"\n## HPA Headroom\n| HPA | Current | Max | % Used | CPU |\n|-----|---------|-----|--------|-----|\n{rows}\n")

    elif checkout_type == "slo_review":
        slo_data = data.get("slo_metrics", {})
        if slo_data:
            rows = []
            for svc, metrics in slo_data.items():
                err = metrics.get("error_rate", {}).get("current", "?")
                lat = metrics.get("latency_p99", {}).get("current", "?")
                rps = metrics.get("rps", {}).get("current", "?")
                # Simple traffic light
                light = "🟢"
                if isinstance(err, (int, float)) and err > 5:
                    light = "🔴"
                elif isinstance(err, (int, float)) and err > 1:
                    light = "🟡"
                rows.append(f"| {light} | {svc} | {err}% | {lat} ms | {rps} req/s |")
            sections.append(
                f"\n## SLO Scorecard\n| Status | Service | Error Rate | p99 Latency | Throughput |\n"
                f"|--------|---------|-----------|------------|------------|\n" + "\n".join(rows) + "\n"
            )
        alerts = data.get("alerts", {}).get("alerts", [])
        if alerts:
            sections.append(f"\n## Active Alerts: {len(alerts)} firing\n" +
                            "\n".join(f"- **{a.get('severity','').upper()}** {a.get('name','')} — {a.get('service','')} — {a.get('message','')[:80]}" for a in alerts) + "\n")

    elif checkout_type == "incident_review":
        alerts = data.get("alerts", {}).get("alerts", [])
        if alerts:
            rows = "\n".join(
                f"| {a.get('severity','').upper()} | {a.get('name','')} | {a.get('service','')} | {a.get('message','')[:80]} |"
                for a in alerts
            )
            sections.append(f"\n## Active Alerts ({len(alerts)})\n| Severity | Name | Service | Message |\n|----------|------|---------|----------|\n{rows}\n")
        deploys = data.get("deployments", {}).get("deployments", [])
        if deploys:
            rows = "\n".join(
                f"| {d.get('name','')} | {d.get('image_to','')} | {d.get('deployed_by','')} | {d.get('rollout_status','')} |"
                for d in deploys
            )
            sections.append(f"\n## Recent Deployments\n| Service | Image | Deployed By | Status |\n|---------|-------|------------|--------|\n{rows}\n")
        error_logs = data.get("error_logs", {})
        if error_logs:
            summary_rows = "\n".join(
                f"| {svc} | {logs.get('total_matches', 0)} | {logs.get('matches', [{}])[-1].get('msg','')[:80] if logs.get('matches') else '—'} |"
                for svc, logs in error_logs.items()
            )
            sections.append(f"\n## Error Log Summary\n| Service | Error Count (3d) | Latest Error |\n|---------|-----------------|------------|\n{summary_rows}\n")

    return "\n".join(sections)


# ── Email formatter ───────────────────────────────────────────────────────────

def _format_email_html(checkout: Checkout, report_md: str, status: str, run_date: str) -> str:
    emoji = _STATUS_EMOJI.get(status, "ℹ️")
    label = TYPE_LABELS.get(checkout.checkout_type, checkout.checkout_type)
    color = {"passed": "#22c55e", "warning": "#f59e0b", "failed": "#ef4444"}.get(status, "#6366f1")

    # Convert markdown tables to simple text for email
    body_text = report_md.replace("**", "").replace("##", "").replace("#", "").replace("|", " | ")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#0f1117; color:#e2e8f0; margin:0; padding:0; }}
  .container {{ max-width:720px; margin:0 auto; padding:24px; }}
  .header {{ background:#161b27; border:1px solid #1e2535; border-radius:12px; padding:24px; margin-bottom:20px; }}
  .status-badge {{ display:inline-block; padding:4px 12px; border-radius:999px; font-size:12px; font-weight:600; color:#fff; background:{color}; }}
  .section {{ background:#161b27; border:1px solid #1e2535; border-radius:8px; padding:16px; margin-bottom:12px; }}
  h1 {{ font-size:20px; color:#fff; margin:0 0 8px; }}
  h2 {{ font-size:14px; color:#94a3b8; margin:0 0 4px; text-transform:uppercase; letter-spacing:.05em; }}
  p {{ font-size:14px; color:#94a3b8; margin:0 0 8px; }}
  pre {{ background:#0b0e16; border:1px solid #1e2535; border-radius:6px; padding:12px; font-size:12px; color:#e2e8f0; white-space:pre-wrap; overflow-x:auto; }}
  .footer {{ text-align:center; font-size:11px; color:#475569; margin-top:20px; }}
</style></head><body>
<div class="container">
  <div class="header">
    <h1>{emoji} {checkout.name}</h1>
    <span class="status-badge">{status.upper()}</span>
    <p style="margin-top:8px;">{label} · {checkout.frequency.title()} · {checkout.namespace} · {run_date} UTC</p>
  </div>
  <div class="section">
    <pre>{body_text[:8000]}</pre>
  </div>
  <div class="footer">Generated by OpsBrain AI · <a href="http://localhost:3010" style="color:#6366f1;">View Dashboard</a></div>
</div></body></html>"""


# ── Main run entry point ───────────────────────────────────────────────────────

async def run_checkout(
    checkout: Checkout,
    claude,           # ClaudeClient — avoid circular import
    triggered_by: str = "scheduler",
) -> RunHistory:

    started_at = datetime.now(timezone.utc)
    run_id     = str(uuid.uuid4())
    run_date   = started_at.strftime("%Y-%m-%d %H:%M")

    run = RunHistory(
        id=run_id, checkout_id=checkout.id, checkout_name=checkout.name,
        checkout_type=checkout.checkout_type,
        started_at=started_at.isoformat(), completed_at=None,
        status=CheckoutStatus.running, summary="Running…",
        full_report="", duration_seconds=None,
        triggered_by=triggered_by, error=None,
    )
    save_run(run)

    try:
        # ── Route: compiled plan vs. full SOP analysis ────────────────────────
        if checkout.is_compiled and checkout.execution_plan:
            from checkouts.plan import CheckoutPlan, execute_plan
            plan = CheckoutPlan.from_dict(checkout.execution_plan)
            plan_result = await execute_plan(plan, checkout, claude)
            analysis = plan_result["analysis"]
            run.full_report = analysis.get("report_markdown", "")
            run_mode = f"compiled-plan ({plan_result['phases_used']['llm_calls']} LLM call, ~{checkout.tokens_saved_pct}% tokens saved)"
        else:
            # ── Full SOP analysis (first run or uncompiled) ───────────────────
            run_mode = "full-sop"
            gatherer = _GATHERERS.get(checkout.checkout_type, _gather_custom)
            data = await gatherer(checkout)
            prompt = _build_analysis_prompt(checkout, data)
            result = await claude.analyze(agent_type="sre", user_message=prompt)
            text = result.get("text", "{}").strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            try:
                analysis = json.loads(text)
            except Exception:
                analysis = {
                    "status": "warning",
                    "health_score": None,
                    "summary": "Checkout completed — manual review of data required.",
                    "key_findings": [],
                    "critical_issues": [],
                    "recommendations": [],
                    "analysis_narrative": result.get("text", ""),
                }

        raw_status = analysis.get("status", "warning")
        status = CheckoutStatus(raw_status) if raw_status in ("passed", "warning", "failed") else CheckoutStatus.warning
        summary = analysis.get("summary", "Checkout completed.")

        # ── Step 3: build report ──────────────────────────────────────────────
        if run.full_report:
            # Already set by compiled plan executor
            full_report = run.full_report
            run.full_report = ""   # reset — will be set properly below
        elif analysis.get("report_markdown"):
            full_report = analysis["report_markdown"]
        else:
            full_report = _render_report(checkout, {}, analysis, run_date)

        # ── Step 4: persist ───────────────────────────────────────────────────
        completed_at = datetime.now(timezone.utc)
        duration     = (completed_at - started_at).total_seconds()
        next_run     = compute_next_run(
            checkout.frequency, checkout.scheduled_hour,
            checkout.scheduled_weekday, checkout.scheduled_day,
            after=completed_at,
        )

        run.status           = status
        run.summary          = summary
        run.full_report      = full_report
        run.completed_at     = completed_at.isoformat()
        run.duration_seconds = duration
        save_run(run)
        update_checkout_after_run(checkout.id, status, summary, next_run.isoformat())

        # ── Step 5: notify ────────────────────────────────────────────────────
        await _notify(checkout, run, full_report)

    except Exception as exc:
        completed_at = datetime.now(timezone.utc)
        run.status           = CheckoutStatus.failed
        run.error            = str(exc)
        run.summary          = f"Checkout failed: {exc}"
        run.completed_at     = completed_at.isoformat()
        run.duration_seconds = (completed_at - started_at).total_seconds()
        save_run(run)
        next_run = compute_next_run(
            checkout.frequency, checkout.scheduled_hour,
            checkout.scheduled_weekday, checkout.scheduled_day,
            after=completed_at,
        )
        update_checkout_after_run(checkout.id, CheckoutStatus.failed, run.summary, next_run.isoformat())

    return run


async def _notify(checkout: Checkout, run: RunHistory, report_md: str) -> None:
    try:
        from connectors.registry import registry
        from connectors.base import ConnectorType

        label   = TYPE_LABELS.get(checkout.checkout_type, checkout.checkout_type)
        emoji   = _STATUS_EMOJI.get(run.status.value, "ℹ️")
        subject = f"{emoji} [{run.status.value.upper()}] {checkout.name} — {label} ({checkout.frequency})"
        run_date = run.started_at[:16].replace("T", " ")

        if checkout.audience_slack:
            for conn in registry.get_by_type(ConnectorType.SLACK)[:1]:
                for channel in checkout.audience_slack:
                    try:
                        msg = f"{subject}\n\n{run.summary}\n\n*Report generated:* {run_date} UTC"
                        await conn.send_notification(msg, channel=channel)
                    except Exception:
                        pass

        if checkout.audience_emails:
            for conn in registry.get_by_type(ConnectorType.EMAIL)[:1]:
                html_body = _format_email_html(checkout, report_md, run.status.value, run_date)
                for addr in checkout.audience_emails:
                    try:
                        await conn.send_email(addr, subject, html_body, html=True)
                    except Exception:
                        pass
    except Exception:
        pass  # notifications best-effort

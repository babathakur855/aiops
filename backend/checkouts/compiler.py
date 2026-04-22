"""
One-time checkout compiler.

Claude reads the SOP + report template from the Knowledge Base,
then generates a CheckoutPlan that encodes:
  - exact tool calls to make on every run
  - threshold rules for auto-detection of critical/warning findings
  - a short narrative_prompt (~200 words) used in place of the full SOP
  - a compact report template

After compilation the checkout runs WITHOUT reloading the SOP.
Token savings: ~78% per run (2k tokens vs 9k tokens).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from checkouts.models import Checkout
from checkouts.plan import CheckoutPlan, ToolStep

# All tools Claude may include in a plan
AVAILABLE_TOOLS_DOC = """
KUBERNETES TOOLS (connector: kubernetes)
  get_pod_status(namespace, label_selector?)          → pod list + summary
  get_pod_logs(namespace, pod_name, lines?, filter_errors?)
  get_recent_deployments(namespace, hours?)            → deployment events
  get_resource_usage(namespace, resource_type)         → resource_type: "pods"|"nodes"
  describe_service(namespace, service_name)
  get_hpa_status(namespace)                            → HPA list + scaling events

OBSERVABILITY TOOLS (connector: observability)
  query_metrics(service, metric, window_minutes?)
    metric options: latency_p99 | latency_p50 | error_rate | rps | memory_usage | cpu_usage
  query_logs(service, query, severity?, window_minutes?)
    severity options: ERROR | WARN | INFO | DEBUG | ALL
  get_service_dependencies(service, depth?)
  get_active_alerts(severity_filter?)                  → severity_filter: critical|warning|all

CLOUD / FINOPS TOOLS (connector: cloud)
  get_cloud_cost_breakdown(cloud?, group_by?, months?) → cloud: aws|azure|gcp|all
  get_underutilized_resources(resource_type?, utilization_threshold_pct?)
  get_rightsizing_recommendations(namespace?, min_savings_usd?)
  get_cost_anomalies(days?, threshold_pct?)

AWS CONNECTOR (connector: aws — only if AWS connector is configured)
  fetch_alerts()                  → CloudWatch alarms
  get_cost_breakdown(months?)     → real Cost Explorer data
  list_eks_clusters()             → EKS cluster list
"""


async def compile_checkout(
    checkout: Checkout,
    claude,  # ClaudeClient
) -> CheckoutPlan:
    """
    Call Claude ONCE to compile the checkout SOPs into an execution plan.
    The plan is saved and reused for all future runs.
    """
    from knowledge.store import get_docs_for_checkout

    # Load docs via Knowledge Set resolution (same logic as runner)
    from knowledge.set_store import resolve_set
    from knowledge.store import get_doc

    ks = resolve_set(checkout)
    sop_docs, template_docs, context_docs = [], [], []

    if ks:
        if ks.sop_doc_id:
            d = get_doc(ks.sop_doc_id)
            if d: sop_docs = [d]
        if ks.template_doc_id:
            d = get_doc(ks.template_doc_id)
            if d: template_docs = [d]
        for cid in ks.context_doc_ids:
            d = get_doc(cid)
            if d: context_docs.append(d)
    else:
        all_docs = get_docs_for_checkout(checkout.checkout_type)
        sop_docs      = [d for d in all_docs if d.doc_type == "sop"]
        template_docs = [d for d in all_docs if d.doc_type == "report_template"]
        context_docs  = [d for d in all_docs if d.doc_type == "context"]

    sop_text      = "\n\n---\n\n".join(f"# {d.name}\n{d.content}" for d in sop_docs)
    template_text = "\n\n---\n\n".join(f"# {d.name}\n{d.content}" for d in template_docs)
    context_text  = "\n\n---\n\n".join(f"# {d.name}\n{d.content}" for d in context_docs)

    doc_names = [d.name for d in sop_docs + template_docs + context_docs]

    compile_prompt = f"""You are a DevOps platform engineer compiling an automated checkout plan.

CHECKOUT TO COMPILE:
  Name:      {checkout.name}
  Type:      {checkout.checkout_type}
  Frequency: {checkout.frequency}
  Namespace: {checkout.namespace}
  Custom instructions: {checkout.custom_prompt or 'None'}

AVAILABLE DATA TOOLS (these are the ONLY sources of data):
{AVAILABLE_TOOLS_DOC}

{"SOP TO IMPLEMENT:" if sop_text else "No SOP — use engineering judgment."}
{sop_text}

{"REPORT FORMAT TO PRODUCE:" if template_text else ""}
{template_text}

{"ADDITIONAL CONTEXT:" if context_text else ""}
{context_text}

YOUR TASK:
Compile this SOP into a reusable execution plan so that:
1. Tool calls happen deterministically (no LLM reads the SOP again)
2. Threshold rules auto-detect obvious critical/warning conditions
3. A SHORT narrative_prompt encodes all analysis logic from the SOP (Claude reads THIS, not the SOP)
4. A compact report_template tells Claude exactly how to format output

The plan will run {checkout.frequency} WITHOUT reloading the SOP.
Make narrative_prompt self-contained and complete — it must capture ALL the analysis logic.

Return ONLY this JSON (no extra text):
{{
  "tool_steps": [
    {{
      "step": 1,
      "tool": "get_pod_status",
      "params": {{"namespace": "{{namespace}}"}},
      "purpose": "Check pod health — CrashLoopBackOff, OOMKilled, high restarts",
      "connector": "kubernetes"
    }}
  ],
  "thresholds": {{
    "critical": [
      "Any pod in CrashLoopBackOff status",
      "Any pod with OOMKilled status",
      "Any node with memory_pct > 90"
    ],
    "warning": [
      "Any pod with restart count > 10",
      "Any node with memory_pct > 80",
      "Any HPA with current_replicas / max_replicas > 0.8"
    ]
  }},
  "narrative_prompt": "You are analyzing {{frequency}} {checkout.checkout_type.replace('_',' ')} data for namespace {{namespace}}. [150-250 words that encode ALL the analysis logic, thresholds, interpretation rules, and health score formula from the SOP. This is what Claude reads every run instead of the SOP. Be specific with numbers.]",
  "report_template": "[Compact Markdown template max 1200 chars. Use {{date}}, {{namespace}}, {{frequency}}, {{STATUS}}, {{SCORE}} as placeholders. Include all required table headers. Claude fills in the actual data.]"
}}

Requirements:
- tool_steps: include only tools from the available list, in logical order. Use {{namespace}} placeholder in params where applicable.
- thresholds: plain-English rules that a Python script can match against tool output keys/values
- narrative_prompt: MUST encode ALL thresholds, health score formula, status rules, and any service-specific SLOs from the SOP. Claude will ONLY see this + the collected data at runtime.
- report_template: must have same section headers as the full template but be concise (Claude expands it with real data)
- connector field: "kubernetes" | "observability" | "cloud" | "aws"
"""

    result = await claude.analyze(agent_type="sre", user_message=compile_prompt)
    text = result.get("text", "{}").strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        # If JSON parse fails, extract with a fallback
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            raw = json.loads(match.group(0))
        else:
            raise ValueError(f"Claude returned non-JSON: {text[:500]}")

    # Build ToolStep objects
    tool_steps = [
        ToolStep(
            step=s.get("step", i + 1),
            tool=s["tool"],
            params=s.get("params", {}),
            purpose=s.get("purpose", ""),
            connector=s.get("connector", ""),
        )
        for i, s in enumerate(raw.get("tool_steps", []))
    ]

    plan = CheckoutPlan(
        version="1.0",
        compiled_at=datetime.now(timezone.utc).isoformat(),
        compiled_from=doc_names,
        tool_steps=tool_steps,
        thresholds=raw.get("thresholds", {"critical": [], "warning": []}),
        narrative_prompt=raw.get("narrative_prompt", ""),
        report_template=raw.get("report_template", ""),
        estimated_tokens_saved_pct=_estimate_savings(len(sop_text) + len(template_text), raw.get("narrative_prompt", "")),
    )

    return plan


def _estimate_savings(original_chars: int, narrative: str) -> int:
    """Estimate token savings percentage: 4 chars ≈ 1 token."""
    full_tokens  = original_chars // 4 + 2000   # SOP + template + data
    plan_tokens  = len(narrative) // 4 + 2000   # narrative + data
    if full_tokens == 0:
        return 0
    pct = int((1 - plan_tokens / full_tokens) * 100)
    return max(0, min(99, pct))

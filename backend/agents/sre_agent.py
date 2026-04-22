"""
AI-SRE Agent — incident triage, root cause analysis, and runbook generation.
Transparent extended thinking + auto-runbook generation.
"""
from __future__ import annotations

from core.claude_client import ClaudeClient
from tools import kubernetes_tools, observability_tools


ALL_TOOLS = kubernetes_tools.TOOL_DEFINITIONS + observability_tools.TOOL_DEFINITIONS


async def _tool_executor(tool_name: str, tool_input: dict) -> dict:
    if tool_name in {t["name"] for t in kubernetes_tools.TOOL_DEFINITIONS}:
        return await kubernetes_tools.execute(tool_name, tool_input)
    return await observability_tools.execute(tool_name, tool_input)


class SREAgent:
    def __init__(self, claude: ClaudeClient) -> None:
        self.claude = claude

    async def analyze_incident(
        self,
        alert_name: str,
        service: str,
        namespace: str,
        description: str,
        deep_analysis: bool = False,
    ) -> dict:
        """
        Full incident analysis with tool use.
        Set deep_analysis=True to use extended thinking for complex incidents.
        """
        prompt = f"""
INCIDENT ALERT: {alert_name}
Service: {service}
Namespace: {namespace}
Description: {description}

Please perform a complete root cause analysis for this incident. Use the available tools to:
1. Check pod status and recent restarts in namespace '{namespace}'
2. Fetch error logs from the affected service pods
3. Check for recent deployments that may have triggered this
4. Query error rate and latency metrics for '{service}'
5. Get service dependencies to understand blast radius
6. Check active alerts for related issues

After gathering data, provide:
- Severity assessment (P0/P1/P2/P3)
- Root cause (be specific — point to exact log lines, metric values, commits)
- Immediate remediation steps (numbered, copy-pasteable commands)
- A complete runbook in YAML format
- Post-mortem data points to collect
"""
        result = await self.claude.analyze_with_tools(
            agent_type="sre",
            user_message=prompt,
            tools=ALL_TOOLS,
            tool_executor=_tool_executor,
            use_thinking=deep_analysis,
        )
        return {
            "incident": {
                "alert": alert_name,
                "service": service,
                "namespace": namespace,
            },
            "analysis": result["text"],
            "thinking": result.get("thinking", ""),
            "tool_calls": result.get("tool_calls", []),
            "usage": result.get("usage", {}),
            "deep_analysis": deep_analysis,
        }

    async def generate_runbook(self, service: str, incident_type: str) -> dict:
        prompt = f"""
Generate a complete, production-ready runbook for:
Service: {service}
Incident Type: {incident_type}

The runbook must include:
1. Detection criteria (alert thresholds, log patterns)
2. Immediate triage steps (ordered, with expected outputs)
3. Diagnosis decision tree
4. Remediation procedures (with rollback steps)
5. Escalation path and criteria
6. Post-incident checklist

Format as YAML that can be stored in a GitOps repository.
"""
        result = await self.claude.analyze(agent_type="sre", user_message=prompt)
        return {"service": service, "incident_type": incident_type, "runbook": result["text"]}

    async def quick_triage(self, alert_payload: dict) -> dict:
        """Fast triage — no tools, instant severity + initial hypothesis."""
        prompt = f"""
Quick triage for this alert (respond in under 200 words):
{alert_payload}

Give me:
1. Severity (P0/P1/P2/P3) with justification
2. Most likely cause (1-2 sentences)
3. First 3 actions to take RIGHT NOW
"""
        result = await self.claude.analyze(agent_type="sre", user_message=prompt)
        return {"triage": result["text"], "usage": result.get("usage", {})}

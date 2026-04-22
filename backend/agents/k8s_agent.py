"""
AI-K8s Ops Agent — natural language Kubernetes operations and cluster management.
"""
from __future__ import annotations

from core.claude_client import ClaudeClient
from tools import kubernetes_tools, observability_tools


class K8sAgent:
    def __init__(self, claude: ClaudeClient) -> None:
        self.claude = claude

    async def natural_language_query(self, question: str, namespace: str = "production") -> dict:
        """
        Answer any Kubernetes question or execute an operation in natural language.
        Example: "Why are my pods restarting?" or "Scale payment-service to 5 replicas"
        """
        prompt = f"""
Kubernetes operation request for namespace '{namespace}':

"{question}"

Use the available tools to gather the necessary information, then:
1. Directly answer the question or explain what will happen
2. Provide the exact kubectl commands needed
3. If it's a write operation, include a --dry-run command first
4. Explain any risks or side effects
"""
        all_tools = kubernetes_tools.TOOL_DEFINITIONS + observability_tools.TOOL_DEFINITIONS

        async def tool_executor(tool_name: str, tool_input: dict) -> dict:
            if tool_name in {t["name"] for t in kubernetes_tools.TOOL_DEFINITIONS}:
                return await kubernetes_tools.execute(tool_name, tool_input)
            return await observability_tools.execute(tool_name, tool_input)

        result = await self.claude.analyze_with_tools(
            agent_type="k8s",
            user_message=prompt,
            tools=all_tools,
            tool_executor=tool_executor,
        )
        return {
            "question": question,
            "namespace": namespace,
            "answer": result["text"],
            "tool_calls": result.get("tool_calls", []),
        }

    async def cluster_health_report(self, namespace: str = "production") -> dict:
        prompt = f"""
Generate a comprehensive cluster health report for namespace '{namespace}'.

Use tools to check:
1. Pod status and any problematic pods
2. Resource usage for pods and nodes
3. HPA status and scaling activity
4. Active alerts

Produce a structured health report with:
- Overall health score (0-100) with reasoning
- Critical issues (if any)
- Warning items
- Resource utilization summary
- Capacity forecast (will we run out of resources at current growth?)
- Top 3 recommended actions
"""

        async def tool_executor(tool_name: str, tool_input: dict) -> dict:
            if tool_name in {t["name"] for t in kubernetes_tools.TOOL_DEFINITIONS}:
                return await kubernetes_tools.execute(tool_name, tool_input)
            return await observability_tools.execute(tool_name, tool_input)

        all_tools = kubernetes_tools.TOOL_DEFINITIONS + observability_tools.TOOL_DEFINITIONS
        result = await self.claude.analyze_with_tools(
            agent_type="k8s",
            user_message=prompt,
            tools=all_tools,
            tool_executor=tool_executor,
        )
        return {"namespace": namespace, "report": result["text"], "tool_calls": result.get("tool_calls", [])}

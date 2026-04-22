"""
AI-FinOps Agent — cloud cost analysis, waste detection, and optimization PRs.
"""
from __future__ import annotations

from core.claude_client import ClaudeClient
from tools import cloud_tools


class FinOpsAgent:
    def __init__(self, claude: ClaudeClient) -> None:
        self.claude = claude

    async def analyze_costs(self, cloud: str = "all") -> dict:
        prompt = f"""
Perform a comprehensive cloud cost optimization analysis for cloud: {cloud}.

Use the available tools to:
1. Get the full cost breakdown by service
2. Identify underutilized resources
3. Get pod rightsizing recommendations
4. Detect any cost anomalies

Then provide:
- Executive summary: total monthly spend and MoM change
- Top 5 cost optimization opportunities ranked by savings (with $ amounts)
- For each opportunity: implementation steps, effort level (Low/Med/High), risk (Low/Med/High)
- Generate YAML patches for any Kubernetes rightsizing recommendations
- Estimated total monthly savings achievable
- Prioritized 30-day action plan
"""

        async def tool_executor(tool_name: str, tool_input: dict) -> dict:
            return await cloud_tools.execute(tool_name, tool_input)

        result = await self.claude.analyze_with_tools(
            agent_type="finops",
            user_message=prompt,
            tools=cloud_tools.TOOL_DEFINITIONS,
            tool_executor=tool_executor,
        )
        return {
            "analysis": result["text"],
            "tool_calls": result.get("tool_calls", []),
            "usage": result.get("usage", {}),
        }

    async def estimate_savings(self, description: str) -> dict:
        """Quick savings estimate from a plain-English description."""
        prompt = f"""
Estimate cloud cost savings for this scenario:
{description}

Provide: estimated monthly savings ($), implementation complexity, and key risks.
Keep the response concise (under 150 words).
"""
        result = await self.claude.analyze(agent_type="finops", user_message=prompt)
        return {"estimate": result["text"]}

    async def generate_rightsizing_pr(self, namespace: str) -> dict:
        """Generate a complete PR description + YAML for pod rightsizing."""
        prompt = f"""
Generate a complete GitHub Pull Request for Kubernetes pod rightsizing in namespace: {namespace}.

The PR should include:
1. PR title and description
2. Complete YAML patches for each workload (as HelmValues or direct manifest patches)
3. Testing/validation steps
4. Expected cost savings per workload
5. Rollback procedure

Format as a ready-to-open GitHub PR with markdown description and attached YAML files.
"""

        async def tool_executor(tool_name: str, tool_input: dict) -> dict:
            return await cloud_tools.execute(tool_name, tool_input)

        result = await self.claude.analyze_with_tools(
            agent_type="finops",
            user_message=prompt,
            tools=[t for t in cloud_tools.TOOL_DEFINITIONS if "rightsizing" in t["name"]],
            tool_executor=tool_executor,
        )
        return {"pr_content": result["text"], "namespace": namespace}

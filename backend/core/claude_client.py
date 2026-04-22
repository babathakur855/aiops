"""
Claude client with prompt caching, extended thinking, tool use, and streaming.
Claude client with prompt caching, extended thinking, tool use, and streaming.
"""
from __future__ import annotations

import os
from typing import Any, AsyncGenerator

import anthropic
from anthropic import AsyncAnthropic

MODEL = "claude-sonnet-4-6"
MODEL_THINKING = "claude-opus-4-7"  # Use Opus for deep extended thinking


class ClaudeClient:
    def __init__(self) -> None:
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = MODEL
        self._usage_log: list[dict] = []

    # ------------------------------------------------------------------
    # Cached system prompt blocks (saves tokens on repeated calls)
    # ------------------------------------------------------------------

    def _sre_system(self) -> list[dict]:
        return [
            {
                "type": "text",
                "text": (
                    "You are OpsBrain's AI-SRE — an expert Site Reliability Engineer "
                    "with deep expertise in Kubernetes, distributed systems, cloud infrastructure, "
                    "and incident management. Your job is to perform root cause analysis (RCA), "
                    "triage alerts, suggest actionable fixes, and generate runbooks.\n\n"
                    "Principles:\n"
                    "- Be specific: reference exact pod names, namespaces, timestamps, metric values.\n"
                    "- Prioritise safety: always show the blast radius before recommending changes.\n"
                    "- Explain WHY, not just WHAT.\n"
                    "- When unsure, say so and provide investigative next steps.\n"
                    "- Generate YAML manifests or kubectl commands that are directly copy-pasteable.\n"
                    "- Always assess severity: P0 (SEV1), P1 (SEV2), P2 (SEV3), P3 (SEV4)."
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _finops_system(self) -> list[dict]:
        return [
            {
                "type": "text",
                "text": (
                    "You are OpsBrain's AI-FinOps — a cloud cost optimization expert. "
                    "You analyze cloud spend, identify waste, and generate cost-saving action plans "
                    "with specific dollar amounts and implementation steps.\n\n"
                    "Principles:\n"
                    "- Always quantify savings in $/month.\n"
                    "- Rank recommendations by ROI (highest savings first).\n"
                    "- Include implementation complexity (low/medium/high) and risk level.\n"
                    "- Generate PRs/YAML patches for rightsizing where applicable.\n"
                    "- Consider reserved instances, spot instances, and scheduling opportunities."
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _k8s_system(self) -> list[dict]:
        return [
            {
                "type": "text",
                "text": (
                    "You are OpsBrain's AI-K8s Ops assistant — a Kubernetes expert. "
                    "You translate natural language into precise kubectl commands, Helm operations, "
                    "and Kubernetes manifests. You perform cluster health analysis, upgrade planning, "
                    "and capacity management.\n\n"
                    "Principles:\n"
                    "- Always validate commands before suggesting them.\n"
                    "- Include --dry-run flags for destructive operations.\n"
                    "- Explain the impact of each command.\n"
                    "- Suggest RBAC-safe approaches.\n"
                    "- Provide rollback procedures alongside changes."
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _postmortem_system(self) -> list[dict]:
        return [
            {
                "type": "text",
                "text": (
                    "You are OpsBrain's Post-Mortem Generator — you create blameless, thorough "
                    "incident post-mortems following Google SRE and Atlassian best practices.\n\n"
                    "Format every post-mortem with:\n"
                    "1. Executive Summary (2-3 sentences)\n"
                    "2. Impact (users affected, revenue impact, duration)\n"
                    "3. Timeline (minute-by-minute with UTC timestamps)\n"
                    "4. Root Cause (5-whys analysis)\n"
                    "5. Contributing Factors\n"
                    "6. What Went Well\n"
                    "7. What Went Wrong\n"
                    "8. Action Items (with owner, priority, and deadline)\n"
                    "9. Detection & Alerting Improvements\n\n"
                    "Tone: blameless, factual, focused on systems not individuals."
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]

    # ------------------------------------------------------------------
    # Core analysis methods
    # ------------------------------------------------------------------

    async def analyze(
        self,
        agent_type: str,
        user_message: str,
        tools: list[dict] | None = None,
        use_thinking: bool = False,
    ) -> dict[str, Any]:
        """Standard analysis — returns full response dict."""
        system_map = {
            "sre": self._sre_system,
            "finops": self._finops_system,
            "k8s": self._k8s_system,
            "postmortem": self._postmortem_system,
        }
        system = system_map.get(agent_type, self._sre_system)()

        kwargs: dict[str, Any] = {
            "model": MODEL_THINKING if use_thinking else self.model,
            "max_tokens": 16000,
            "system": system,
            "messages": [{"role": "user", "content": user_message}],
        }

        if use_thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 8000}

        if tools:
            kwargs["tools"] = tools

        response = await self.client.messages.create(**kwargs)
        self._log_usage(response.usage, agent_type)
        return self._parse_response(response)

    async def analyze_with_tools(
        self,
        agent_type: str,
        user_message: str,
        tools: list[dict],
        tool_executor: Any,
        use_thinking: bool = False,
        max_turns: int = 10,
        system_override: str | None = None,
    ) -> dict[str, Any]:
        """Agentic loop — calls tools and continues until final answer."""
        system_map = {
            "sre": self._sre_system,
            "finops": self._finops_system,
            "k8s": self._k8s_system,
        }
        if system_override:
            system = [{"type": "text", "text": system_override, "cache_control": {"type": "ephemeral"}}]
        else:
            system = system_map.get(agent_type, self._sre_system)()
        messages: list[dict] = [{"role": "user", "content": user_message}]
        tool_calls_log: list[dict] = []

        for _ in range(max_turns):
            kwargs: dict[str, Any] = {
                "model": MODEL_THINKING if use_thinking else self.model,
                "max_tokens": 16000,
                "system": system,
                "messages": messages,
                "tools": tools,
            }
            if use_thinking:
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": 8000}

            response = await self.client.messages.create(**kwargs)
            self._log_usage(response.usage, agent_type)

            if response.stop_reason == "end_turn":
                return {**self._parse_response(response), "tool_calls": tool_calls_log}

            if response.stop_reason == "tool_use":
                tool_uses = [b for b in response.content if b.type == "tool_use"]
                tool_results = []
                for tool_use in tool_uses:
                    result = await tool_executor(tool_use.name, tool_use.input)
                    tool_calls_log.append(
                        {"tool": tool_use.name, "input": tool_use.input, "result": result}
                    )
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": tool_use.id, "content": str(result)}
                    )
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                continue

            break

        return self._parse_response(response)

    async def stream(
        self,
        agent_type: str,
        user_message: str,
        use_thinking: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens as Server-Sent Events for real-time UI updates."""
        system_map = {
            "sre": self._sre_system,
            "finops": self._finops_system,
            "k8s": self._k8s_system,
            "postmortem": self._postmortem_system,
        }
        system = system_map.get(agent_type, self._sre_system)()

        kwargs: dict[str, Any] = {
            "model": MODEL_THINKING if use_thinking else self.model,
            "max_tokens": 16000,
            "system": system,
            "messages": [{"role": "user", "content": user_message}],
        }
        if use_thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 8000}

        async with self.client.messages.stream(**kwargs) as stream_ctx:
            async for event in stream_ctx:
                if hasattr(event, "type"):
                    if event.type == "content_block_start":
                        if hasattr(event, "content_block"):
                            if event.content_block.type == "thinking":
                                yield f"data: {{'type':'thinking_start'}}\n\n"
                            elif event.content_block.type == "text":
                                yield f"data: {{'type':'text_start'}}\n\n"
                    elif event.type == "content_block_delta":
                        if hasattr(event, "delta"):
                            if event.delta.type == "thinking_delta":
                                chunk = event.delta.thinking.replace('"', '\\"').replace("\n", "\\n")
                                yield f'data: {{"type":"thinking","text":"{chunk}"}}\n\n'
                            elif event.delta.type == "text_delta":
                                chunk = event.delta.text.replace('"', '\\"').replace("\n", "\\n")
                                yield f'data: {{"type":"text","text":"{chunk}"}}\n\n'
                    elif event.type == "message_stop":
                        yield "data: [DONE]\n\n"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_response(self, response: anthropic.types.Message) -> dict[str, Any]:
        text_blocks = []
        thinking_blocks = []
        for block in response.content:
            if hasattr(block, "type"):
                if block.type == "text":
                    text_blocks.append(block.text)
                elif block.type == "thinking":
                    thinking_blocks.append(block.thinking)
        return {
            "text": "\n".join(text_blocks),
            "thinking": "\n".join(thinking_blocks),
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
                "cache_creation_input_tokens": getattr(
                    response.usage, "cache_creation_input_tokens", 0
                ),
            },
        }

    def _log_usage(self, usage: Any, agent_type: str) -> None:
        self._usage_log.append(
            {
                "agent": agent_type,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read": getattr(usage, "cache_read_input_tokens", 0),
            }
        )

    def get_usage_summary(self) -> dict:
        total_input = sum(u["input_tokens"] for u in self._usage_log)
        total_output = sum(u["output_tokens"] for u in self._usage_log)
        total_cache_read = sum(u["cache_read"] for u in self._usage_log)
        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cache_read_tokens": total_cache_read,
            "estimated_cost_usd": round(
                (total_input * 3 / 1_000_000) + (total_output * 15 / 1_000_000), 4
            ),
            "calls": len(self._usage_log),
        }

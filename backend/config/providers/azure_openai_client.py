"""
Azure OpenAI client — for air-gapped / private endpoint deployments.
Traffic stays inside the customer's Azure network.
"""
from __future__ import annotations

from typing import Any, AsyncGenerator
from config.settings import settings


class AzureOpenAIClient:
    """
    Wraps Azure OpenAI with the same interface as ClaudeClient.
    Use this when LLM_PROVIDER=azure_openai.
    """

    def __init__(self) -> None:
        try:
            from openai import AsyncAzureOpenAI
        except ImportError:
            raise ImportError("Install openai package: pip install openai")

        self._client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
        self.deployment = settings.azure_openai_deployment

    def _system_prompt(self, agent_type: str) -> str:
        prompts = {
            "sre": "You are an expert Site Reliability Engineer performing root cause analysis.",
            "finops": "You are a cloud cost optimization expert identifying waste and savings.",
            "k8s": "You are a Kubernetes expert helping with cluster operations.",
            "postmortem": "You generate blameless post-mortems following Google SRE best practices.",
        }
        return prompts.get(agent_type, prompts["sre"])

    async def analyze(self, agent_type: str, user_message: str, tools=None, use_thinking: bool = False) -> dict:
        messages = [
            {"role": "system", "content": self._system_prompt(agent_type)},
            {"role": "user", "content": user_message},
        ]
        kwargs: dict[str, Any] = {
            "model": self.deployment,
            "messages": messages,
            "max_tokens": 4096,
        }
        if tools:
            kwargs["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"],
                "parameters": t["input_schema"],
            }} for t in tools]

        response = await self._client.chat.completions.create(**kwargs)
        return {
            "text": response.choices[0].message.content or "",
            "thinking": "",
            "stop_reason": response.choices[0].finish_reason,
            "usage": {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            },
        }

    async def analyze_with_tools(self, agent_type, user_message, tools, tool_executor, use_thinking=False, max_turns=10):
        # Simplified — delegates to analyze for now
        return await self.analyze(agent_type, user_message, tools, use_thinking)

    async def stream(self, agent_type: str, user_message: str, use_thinking: bool = False) -> AsyncGenerator[str, None]:
        messages = [
            {"role": "system", "content": self._system_prompt(agent_type)},
            {"role": "user", "content": user_message},
        ]
        async with await self._client.chat.completions.create(
            model=self.deployment, messages=messages, max_tokens=4096, stream=True
        ) as stream:
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content.replace('"', '\\"').replace("\n", "\\n")
                    yield f'data: {{"type":"text","text":"{text}"}}\n\n'
        yield "data: [DONE]\n\n"

    def get_usage_summary(self) -> dict:
        return {"provider": "azure_openai", "deployment": self.deployment}

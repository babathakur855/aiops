"""
Ollama client — fully air-gapped, self-hosted LLM (Llama, Mistral, etc.)
For environments with zero external internet access.
"""
from __future__ import annotations

from typing import Any, AsyncGenerator
import httpx
from config.settings import settings


class OllamaClient:
    """
    Wraps Ollama API with the same interface as ClaudeClient.
    Use this when LLM_PROVIDER=ollama.
    Deploy Ollama as a sidecar or service in the same namespace.
    """

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model

    def _system_prompt(self, agent_type: str) -> str:
        prompts = {
            "sre": "You are an expert SRE. Perform detailed root cause analysis with specific commands.",
            "finops": "You are a cloud cost optimization expert. Quantify savings in dollar amounts.",
            "k8s": "You are a Kubernetes expert. Provide exact kubectl commands.",
            "postmortem": "You write blameless post-mortems following Google SRE practices.",
        }
        return prompts.get(agent_type, prompts["sre"])

    async def analyze(self, agent_type: str, user_message: str, tools=None, use_thinking: bool = False) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system_prompt(agent_type)},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("message", {}).get("content", "")
            return {
                "text": text,
                "thinking": "",
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": data.get("prompt_eval_count", 0),
                    "output_tokens": data.get("eval_count", 0),
                },
            }

    async def analyze_with_tools(self, agent_type, user_message, tools, tool_executor, use_thinking=False, max_turns=10):
        return await self.analyze(agent_type, user_message)

    async def stream(self, agent_type: str, user_message: str, use_thinking: bool = False) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system_prompt(agent_type)},
                {"role": "user", "content": user_message},
            ],
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json
                        try:
                            data = json.loads(line)
                            text = data.get("message", {}).get("content", "")
                            if text:
                                text = text.replace('"', '\\"').replace("\n", "\\n")
                                yield f'data: {{"type":"text","text":"{text}"}}\n\n'
                            if data.get("done"):
                                yield "data: [DONE]\n\n"
                        except Exception:
                            continue

    def get_usage_summary(self) -> dict:
        return {"provider": "ollama", "model": self.model, "base_url": self.base_url}

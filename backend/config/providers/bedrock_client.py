"""
AWS Bedrock client — Claude via AWS. Traffic stays within AWS VPC.
Use VPC endpoints so no data leaves the customer network.
"""
from __future__ import annotations

from typing import Any, AsyncGenerator
import json
from config.settings import settings


class BedrockClient:
    """
    Wraps AWS Bedrock with the same interface as ClaudeClient.
    Use this when LLM_PROVIDER=aws_bedrock.
    """

    def __init__(self) -> None:
        try:
            import boto3
        except ImportError:
            raise ImportError("Install boto3: pip install boto3")

        session_kwargs: dict[str, Any] = {"region_name": settings.aws_bedrock_region}
        if settings.aws_access_key_id:
            session_kwargs["aws_access_key_id"] = settings.aws_access_key_id
            session_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

        import boto3
        self._client = boto3.client("bedrock-runtime", **session_kwargs)
        self.model_id = settings.aws_bedrock_model_id

    def _system_prompt(self, agent_type: str) -> str:
        prompts = {
            "sre": "You are an expert SRE performing root cause analysis.",
            "finops": "You are a cloud cost optimization expert.",
            "k8s": "You are a Kubernetes operations expert.",
            "postmortem": "You generate blameless post-mortems.",
        }
        return prompts.get(agent_type, prompts["sre"])

    async def analyze(self, agent_type: str, user_message: str, tools=None, use_thinking: bool = False) -> dict:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": self._system_prompt(agent_type),
            "messages": [{"role": "user", "content": user_message}],
        }
        response = self._client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
        )
        result = json.loads(response["body"].read())
        text = "".join(b.get("text", "") for b in result.get("content", []) if b.get("type") == "text")
        return {
            "text": text,
            "thinking": "",
            "stop_reason": result.get("stop_reason"),
            "usage": {
                "input_tokens": result.get("usage", {}).get("input_tokens", 0),
                "output_tokens": result.get("usage", {}).get("output_tokens", 0),
            },
        }

    async def analyze_with_tools(self, agent_type, user_message, tools, tool_executor, use_thinking=False, max_turns=10):
        return await self.analyze(agent_type, user_message)

    async def stream(self, agent_type: str, user_message: str, use_thinking: bool = False) -> AsyncGenerator[str, None]:
        result = await self.analyze(agent_type, user_message)
        text = result["text"].replace('"', '\\"').replace("\n", "\\n")
        yield f'data: {{"type":"text","text":"{text}"}}\n\n'
        yield "data: [DONE]\n\n"

    def get_usage_summary(self) -> dict:
        return {"provider": "aws_bedrock", "model_id": self.model_id}

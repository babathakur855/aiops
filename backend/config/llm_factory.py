"""
LLM provider factory — returns a unified client regardless of provider.
Supports: Anthropic (direct), Azure OpenAI, AWS Bedrock, Ollama (air-gapped).
"""
from __future__ import annotations

from config.settings import LLMProvider, settings


def get_llm_client():
    """Return the configured LLM client based on LLM_PROVIDER env var."""
    provider = settings.llm_provider

    if provider == LLMProvider.ANTHROPIC:
        from core.claude_client import ClaudeClient
        return ClaudeClient()

    if provider == LLMProvider.AZURE_OPENAI:
        from config.providers.azure_openai_client import AzureOpenAIClient
        return AzureOpenAIClient()

    if provider == LLMProvider.AWS_BEDROCK:
        from config.providers.bedrock_client import BedrockClient
        return BedrockClient()

    if provider == LLMProvider.OLLAMA:
        from config.providers.ollama_client import OllamaClient
        return OllamaClient()

    raise ValueError(f"Unknown LLM provider: {provider}")

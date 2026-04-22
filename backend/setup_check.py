"""
Pre-flight checks — verify the LLM is reachable before the app is usable.
Called by /health and /setup/status endpoints.
"""
from __future__ import annotations

import os
from config.settings import settings, LLMProvider


async def check_llm() -> dict:
    """Test the configured LLM provider. Returns {ok, provider, model, error}."""
    provider = settings.llm_provider
    try:
        if provider == LLMProvider.ANTHROPIC:
            return await _check_anthropic()
        if provider == LLMProvider.AZURE_OPENAI:
            return await _check_azure_openai()
        if provider == LLMProvider.AWS_BEDROCK:
            return await _check_bedrock()
        if provider == LLMProvider.OLLAMA:
            return await _check_ollama()
        return {"ok": False, "provider": str(provider), "error": f"Unknown provider: {provider}"}
    except Exception as e:
        return {"ok": False, "provider": str(provider), "error": str(e)}


async def _check_anthropic() -> dict:
    if not settings.anthropic_api_key:
        return {"ok": False, "provider": "anthropic", "error": "ANTHROPIC_API_KEY not set"}
    try:
        import asyncio
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=5,
            messages=[{"role": "user", "content": "OK"}],
        )
        return {"ok": True, "provider": "anthropic", "model": settings.anthropic_model}
    except Exception as e:
        return {"ok": False, "provider": "anthropic", "error": str(e)}


async def _check_azure_openai() -> dict:
    if not settings.azure_openai_endpoint:
        return {"ok": False, "provider": "azure_openai", "error": "AZURE_OPENAI_ENDPOINT not set"}
    try:
        import asyncio
        from openai import AsyncAzureOpenAI
        client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key or None,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
        resp = await client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[{"role": "user", "content": "OK"}],
            max_tokens=5,
        )
        return {"ok": True, "provider": "azure_openai", "model": settings.azure_openai_deployment}
    except Exception as e:
        return {"ok": False, "provider": "azure_openai", "error": str(e)}


async def _check_bedrock() -> dict:
    try:
        import asyncio, boto3, json
        kwargs: dict = {"region_name": settings.aws_bedrock_region}
        if settings.aws_access_key_id:
            kwargs["aws_access_key_id"]     = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        client = boto3.client("bedrock-runtime", **kwargs)
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "OK"}],
        })
        await asyncio.to_thread(
            client.invoke_model,
            modelId=settings.aws_bedrock_model_id,
            body=body, contentType="application/json",
        )
        return {"ok": True, "provider": "aws_bedrock", "model": settings.aws_bedrock_model_id}
    except Exception as e:
        return {"ok": False, "provider": "aws_bedrock", "error": str(e)}


async def _check_ollama() -> dict:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                model_found = settings.ollama_model in models
                return {
                    "ok": model_found,
                    "provider": "ollama",
                    "model": settings.ollama_model,
                    "available_models": models,
                    "error": None if model_found else f"Model '{settings.ollama_model}' not pulled. Run: ollama pull {settings.ollama_model}",
                }
            return {"ok": False, "provider": "ollama", "error": f"Ollama returned {r.status_code}"}
    except Exception as e:
        return {"ok": False, "provider": "ollama", "error": f"Cannot reach Ollama at {settings.ollama_base_url}: {e}"}


def get_setup_requirements() -> dict:
    """Return what's missing from the current configuration."""
    issues = []
    provider = settings.llm_provider

    if provider == LLMProvider.ANTHROPIC and not settings.anthropic_api_key:
        issues.append("ANTHROPIC_API_KEY is not set")
    if provider == LLMProvider.AZURE_OPENAI and not settings.azure_openai_endpoint:
        issues.append("AZURE_OPENAI_ENDPOINT is not set")
    if provider == LLMProvider.AZURE_OPENAI and not settings.azure_openai_api_key:
        issues.append("AZURE_OPENAI_API_KEY is not set (or use Managed Identity)")
    if provider == LLMProvider.OLLAMA and not settings.ollama_base_url:
        issues.append("OLLAMA_BASE_URL is not set")

    return {
        "configured": len(issues) == 0,
        "provider": str(provider.value),
        "issues": issues,
        "setup_command": "python setup.py  (or ./setup.sh on Linux/Mac, .\\setup.ps1 on Windows)",
    }

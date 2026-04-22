"""
Unified configuration — reads from environment variables.
Supports any deployment: AWS, Azure, on-prem, air-gapped.
"""
from __future__ import annotations

from enum import Enum
from pydantic_settings import BaseSettings
from pydantic import Field


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    AWS_BEDROCK = "aws_bedrock"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────
    app_env: str = Field("development", alias="APP_ENV")
    app_secret_key: str = Field("change-me", alias="APP_SECRET_KEY")
    jwt_secret_key: str = Field("change-me-jwt", alias="JWT_SECRET_KEY")
    jwt_expire_minutes: int = Field(480, alias="JWT_EXPIRE_MINUTES")
    cors_origins: list[str] = Field(["*"], alias="CORS_ORIGINS")

    # ── LLM Provider ──────────────────────────────────────────
    llm_provider: LLMProvider = Field(LLMProvider.ANTHROPIC, alias="LLM_PROVIDER")

    # Anthropic (default)
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field("claude-sonnet-4-6", alias="ANTHROPIC_MODEL")

    # Azure OpenAI (air-gapped / private endpoint)
    azure_openai_api_key: str = Field("", alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str = Field("", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_deployment: str = Field("gpt-4o", alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = Field("2024-02-01", alias="AZURE_OPENAI_API_VERSION")

    # AWS Bedrock (Claude via AWS)
    aws_bedrock_region: str = Field("us-east-1", alias="AWS_BEDROCK_REGION")
    aws_bedrock_model_id: str = Field(
        "anthropic.claude-3-5-sonnet-20241022-v2:0", alias="AWS_BEDROCK_MODEL_ID"
    )
    aws_access_key_id: str = Field("", alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field("", alias="AWS_SECRET_ACCESS_KEY")

    # Ollama (fully air-gapped, self-hosted)
    ollama_base_url: str = Field("http://ollama:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field("llama3.1:70b", alias="OLLAMA_MODEL")

    # ── Connector defaults (can also be set per-connector at runtime) ──
    snow_instance_url: str = Field("", alias="SNOW_INSTANCE_URL")
    snow_username: str = Field("", alias="SNOW_USERNAME")
    snow_password: str = Field("", alias="SNOW_PASSWORD")
    snow_client_id: str = Field("", alias="SNOW_CLIENT_ID")
    snow_client_secret: str = Field("", alias="SNOW_CLIENT_SECRET")

    confluence_base_url: str = Field("", alias="CONFLUENCE_BASE_URL")
    confluence_username: str = Field("", alias="CONFLUENCE_USERNAME")
    confluence_api_token: str = Field("", alias="CONFLUENCE_API_TOKEN")

    dynatrace_base_url: str = Field("", alias="DYNATRACE_BASE_URL")
    dynatrace_api_token: str = Field("", alias="DYNATRACE_API_TOKEN")

    elasticsearch_url: str = Field("", alias="ELASTICSEARCH_URL")
    elasticsearch_api_key: str = Field("", alias="ELASTICSEARCH_API_KEY")
    elasticsearch_username: str = Field("", alias="ELASTICSEARCH_USERNAME")
    elasticsearch_password: str = Field("", alias="ELASTICSEARCH_PASSWORD")

    smtp_host: str = Field("", alias="SMTP_HOST")
    smtp_port: int = Field(587, alias="SMTP_PORT")
    smtp_username: str = Field("", alias="SMTP_USERNAME")
    smtp_password: str = Field("", alias="SMTP_PASSWORD")
    smtp_from_email: str = Field("", alias="SMTP_FROM_EMAIL")

    slack_webhook_url: str = Field("", alias="SLACK_WEBHOOK_URL")
    slack_bot_token: str = Field("", alias="SLACK_BOT_TOKEN")

    teams_webhook_url: str = Field("", alias="TEAMS_WEBHOOK_URL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        populate_by_name = True


settings = Settings()

#!/usr/bin/env python3
"""
OpsBrain Installation Wizard
==============================
Run this BEFORE starting the application.
It configures your LLM provider, tests connectivity, writes .env, and optionally starts OpsBrain.

Usage:
  python setup.py            # interactive setup
  python setup.py --check    # verify existing .env without changing anything
  python setup.py --start    # setup + start docker-compose
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

# ─── Terminal colours (no external dependencies) ─────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
DIM    = "\033[2m"

def c(text: str, colour: str) -> str:
    return f"{colour}{text}{RESET}"

def ok(msg: str)   -> None: print(c(f"  ✓  {msg}", GREEN))
def err(msg: str)  -> None: print(c(f"  ✗  {msg}", RED))
def warn(msg: str) -> None: print(c(f"  ⚠  {msg}", YELLOW))
def info(msg: str) -> None: print(c(f"  →  {msg}", CYAN))
def step(n: int, title: str) -> None:
    print(f"\n{BOLD}{BLUE}Step {n}: {title}{RESET}")
    print(c("─" * 50, DIM))

def prompt(label: str, default: str = "", secret: bool = False) -> str:
    display_default = f" [{DIM}{'••••' if secret and default else default}{RESET}]" if default else ""
    prompt_str = f"  {BOLD}{label}{RESET}{display_default}: "
    if secret:
        import getpass
        val = getpass.getpass(prompt_str)
        return val if val else default
    val = input(prompt_str).strip()
    return val if val else default

def choose(label: str, options: list[tuple[str, str]], default: int = 1) -> str:
    print(f"\n  {BOLD}{label}{RESET}")
    for i, (key, desc) in enumerate(options, 1):
        marker = c(f"  [{i}]", CYAN)
        print(f"{marker} {BOLD}{key}{RESET} — {desc}")
    while True:
        raw = input(f"\n  Enter choice [{DIM}1-{len(options)}, default {default}{RESET}]: ").strip()
        if not raw:
            return options[default - 1][0]
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
        except ValueError:
            pass
        warn("Invalid choice — enter a number")

def banner() -> None:
    print(c("""
╔══════════════════════════════════════════════════════════╗
║              OpsBrain Installation Wizard                ║
║          AI-Native AIOps Platform — Setup                ║
╚══════════════════════════════════════════════════════════╝
""", CYAN))
    print(c("  This wizard will:", DIM))
    print(c("  1. Configure your LLM provider (required before first start)", DIM))
    print(c("  2. Test the LLM connection", DIM))
    print(c("  3. Set up auth secrets", DIM))
    print(c("  4. Write .env file", DIM))
    print(c("  5. Optionally start OpsBrain\n", DIM))


# ─── LLM provider configurations ─────────────────────────────────

LLM_PROVIDERS = [
    ("anthropic",    "Anthropic (Claude API — direct, recommended for dev)"),
    ("aws_bedrock",  "AWS Bedrock (Claude via AWS — stays inside AWS network)"),
    ("azure_openai", "Azure OpenAI (GPT-4o — stays inside Azure network, air-gap ready)"),
    ("gcp_vertex",   "GCP Vertex AI (Gemini — stays inside GCP network)"),
    ("ollama",       "Ollama (fully self-hosted, zero internet, air-gapped)"),
]

def configure_anthropic(env: dict) -> bool:
    print(c("""
  Anthropic Setup:
  ─────────────────
  Get your API key at: https://console.anthropic.com/settings/keys
  Key format: sk-ant-api03-...
""", DIM))
    key = prompt("Anthropic API Key", secret=True)
    if not key.startswith("sk-ant-"):
        warn("Key doesn't look like an Anthropic key (expected sk-ant-...) — continuing anyway")
    model = choose("Model", [
        ("claude-sonnet-4-6", "Claude Sonnet 4.6 — best balance of speed and quality"),
        ("claude-opus-4-7",   "Claude Opus 4.7 — most capable, slower"),
        ("claude-haiku-4-5-20251001", "Claude Haiku 4.5 — fastest, cheapest"),
    ])
    env["ANTHROPIC_API_KEY"] = key
    env["ANTHROPIC_MODEL"]   = model
    env["LLM_PROVIDER"]      = "anthropic"
    return _test_anthropic(key, model)

def _test_anthropic(key: str, model: str) -> bool:
    info("Testing Anthropic connection…")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "Reply with OK"}],
        )
        ok(f"Anthropic connected — model: {model}")
        return True
    except ImportError:
        warn("anthropic package not installed — run: pip install anthropic")
        return False
    except Exception as e:
        err(f"Anthropic connection failed: {e}")
        return False

def configure_bedrock(env: dict) -> bool:
    print(c("""
  AWS Bedrock Setup:
  ──────────────────
  Bedrock keeps all AI traffic inside your AWS network.
  Required IAM permissions: bedrock:InvokeModel, bedrock:ListFoundationModels

  Authentication options:
  • Access Key (dev/testing) — not recommended for production
  • IAM Role / Instance Profile — recommended, no static credentials
""", DIM))
    auth = choose("Auth method", [
        ("access_key",        "Access Key + Secret (dev only)"),
        ("instance_profile",  "Instance Profile / IRSA (production, no static keys)"),
    ])
    region = prompt("AWS Region", default="us-east-1")
    env["AWS_BEDROCK_REGION"] = region
    env["LLM_PROVIDER"] = "aws_bedrock"

    model = choose("Bedrock Model", [
        ("anthropic.claude-3-5-sonnet-20241022-v2:0", "Claude 3.5 Sonnet v2 (recommended)"),
        ("anthropic.claude-opus-4-7",                  "Claude Opus 4.7 (most capable)"),
        ("anthropic.claude-3-haiku-20240307-v1:0",     "Claude 3 Haiku (fastest)"),
        ("meta.llama3-70b-instruct-v1:0",              "Meta Llama 3 70B (open source)"),
    ])
    env["AWS_BEDROCK_MODEL_ID"] = model

    if auth == "access_key":
        key_id = prompt("Access Key ID")
        secret  = prompt("Secret Access Key", secret=True)
        env["AWS_ACCESS_KEY_ID"]     = key_id
        env["AWS_SECRET_ACCESS_KEY"] = secret

    return _test_bedrock(env)

def _test_bedrock(env: dict) -> bool:
    info("Testing AWS Bedrock connection…")
    try:
        import boto3, json as _json
        kwargs: dict = {"region_name": env.get("AWS_BEDROCK_REGION", "us-east-1")}
        if env.get("AWS_ACCESS_KEY_ID"):
            kwargs["aws_access_key_id"]     = env["AWS_ACCESS_KEY_ID"]
            kwargs["aws_secret_access_key"] = env["AWS_SECRET_ACCESS_KEY"]
        client = boto3.client("bedrock-runtime", **kwargs)
        body = _json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Reply with OK"}],
        })
        resp = client.invoke_model(
            modelId=env.get("AWS_BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
            body=body, contentType="application/json",
        )
        ok(f"AWS Bedrock connected — model: {env.get('AWS_BEDROCK_MODEL_ID')}")
        return True
    except ImportError:
        warn("boto3 not installed — run: pip install boto3")
        return False
    except Exception as e:
        err(f"Bedrock connection failed: {e}")
        return False

def configure_azure_openai(env: dict) -> bool:
    print(c("""
  Azure OpenAI Setup:
  ────────────────────
  Azure OpenAI keeps AI traffic inside your Azure tenant — ideal for banking/regulated environments.
  Deploy a model at: Azure Portal → Azure OpenAI → Deployments

  Auth options:
  • Service Principal — for initial setup or cross-subscription access
  • Managed Identity — for AKS/VM deployments (recommended, no secrets)
""", DIM))
    endpoint = prompt("Azure OpenAI Endpoint", default="https://your-resource.openai.azure.com/")
    deployment = prompt("Deployment Name", default="gpt-4o")
    api_version = prompt("API Version", default="2024-02-01")

    auth = choose("Auth method", [
        ("api_key",          "API Key (get from Azure Portal → Keys and Endpoint)"),
        ("managed_identity", "Azure Managed Identity (AKS pod / VM — no secret)"),
    ])

    env["AZURE_OPENAI_ENDPOINT"]    = endpoint
    env["AZURE_OPENAI_DEPLOYMENT"]  = deployment
    env["AZURE_OPENAI_API_VERSION"] = api_version
    env["LLM_PROVIDER"]             = "azure_openai"

    if auth == "api_key":
        key = prompt("Azure OpenAI API Key", secret=True)
        env["AZURE_OPENAI_API_KEY"] = key

    return _test_azure_openai(env)

def _test_azure_openai(env: dict) -> bool:
    info("Testing Azure OpenAI connection…")
    try:
        from openai import AzureOpenAI
        kwargs: dict = {
            "azure_endpoint": env.get("AZURE_OPENAI_ENDPOINT", ""),
            "api_version": env.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        }
        if env.get("AZURE_OPENAI_API_KEY"):
            kwargs["api_key"] = env["AZURE_OPENAI_API_KEY"]
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
            kwargs["azure_ad_token_provider"] = token_provider

        client = AzureOpenAI(**kwargs)
        resp = client.chat.completions.create(
            model=env.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            messages=[{"role": "user", "content": "Reply with OK"}],
            max_tokens=10,
        )
        ok(f"Azure OpenAI connected — deployment: {env.get('AZURE_OPENAI_DEPLOYMENT')}")
        return True
    except ImportError:
        warn("openai or azure-identity not installed — run: pip install openai azure-identity")
        return False
    except Exception as e:
        err(f"Azure OpenAI connection failed: {e}")
        return False

def configure_vertex(env: dict) -> bool:
    print(c("""
  GCP Vertex AI Setup:
  ─────────────────────
  Vertex AI keeps AI traffic inside your GCP project.
  Enable the API at: console.cloud.google.com/vertex-ai

  Auth options:
  • Service Account JSON key file
  • Application Default Credentials (ADC) — for GKE / GCE
""", DIM))
    project_id = prompt("GCP Project ID")
    location   = prompt("Vertex AI Location", default="us-central1")
    model      = choose("Model", [
        ("gemini-1.5-pro",        "Gemini 1.5 Pro (recommended)"),
        ("gemini-1.5-flash",      "Gemini 1.5 Flash (fast/cheap)"),
        ("gemini-2.0-flash-exp",  "Gemini 2.0 Flash (latest)"),
    ])

    auth = choose("Auth method", [
        ("adc",             "Application Default Credentials (GKE/GCE/gcloud auth)"),
        ("service_account", "Service Account JSON key file path"),
    ])

    env["GCP_PROJECT_ID"]          = project_id
    env["GCP_VERTEX_AI_LOCATION"]  = location
    env["GCP_VERTEX_AI_MODEL"]     = model
    env["LLM_PROVIDER"]            = "gcp_vertex"

    if auth == "service_account":
        key_path = prompt("Path to service account JSON file")
        env["GOOGLE_APPLICATION_CREDENTIALS"] = key_path

    return _test_vertex(env)

def _test_vertex(env: dict) -> bool:
    info("Testing GCP Vertex AI connection…")
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel
        creds = None
        if env.get("GOOGLE_APPLICATION_CREDENTIALS"):
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(env["GOOGLE_APPLICATION_CREDENTIALS"])
        vertexai.init(project=env.get("GCP_PROJECT_ID"), location=env.get("GCP_VERTEX_AI_LOCATION", "us-central1"), credentials=creds)
        model = GenerativeModel(env.get("GCP_VERTEX_AI_MODEL", "gemini-1.5-pro"))
        resp = model.generate_content("Reply with OK")
        ok(f"GCP Vertex AI connected — model: {env.get('GCP_VERTEX_AI_MODEL')}")
        return True
    except ImportError:
        warn("google-cloud-aiplatform not installed — run: pip install google-cloud-aiplatform")
        return False
    except Exception as e:
        err(f"Vertex AI connection failed: {e}")
        return False

def configure_ollama(env: dict) -> bool:
    print(c("""
  Ollama Setup (Self-hosted, Air-gapped):
  ────────────────────────────────────────
  Ollama runs entirely in your network — no internet required.
  Install at: https://ollama.ai

  Recommended models for AIOps:
  • llama3.1:70b — best quality (requires ~40GB VRAM)
  • mistral:7b   — good quality, lower resources
  • codellama:13b — good for kubectl/code generation
""", DIM))
    base_url = prompt("Ollama URL", default="http://localhost:11434")
    model    = prompt("Model name (must be pulled first)", default="llama3.1:70b")

    env["OLLAMA_BASE_URL"] = base_url
    env["OLLAMA_MODEL"]    = model
    env["LLM_PROVIDER"]    = "ollama"

    return _test_ollama(base_url, model)

def _test_ollama(base_url: str, model: str) -> bool:
    info(f"Testing Ollama at {base_url}…")
    try:
        import urllib.request, json as _json
        payload = _json.dumps({"model": model, "messages": [{"role": "user", "content": "Reply OK"}], "stream": False}).encode()
        req = urllib.request.Request(f"{base_url}/api/chat", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read())
            ok(f"Ollama connected — model: {model}")
            return True
    except Exception as e:
        err(f"Ollama connection failed: {e}")
        info(f"Make sure Ollama is running and model '{model}' is pulled: ollama pull {model}")
        return False


# ─── Write .env file ──────────────────────────────────────────────

def write_env(env: dict, path: Path) -> None:
    lines = [
        "# OpsBrain Configuration",
        "# Generated by setup.py — do not commit this file",
        "",
        "# ── LLM Provider ─────────────────────────────────────────",
    ]
    llm_keys = ["LLM_PROVIDER", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
                 "AWS_BEDROCK_REGION", "AWS_BEDROCK_MODEL_ID", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                 "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION",
                 "GCP_PROJECT_ID", "GCP_VERTEX_AI_LOCATION", "GCP_VERTEX_AI_MODEL", "GOOGLE_APPLICATION_CREDENTIALS",
                 "OLLAMA_BASE_URL", "OLLAMA_MODEL"]
    for k in llm_keys:
        if k in env:
            lines.append(f"{k}={env[k]}")

    lines += [
        "",
        "# ── Auth ─────────────────────────────────────────────────",
    ]
    for k in ["JWT_SECRET_KEY", "APP_SECRET_KEY", "APP_ENV", "JWT_EXPIRE_MINUTES"]:
        if k in env:
            lines.append(f"{k}={env[k]}")

    lines += [
        "",
        "# ── Network ──────────────────────────────────────────────",
        "CORS_ORIGINS=[\"*\"]",
        "",
        "# ── Add connector credentials below ──────────────────────",
        "# SNOW_INSTANCE_URL=",
        "# SNOW_USERNAME=",
        "# SNOW_PASSWORD=",
        "# CONFLUENCE_BASE_URL=",
        "# CONFLUENCE_API_TOKEN=",
        "# DYNATRACE_BASE_URL=",
        "# DYNATRACE_API_TOKEN=",
        "# ELASTICSEARCH_URL=",
        "# SLACK_WEBHOOK_URL=",
        "# TEAMS_WEBHOOK_URL=",
        "# SMTP_HOST=",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok(f"Configuration written to {path}")


# ─── Secrets generation ───────────────────────────────────────────

def generate_secrets(env: dict) -> None:
    import secrets
    env["JWT_SECRET_KEY"]  = secrets.token_hex(32)
    env["APP_SECRET_KEY"]  = secrets.token_hex(32)
    env["APP_ENV"]         = "production"
    env["JWT_EXPIRE_MINUTES"] = "480"
    ok("JWT secret keys generated")


# ─── Docker / startup check ───────────────────────────────────────

def check_docker() -> bool:
    return shutil.which("docker") is not None and shutil.which("docker-compose") is not None

def start_application(root: Path) -> None:
    info("Starting OpsBrain with docker-compose…")
    try:
        subprocess.run(["docker-compose", "up", "-d", "--build"], cwd=root, check=True)
        print()
        ok("OpsBrain started successfully!")
        print(c(f"""
  ┌──────────────────────────────────────────┐
  │  Frontend:  http://localhost:3010        │
  │  Backend:   http://localhost:8011        │
  │  API Docs:  http://localhost:8011/docs   │
  │                                          │
  │  Default login: admin / admin123         │
  │  (Change this immediately in Admin tab)  │
  └──────────────────────────────────────────┘
""", GREEN))
    except subprocess.CalledProcessError as e:
        err(f"docker-compose failed: {e}")
        info("Try manually: docker-compose up -d --build")


# ─── Verify existing .env ─────────────────────────────────────────

def check_existing(env_path: Path) -> bool:
    if not env_path.exists():
        err(f".env not found at {env_path}")
        return False

    from dotenv import dotenv_values
    env = dotenv_values(env_path)
    provider = env.get("LLM_PROVIDER", "")
    print(c(f"\n  Current configuration:", BOLD))
    print(f"  LLM Provider: {c(provider or '(not set)', YELLOW if not provider else GREEN)}")

    if not provider:
        err("LLM_PROVIDER not set in .env — run setup.py without --check to configure")
        return False

    testers = {
        "anthropic":    lambda: _test_anthropic(env.get("ANTHROPIC_API_KEY", ""), env.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")),
        "aws_bedrock":  lambda: _test_bedrock(env),
        "azure_openai": lambda: _test_azure_openai(env),
        "gcp_vertex":   lambda: _test_vertex(env),
        "ollama":       lambda: _test_ollama(env.get("OLLAMA_BASE_URL", "http://localhost:11434"), env.get("OLLAMA_MODEL", "llama3.1:70b")),
    }
    tester = testers.get(provider)
    if tester:
        return tester()
    warn(f"Unknown provider '{provider}'")
    return False


# ─── Main ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="OpsBrain Installation Wizard")
    parser.add_argument("--check", action="store_true", help="Verify existing .env without changing anything")
    parser.add_argument("--start", action="store_true", help="Start OpsBrain after setup")
    args = parser.parse_args()

    root     = Path(__file__).parent
    env_path = root / ".env"

    banner()

    if args.check:
        step(0, "Verifying existing configuration")
        success = check_existing(env_path)
        sys.exit(0 if success else 1)

    env: dict[str, str] = {}

    # ── Step 1: LLM Provider ──────────────────────────────────────
    step(1, "LLM Provider (required — the AI brain of OpsBrain)")
    print(c("""
  The LLM provider must be configured BEFORE starting OpsBrain.
  Choose based on your deployment context:
  • Cloud-hosted & internet OK → Anthropic (simplest)
  • AWS environment → Bedrock (traffic stays in AWS)
  • Azure environment → Azure OpenAI (traffic stays in Azure)
  • GCP environment → Vertex AI (traffic stays in GCP)
  • Air-gapped / no internet → Ollama (fully self-hosted)
""", DIM))
    provider = choose("LLM Provider", LLM_PROVIDERS)

    configurers = {
        "anthropic":    configure_anthropic,
        "aws_bedrock":  configure_bedrock,
        "azure_openai": configure_azure_openai,
        "gcp_vertex":   configure_vertex,
        "ollama":       configure_ollama,
    }
    connected = configurers[provider](env)

    if not connected:
        print()
        warn("LLM connection test failed. You can continue setup, but OpsBrain won't work until the LLM is reachable.")
        proceed = input(c("  Continue anyway? [y/N]: ", YELLOW)).strip().lower()
        if proceed != "y":
            info("Setup cancelled. Fix the LLM connection and re-run setup.py")
            sys.exit(1)

    # ── Step 2: Auth secrets ──────────────────────────────────────
    step(2, "Auth secrets")
    generate_secrets(env)
    env["APP_ENV"] = choose("Environment", [
        ("production",  "Production"),
        ("development", "Development"),
    ], default=2 if os.getenv("DEBUG") else 1)

    # ── Step 3: Write .env ───────────────────────────────────────
    step(3, "Write configuration")
    if env_path.exists():
        warn(f"{env_path} already exists")
        overwrite = input(c("  Overwrite existing .env? [y/N]: ", YELLOW)).strip().lower()
        if overwrite != "y":
            info("Keeping existing .env — setup complete")
            sys.exit(0)

    write_env(env, env_path)

    # ── Step 4: Start? ────────────────────────────────────────────
    step(4, "Start OpsBrain")
    if args.start:
        if check_docker():
            start_application(root)
        else:
            warn("docker / docker-compose not found")
            info("Install Docker: https://docs.docker.com/get-docker/")
            info("Then run: docker-compose up -d --build")
    else:
        print()
        ok("Setup complete! To start OpsBrain:")
        print()
        info("  docker-compose up -d --build")
        info("  or: python setup.py --start")
        print()
        print(c("  Once started:", DIM))
        info("  Frontend: http://localhost:3010")
        info("  Backend:  http://localhost:8011/docs")
        info("  Login:    admin / admin123")
        print()

    print(c("  Setup complete.\n", GREEN))


if __name__ == "__main__":
    main()

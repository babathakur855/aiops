# OpsBrain — AI-Native AIOps Platform

> Open-core AIOps platform with transparent AI reasoning, predictive intelligence, and automatic post-mortems — powered by Claude.

## Key Features

| Feature | Description |
|---|---|
| 🧠 **Transparent AI Reasoning** | Claude's extended thinking is visible in the UI — see every step of the analysis |
| 🔮 **Predictive Intelligence** | Detects anomalies and forecasts failures before they happen |
| 📄 **Auto Post-Mortems** | Generates blameless, structured post-mortems instantly from incident data |
| ☸️ **Natural Language K8s** | Talk to your cluster in plain English — gets translated to kubectl commands |
| 💰 **Cloud Cost Optimization** | Identifies waste and generates rightsizing PRs with exact $ savings |
| 🔁 **GitOps-Native Automation** | Runbooks generated as YAML, ready to commit to Git |
| ☁️ **Multi-Cloud** | AWS, Azure, and GCP supported out of the box |
| 🔌 **50+ Integrations** | Prometheus, Datadog, Splunk, Slack, PagerDuty, Jira, and more |
| 💸 **Pay-per-Use** | No monthly subscription — only Claude API costs per analysis |
| 🔓 **Open-Source Core** | No vendor lock-in, bring your own model |

## Core Capabilities

### 🔴 AI-SRE Agent
- Root cause analysis with Claude extended thinking (reasoning visible in UI)
- Correlates logs, metrics, deployments, and service dependencies
- Generates copy-pasteable kubectl commands and YAML fixes
- Auto-generates production runbooks stored as YAML

### 💰 AI-FinOps Agent
- Analyzes cloud spend across AWS/Azure/GCP
- Identifies idle RDS, oversized EC2, overprovisioned pods
- Generates rightsizing Pull Requests with YAML patches
- Detects cost anomalies (e.g. debug logging enabled in prod)

### ☸️ AI-K8s Ops Agent
- Natural language → kubectl commands
- Cluster health reports with capacity forecasting
- HPA status, pod rightsizing, upgrade planning

### 📄 Auto Post-Mortem Generator
- Blameless post-mortems from incident data
- 5-Whys root cause analysis
- Structured action items with priority and due dates
- Business impact quantification

### 🔮 Predictive Intelligence
- Anomaly detection before incidents happen
- Capacity forecasting from historical trends

## Architecture

```
frontend/          Next.js 14 + Tailwind — real-time streaming dashboard
backend/
  main.py          FastAPI — REST + WebSocket endpoints
  core/
    claude_client.py    Claude with prompt caching, extended thinking, tool use
    knowledge_graph.py  Service dependency graph and incident history
    postmortem.py       Blameless post-mortem generator
  agents/
    sre_agent.py        Incident triage and RCA
    finops_agent.py     Cost optimization
    k8s_agent.py        Kubernetes operations
  tools/
    kubernetes_tools.py  kubectl, logs, deployments (+ mock data for demo)
    observability_tools.py  metrics, alerts, traces
    cloud_tools.py       AWS/Azure/GCP cost tools
```

## Quick Start

```bash
# 1. Set your Anthropic API key
cp .env.example .env
# Edit .env and add: ANTHROPIC_API_KEY=your_key_here

# 2. Run with Docker Compose
docker-compose up

# Backend:  http://localhost:8011
# Frontend: http://localhost:3010
# API docs: http://localhost:8011/docs
```

## Local Development (without Docker)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8011

# Frontend
cd frontend
npm install
npm run dev  # runs on port 3010
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/incidents/analyze` | Full RCA with tool use + optional extended thinking |
| POST | `/api/v1/incidents/triage` | Quick severity + initial hypothesis (fast) |
| POST | `/api/v1/cost/analyze` | Full cost optimization analysis |
| POST | `/api/v1/k8s/query` | Natural language Kubernetes query |
| GET | `/api/v1/k8s/health-report` | Cluster health report |
| POST | `/api/v1/postmortem/generate` | Generate blameless post-mortem |
| POST | `/api/v1/runbooks/generate` | Generate YAML runbook |
| POST | `/api/v1/chat` | General AI chat (streaming supported) |
| WS | `/ws/stream` | WebSocket streaming |
| GET | `/api/v1/dashboard` | Real-time dashboard metrics |

## Setup

```bash
cp .env.example .env
# Fill in your values
```

## Demo Scenarios

The tool ships with realistic mock data demonstrating:
- **order-service CrashLoopBackOff** — database connection pool exhaustion after deployment
- **payment-service HPA scaling** — CPU pressure, scaling toward max replicas
- **$7,240/month in cloud waste** — idle RDS, oversized EC2, overprovisioned pods
- **Cost anomaly** — CloudWatch logging costs spiked 366% (debug mode left on in prod)

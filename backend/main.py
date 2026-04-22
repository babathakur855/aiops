"""
OpsBrain — AI-Native AIOps Platform
FastAPI backend with auth, RBAC, connector framework, and streaming agents.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config.settings import settings
from config.llm_factory import get_llm_client
from auth.rbac import get_current_user, require_sre, require_finops, require_any
from auth.router import router as auth_router
from connectors.registry import registry
from connectors.router import router as connectors_router
from collector.router import router as collector_router
from collector.otlp_receiver import router as otlp_router
from checkouts.router import router as checkouts_router
from checkouts import store as checkout_store
from checkouts import scheduler as checkout_scheduler
from knowledge.router import router as knowledge_router
from knowledge import store as knowledge_store
from knowledge import set_store as knowledge_set_store
from knowledge.defaults import init_defaults


# ------------------------------------------------------------------
# App lifespan
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    llm = get_llm_client()
    app.state.llm = llm

    from core.knowledge_graph import ServiceKnowledgeGraph
    from core.postmortem import PostMortemGenerator
    from agents.sre_agent import SREAgent
    from agents.finops_agent import FinOpsAgent
    from agents.k8s_agent import K8sAgent
    from agents.predictive_agent import PredictiveAgent

    app.state.graph = ServiceKnowledgeGraph()
    app.state.sre = SREAgent(llm)
    app.state.finops = FinOpsAgent(llm)
    app.state.k8s = K8sAgent(llm)
    app.state.predictive = PredictiveAgent(llm)
    app.state.postmortem_gen = PostMortemGenerator(llm)
    app.state.registry = registry

    # Initialise knowledge base tables + load built-in SOPs/templates
    knowledge_store.init_db()
    knowledge_set_store.init_db()
    init_defaults()

    # Initialise checkout DB tables and background scheduler
    checkout_store.init_db()
    checkout_scheduler.configure(llm)
    checkout_scheduler.start(interval_seconds=60)

    # Start background metric collection scheduler
    from collector import scheduler as col_scheduler
    col_scheduler.start(interval_seconds=int(os.getenv("COLLECTION_INTERVAL_SECONDS", "300")))
    yield

    checkout_scheduler.stop()
    col_scheduler.stop()


app = FastAPI(
    title="OpsBrain",
    version="1.0.0",
    description="AI-Native AIOps Platform — plug-and-play deployment anywhere",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(connectors_router)
app.include_router(collector_router)
app.include_router(otlp_router)
app.include_router(checkouts_router)
app.include_router(knowledge_router)


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

class IncidentRequest(BaseModel):
    alert_name: str
    service: str
    namespace: str = "production"
    description: str
    deep_analysis: bool = False
    snow_sys_id: str = ""     # If set, push analysis back to SNOW


class ChatRequest(BaseModel):
    agent_type: str = "sre"
    message: str
    use_thinking: bool = False
    stream: bool = False


class K8sQueryRequest(BaseModel):
    question: str
    namespace: str = "production"


class PostMortemRequest(BaseModel):
    title: str
    service: str
    severity: str
    started_at: str
    resolved_at: str
    detected_by: str = "Alerting system"
    resolved_by: str = "On-call engineer"
    affected_users: int = 0
    error_rate_peak_pct: float = 0.0
    timeline_events: list[dict] = []
    root_cause_notes: str = ""
    actions_taken: list[str] = []
    publish_to_confluence: bool = False
    confluence_space_key: str = ""
    email_to: str = ""


class RunbookRequest(BaseModel):
    service: str
    incident_type: str


class CostAnalysisRequest(BaseModel):
    cloud: str = "all"


class AlertIngestRequest(BaseModel):
    source: str = "generic"
    payload: dict


# ------------------------------------------------------------------
# Health & system
# ------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health():
    from setup_check import get_setup_requirements
    reqs = get_setup_requirements()
    return {
        "status": "ok" if reqs["configured"] else "setup_required",
        "service": "opsbrain-backend",
        "version": "1.0.0",
        "llm_provider": settings.llm_provider,
        "llm_configured": reqs["configured"],
        "env": settings.app_env,
    }


@app.get("/setup/status", tags=["setup"])
async def setup_status():
    """
    No auth required — called by frontend before login to check if LLM is configured.
    If setup_required is true, the frontend shows the setup instructions page.
    """
    from setup_check import get_setup_requirements, check_llm
    reqs = get_setup_requirements()
    llm_result = await check_llm()
    return {
        "setup_required": not reqs["configured"] or not llm_result["ok"],
        "llm": llm_result,
        "requirements": reqs,
        "how_to_fix": (
            "Run the setup wizard: python setup.py\n"
            "or ./setup.sh (Linux/Mac) / .\\setup.ps1 (Windows)\n"
            "Then restart the backend."
        ) if not llm_result["ok"] else None,
    }


@app.get("/api/v1/system/info", dependencies=[Depends(require_any)], tags=["system"])
async def system_info():
    return {
        "llm_provider": settings.llm_provider,
        "connectors": len(registry.list_configs()),
        "service_graph": app.state.graph.summary(),
        "usage": app.state.llm.get_usage_summary() if hasattr(app.state.llm, "get_usage_summary") else {},
    }


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------

@app.get("/api/v1/dashboard", dependencies=[Depends(require_any)], tags=["dashboard"])
async def get_dashboard():
    from tools.observability_tools import _get_active_alerts
    from tools.kubernetes_tools import _get_pod_status
    alerts = await _get_active_alerts({})
    pods = await _get_pod_status({"namespace": "production"})
    return {
        "alerts": alerts["alerts"],
        "pod_summary": pods["summary"],
        "metrics": {
            "order_service_error_rate": 97.8,
            "payment_service_latency_p99_ms": 46,
            "auth_service_latency_p99_ms": 43,
            "monthly_cloud_cost_usd": 34820,
            "projected_savings_usd": 10360,
        },
        "service_health": [
            {"name": "api-gateway", "status": "healthy", "uptime_pct": 99.99},
            {"name": "auth-service", "status": "healthy", "uptime_pct": 99.95},
            {"name": "payment-service", "status": "degraded", "uptime_pct": 99.1},
            {"name": "order-service", "status": "down", "uptime_pct": 0.0},
            {"name": "notification-svc", "status": "pending", "uptime_pct": 99.5},
        ],
        "connectors": [{"name": c.name, "type": c.type, "enabled": c.enabled}
                       for c in registry.list_configs()],
    }


# ------------------------------------------------------------------
# Alert ingestion — unified webhook for all monitoring tools
# ------------------------------------------------------------------

@app.post("/api/v1/alerts/ingest", tags=["alerts"])
async def ingest_alert(body: AlertIngestRequest):
    """
    Universal alert webhook. Works with Prometheus AlertManager,
    Dynatrace, Datadog, SNOW, and any custom sender.
    Normalises the payload and optionally triggers auto-analysis.
    """
    source = body.source.lower()
    payload = body.payload

    if source == "prometheus":
        alert_name = payload.get("commonLabels", {}).get("alertname", "Unknown")
        service = payload.get("commonLabels", {}).get("service", "unknown")
        description = payload.get("commonAnnotations", {}).get("summary", "")
    elif source == "dynatrace":
        alert_name = payload.get("title", "Unknown")
        service = payload.get("impactedEntities", [{}])[0].get("name", "unknown") if payload.get("impactedEntities") else "unknown"
        description = payload.get("problemDetailsText", "")
    elif source == "servicenow":
        alert_name = payload.get("short_description", "Unknown")
        service = payload.get("cmdb_ci", "unknown")
        description = payload.get("description", "")
    else:
        alert_name = payload.get("alert_name", payload.get("title", "Unknown"))
        service = payload.get("service", "unknown")
        description = payload.get("description", payload.get("message", ""))

    return {
        "received": True,
        "normalised": {"alert_name": alert_name, "service": service, "description": description},
        "tip": f"POST /api/v1/incidents/analyze with this payload to trigger AI analysis",
    }


# ------------------------------------------------------------------
# SRE endpoints
# ------------------------------------------------------------------

@app.post("/api/v1/incidents/analyze", dependencies=[Depends(require_sre)], tags=["sre"])
async def analyze_incident(req: IncidentRequest):
    ctx = app.state.graph.get_context_for_rca(req.service)

    # Enrich with Confluence SOPs if connected
    confluence_docs = []
    from connectors.base import ConnectorType
    confluence_connectors = registry.get_by_type(ConnectorType.CONFLUENCE)
    if confluence_connectors:
        try:
            confluence_docs = await confluence_connectors[0].fetch_documents(
                query=f"{req.service} {req.alert_name}", limit=3
            )
        except Exception:
            pass

    description_with_context = f"{req.description}\n\nService Context:\n{ctx}"
    if confluence_docs:
        doc_refs = "\n".join(f"- {d['title']}: {d['url']}" for d in confluence_docs)
        description_with_context += f"\n\nRelevant SOPs from Confluence:\n{doc_refs}"

    result = await app.state.sre.analyze_incident(
        alert_name=req.alert_name,
        service=req.service,
        namespace=req.namespace,
        description=description_with_context,
        deep_analysis=req.deep_analysis,
    )

    # Push analysis back to SNOW if sys_id provided
    if req.snow_sys_id:
        snow_connectors = registry.get_by_type(ConnectorType.SERVICENOW)
        if snow_connectors:
            from connectors.snow import ServiceNowConnector
            snow: ServiceNowConnector = snow_connectors[0]  # type: ignore
            await snow.add_work_note(req.snow_sys_id, result["analysis"][:4000])

    return result


@app.post("/api/v1/incidents/triage", dependencies=[Depends(require_sre)], tags=["sre"])
async def quick_triage(req: IncidentRequest):
    return await app.state.sre.quick_triage({
        "alert": req.alert_name, "service": req.service,
        "namespace": req.namespace, "description": req.description,
    })


@app.post("/api/v1/runbooks/generate", dependencies=[Depends(require_sre)], tags=["sre"])
async def generate_runbook(req: RunbookRequest):
    return await app.state.sre.generate_runbook(req.service, req.incident_type)


# ------------------------------------------------------------------
# FinOps endpoints
# ------------------------------------------------------------------

@app.post("/api/v1/cost/analyze", dependencies=[Depends(require_finops)], tags=["finops"])
async def analyze_costs(req: CostAnalysisRequest):
    return await app.state.finops.analyze_costs(req.cloud)


@app.post("/api/v1/cost/rightsizing-pr", dependencies=[Depends(require_finops)], tags=["finops"])
async def generate_rightsizing_pr(namespace: str = "production"):
    return await app.state.finops.generate_rightsizing_pr(namespace)


# ------------------------------------------------------------------
# K8s endpoints
# ------------------------------------------------------------------

@app.post("/api/v1/k8s/query", dependencies=[Depends(require_sre)], tags=["k8s"])
async def k8s_query(req: K8sQueryRequest):
    return await app.state.k8s.natural_language_query(req.question, req.namespace)


@app.get("/api/v1/k8s/health-report", dependencies=[Depends(require_sre)], tags=["k8s"])
async def k8s_health_report(namespace: str = "production"):
    return await app.state.k8s.cluster_health_report(namespace)


@app.get("/api/v1/k8s/status", dependencies=[Depends(require_sre)], tags=["k8s"])
async def k8s_connection_status():
    from tools.kubernetes_tools import k8s_status
    return k8s_status()


# ------------------------------------------------------------------
# Predictive Intelligence
# ------------------------------------------------------------------

@app.get("/api/v1/predict/anomalies", dependencies=[Depends(require_sre)], tags=["predict"])
async def predict_anomalies(services: str = ""):
    svc_list = [s.strip() for s in services.split(",") if s.strip()] if services else None
    return await app.state.predictive.predict_anomalies(svc_list)


@app.get("/api/v1/predict/capacity", dependencies=[Depends(require_sre)], tags=["predict"])
async def predict_capacity(namespace: str = "production"):
    return await app.state.predictive.forecast_capacity(namespace)


@app.get("/api/v1/predict/sweep", dependencies=[Depends(require_sre)], tags=["predict"])
async def predictive_sweep():
    return await app.state.predictive.proactive_sweep()


# ------------------------------------------------------------------
# Post-mortem
# ------------------------------------------------------------------

@app.post("/api/v1/postmortem/generate", dependencies=[Depends(require_sre)], tags=["postmortem"])
async def generate_postmortem(req: PostMortemRequest):
    from core.postmortem import IncidentData
    incident = IncidentData(
        title=req.title, service=req.service, severity=req.severity,
        started_at=req.started_at, resolved_at=req.resolved_at,
        detected_by=req.detected_by, resolved_by=req.resolved_by,
        affected_users=req.affected_users, error_rate_peak_pct=req.error_rate_peak_pct,
        timeline_events=req.timeline_events, root_cause_notes=req.root_cause_notes,
        actions_taken=req.actions_taken,
    )
    result = await app.state.postmortem_gen.generate(incident)

    # Publish to Confluence if requested
    if req.publish_to_confluence and req.confluence_space_key:
        from connectors.base import ConnectorType
        confluence_connectors = registry.get_by_type(ConnectorType.CONFLUENCE)
        if confluence_connectors:
            from connectors.confluence import ConfluenceConnector
            confluence: ConfluenceConnector = confluence_connectors[0]  # type: ignore
            pub = await confluence.create_page(
                req.confluence_space_key, f"Post-Mortem: {req.title}", result["document"]
            )
            result["confluence_url"] = pub.get("url", "")

    # Email if requested
    if req.email_to:
        from connectors.base import ConnectorType
        email_connectors = registry.get_by_type(ConnectorType.EMAIL)
        if email_connectors:
            from connectors.email_connector import EmailConnector
            emailer: EmailConnector = email_connectors[0]  # type: ignore
            await emailer.send_postmortem(req.email_to, req.title, result["document"])
            result["emailed_to"] = req.email_to

    return result


# ------------------------------------------------------------------
# General chat with streaming
# ------------------------------------------------------------------

@app.post("/api/v1/chat", dependencies=[Depends(require_any)], tags=["chat"])
async def chat(req: ChatRequest):
    if req.stream:
        return StreamingResponse(
            app.state.llm.stream(req.agent_type, req.message, req.use_thinking),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return await app.state.llm.analyze(
        agent_type=req.agent_type,
        user_message=req.message,
        use_thinking=req.use_thinking,
    )


# ------------------------------------------------------------------
# WebSocket streaming
# ------------------------------------------------------------------

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            token = data.get("token", "")
            try:
                from auth.jwt_handler import decode_token
                decode_token(token)
            except Exception:
                await websocket.send_json({"type": "error", "message": "Unauthorized"})
                await websocket.close(code=4001)
                return

            agent_type = data.get("agent_type", "sre")
            message = data.get("message", "")
            use_thinking = data.get("use_thinking", False)

            async for chunk in app.state.llm.stream(agent_type, message, use_thinking):
                await websocket.send_text(chunk)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})

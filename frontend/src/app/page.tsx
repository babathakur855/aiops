"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import {
  AlertTriangle, Activity, DollarSign, Brain,
  ChevronRight, ChevronDown, RotateCcw, TrendingDown, TrendingUp, CheckCircle2,
  Clock, Layers, MessageSquare, FileText,
  LogOut, User, Shield, Plug, Server, Plus, Trash2,
  Eye, EyeOff, Zap, AlertCircle, CalendarClock, PlayCircle, X,
  BookOpen, Upload, Edit3, Tag,
} from "lucide-react";
import { ConnectorsTab } from "@/components/ConnectorsTab";
import { KnowledgeTab } from "@/components/KnowledgeTab";
import { DashboardTab } from "@/components/DashboardTab";
import { SetupPage } from "@/components/SetupPage";
import { EnvironmentsPage } from "@/components/EnvironmentsPage";
import ReactMarkdown from "react-markdown";
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from "recharts";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

// ─── Demo data — pre-populates every tab for instant showcase ─────
const _now = () => new Date().toISOString();
const _ago = (m: number) => new Date(Date.now() - m * 60_000).toISOString();

const DEMO = {
  dashboard: {
    alerts: [
      { name: "PodCrashLoopBackOff", severity: "critical", service: "order-service", namespace: "production", message: "Pod order-service-8f9g0h-def34 is in CrashLoopBackOff (23 restarts) — DB connection pool exhausted", firing_since: _ago(8) },
      { name: "HighErrorRate", severity: "critical", service: "order-service", namespace: "production", message: "Error rate 97.8% (threshold: 5%) — all order placements failing", firing_since: _ago(7) },
      { name: "HPAMaxReplicas", severity: "warning", service: "payment-service", namespace: "production", message: "HPA scaling toward max replicas (7/10), CPU at 84% — traffic spike in progress", firing_since: _ago(4) },
      { name: "NodeMemoryPressure", severity: "warning", service: "node-2", namespace: "kube-system", message: "Node node-2 memory at 92% — risk of OOM pod eviction within 3 hours", firing_since: _ago(15) },
    ],
    pod_summary: { running: 14, pending: 1, crashloopbackoff: 1, failed: 0, total: 16 },
    metrics: { monthly_cloud_cost_usd: 34820, projected_savings_usd: 10360, order_service_error_rate: 97.8, payment_service_latency_p99_ms: 46 },
    service_health: [
      { name: "api-gateway",       status: "healthy",  uptime_pct: 99.99 },
      { name: "auth-service",      status: "healthy",  uptime_pct: 99.95 },
      { name: "payment-service",   status: "degraded", uptime_pct: 99.1  },
      { name: "order-service",     status: "down",     uptime_pct: 0.0   },
      { name: "inventory-service", status: "healthy",  uptime_pct: 99.97 },
      { name: "notification-svc",  status: "pending",  uptime_pct: 99.5  },
    ],
    connectors: [
      { id: "1", name: "Slack #incidents", type: "slack",       enabled: true },
      { id: "2", name: "SNOW Production",  type: "servicenow",  enabled: true },
      { id: "3", name: "Confluence Eng",   type: "confluence",  enabled: true },
      { id: "4", name: "Dynatrace SaaS",   type: "dynatrace",   enabled: true },
    ],
  },

  analysisResult: `## Root Cause Analysis — PodCrashLoopBackOff · order-service

**Severity:** P1 (SEV2) &nbsp;·&nbsp; **Namespace:** production &nbsp;·&nbsp; **Duration:** 8+ minutes

### Root Cause
Deployment of \`order-service:v2.4.1\` 8 minutes ago introduced a breaking change in the database connection pool configuration. Migration to **pgxpool v3** silently reduced the default pool size from **10 → 2 connections**, causing the connection pool to exhaust immediately under production load.

### Evidence Chain
| Signal | Value |
|--------|-------|
| Pod restarts | 23 in 8 minutes |
| Log pattern | \`FATAL: connection pool exhausted after 3 retries\` × 47 |
| Deployment trigger | \`a3f8b2c\` — "feat: migrate to connection pool v3" |
| orders-db endpoints | **0 active** (PVC mount failure — secondary factor) |

### Blast Radius
- **4,200 users** unable to place orders · ~\$12,600 revenue at risk/hour
- \`api-gateway\` returning 503 on all \`/api/orders/*\` routes
- \`inventory-service\` and \`notification-svc\` starved of order events (cascade)

### Immediate Fix
\`\`\`bash
# Rollback — restores service in < 2 minutes
kubectl rollout undo deployment/order-service -n production
kubectl rollout status deployment/order-service -n production
\`\`\`

### Prevention
1. Add \`pg_pool_available_connections < 3\` alert to Prometheus
2. Gate DB-touching deployments behind a canary phase (10% traffic)
3. Run \`pgbench\` connection pool stress test in staging CI pipeline`,

  chatMessages: [
    { role: "user", content: "order-service is down, 4200 users affected. What's happening and how do I fix it fast?" },
    { role: "assistant", content: `## Incident Summary

**Status:** P1 active · order-service in CrashLoopBackOff · 8 minutes

I've checked pod logs, deployment history, and the service dependency graph. Here's what happened and how to fix it.

---

### Root Cause
The deployment of **order-service:v2.4.1** (commit \`a3f8b2c\`, 8 min ago) migrated to pgxpool v3 but silently reduced the DB connection pool from 10 → 2. Under production load the pool exhausts in milliseconds — the pod crashes before it can serve a single request.

A secondary factor: \`orders-db\` has **0 healthy endpoints** (PVC mount failure), so even a pool of 10 would struggle.

---

### Fix Now (< 2 min)

\`\`\`bash
# Rollback to v2.4.0
kubectl rollout undo deployment/order-service -n production

# Watch recovery
kubectl rollout status deployment/order-service -n production
kubectl get pods -n production -l app=order-service -w
\`\`\`

### Fix the PVC (secondary)

\`\`\`bash
kubectl describe pvc orders-db-pvc -n production
# Check for "FailedMount" events — re-attach or recreate PVC
\`\`\`

---

**Blast radius:** api-gateway → 503, inventory-service + notification-svc event-starved. Rollback should clear all of these within 90 seconds.` },
    { role: "user", content: "Rollback worked! Service is recovering. Can you generate a runbook so this doesn't happen again?" },
    { role: "assistant", content: `## Runbook: order-service DB Connection Pool Exhaustion

**ID:** RB-ORDER-001 · **Severity:** P1 · **Owner:** Platform SRE

---

### Detection
Alert fires when: \`pod_restarts > 5 in 5m\` AND \`order_service_error_rate > 50%\`

### Diagnosis Checklist

\`\`\`bash
# 1. Check pod status
kubectl get pods -n production -l app=order-service

# 2. Check crash reason
kubectl logs <crashing-pod> -n production --previous | grep -E "FATAL|ERROR|panic"

# 3. Check recent deployments
kubectl rollout history deployment/order-service -n production

# 4. Check DB connectivity
kubectl exec -it <any-pod> -n production -- nc -zv orders-db 5432
\`\`\`

### Remediation Decision Tree

| Symptom | Action |
|---------|--------|
| CrashLoop after deployment | \`kubectl rollout undo deployment/order-service -n production\` |
| DB connection errors only | Check \`orders-db\` pod + PVC health |
| High load (no crash) | \`kubectl scale deployment/order-service --replicas=5\` |
| Memory OOM | Adjust resource limits, check for memory leak in /metrics |

### Post-Incident
1. File incident ticket in ServiceNow
2. Generate post-mortem in OpsBrain → Post-Mortems tab
3. Add regression test to CI pipeline
4. Update this runbook with any new findings` },
  ],

  costAnalysis: `## AI Cost Optimization Report — April 2026

**Total Monthly Spend:** $34,820 &nbsp;(+10.7% MoM)
**Identified Waste:** $7,240/month &nbsp;(20.8% of total)
**Prioritized Quick Wins:** $4,600/month — implementable this week

---

### 🔴 Critical Savings: Idle Reporting Database — Save $1,520/mo

\`prod-reporting-db\` (db.r6g.2xlarge — $1,840/mo) is running at **3.2% average CPU** with only 2 active connections. It serves exclusively end-of-month batch reports that run < 4 hours/month.

**Recommendation:** Migrate to **Aurora Serverless v2** — auto-pauses when idle, auto-scales for month-end batch.
- Implementation: 3 hours · Risk: Low · **Savings: $1,520/mo**

---

### 🟡 EKS Node Group Over-provisioning — Save $960/mo

\`ng-general-purpose\` (6× m5.2xlarge) is at 22% CPU / 38% memory on average. Cluster autoscaler is disabled — nodes never scale in.

\`\`\`bash
# Enable cluster autoscaler
helm upgrade cluster-autoscaler autoscaler/cluster-autoscaler \\
  --set autoDiscovery.clusterName=prod-cluster \\
  --set extraArgs.scale-down-enabled=true
\`\`\`
- **Savings: $960/mo** after scaling to 4 nodes + autoscaler enabled

---

### 🟡 CloudWatch Log Volume Spike — Save $820/mo (+366% anomaly)

Debug logging was accidentally left enabled in production on April 18th, increasing log volume 8×. CloudWatch ingestion cost jumped from $45/day → $210/day.

\`\`\`bash
kubectl set env deployment/order-service LOG_LEVEL=INFO -n production
\`\`\`
- **Savings: $820/mo** · Fix time: 2 minutes

---

### 📦 K8s Rightsizing — Save $520/mo

| Workload | Current CPU | Actual | Recommended | Save |
|----------|------------|--------|-------------|------|
| auth-service | 200m / 512Mi | 45m / 128Mi | 100m / 192Mi | $180/mo |
| notification-svc | 500m / 1Gi | 30m / 200Mi | 100m / 256Mi | $340/mo |

**Generate rightsizing PR** → Click "Rightsizing PR" button above to get ready-to-merge YAML patches.`,

  postMortem: `# Post-Mortem: order-service CrashLoopBackOff — DB Connection Pool Exhaustion
**Date:** ${new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })} &nbsp;·&nbsp; **Severity:** P1 (SEV2) &nbsp;·&nbsp; **Status:** Resolved

---

## Executive Summary

A deployment of \`order-service:v2.4.1\` introduced a database connection pool misconfiguration that caused the service to crash immediately on startup. The migration to pgxpool v3 silently reduced the pool size from 10 → 2, exhausting connections within milliseconds of startup. The incident lasted **8 minutes**, affected **~4,200 users**, and resulted in an estimated **$1,680 revenue impact**. Service was restored via immediate rollback.

---

## Impact

| Metric | Value |
|--------|-------|
| Duration | 8 minutes (14:52–15:00 UTC) |
| Users affected | ~4,200 (100% of order placements) |
| Revenue impact | ~$1,680 (~$12,600/hr order rate) |
| Error rate peak | 100% |
| Services degraded | order-service (down), api-gateway (partial), notification-svc (starved) |
| Tickets created | INC0048291 (auto-created via ServiceNow connector) |

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 14:43 | order-service v2.4.1 build passes CI — pgxpool v3 migration included |
| 14:52 | Deployment of order-service:v2.4.1 completes (GitHub Actions) |
| 14:52 | First pod crash — \`FATAL: connection pool exhausted\` |
| 14:53 | **PodCrashLoopBackOff alert fires** → Slack #incidents + ServiceNow ticket |
| 14:53 | **HighErrorRate alert fires** — 97.8% error rate on order-service |
| 14:54 | On-call SRE acknowledges — begins investigation |
| 14:55 | OpsBrain RCA identifies deployment as root cause (pgxpool pool size) |
| 14:57 | Rollback initiated: \`kubectl rollout undo deployment/order-service\` |
| 14:59 | order-service v2.4.0 pods running and healthy |
| 15:00 | All alerts resolved · error rate < 0.1% |

---

## Root Cause (5-Whys)

1. **Why** did order-service crash? → DB connection pool exhausted on startup
2. **Why** did the pool exhaust? → Pool size was 2 (pgxpool v3 new default), not 10
3. **Why** was pool size 2? → Developer assumed pgxpool v3 inherited v2 defaults — it doesn't
4. **Why** wasn't this caught in staging? → Staging DB has 1 connection max — pool of 2 never exhausts
5. **Why** wasn't there a pre-deploy connection test? → No DB connection health check in deployment pipeline

---

## What Went Well

- Alert fired within 60 seconds of first crash ✓
- ServiceNow ticket created automatically via OpsBrain connector ✓
- RCA completed in under 3 minutes using OpsBrain AI analysis ✓
- Rollback completed in under 2 minutes ✓
- Total MTTR: **8 minutes** (team SLO: < 30 min) ✓

## What Went Wrong

- No automated pool size validation in staging
- pgxpool v3 migration PR had no performance/connection testing requirement
- orders-db PVC issue (separate pre-existing bug) went undetected

---

## Action Items

| Priority | Action | Owner | Due |
|----------|--------|-------|-----|
| P0 | Add DB connection pool health check to deployment pipeline | Platform SRE | May 1 |
| P0 | Fix orders-db PVC mount issue (separate incident) | Storage team | Apr 25 |
| P1 | Set staging DB to match production connection limits | Infra | Apr 30 |
| P1 | Add \`pg_pool_available < 3\` alert to Prometheus | Observability | Apr 28 |
| P2 | Require load testing for all DB-touching deployments | Engineering Leads | May 15 |
| P2 | Document pgxpool v2→v3 migration guide in Confluence | Auth: @dev team | May 7 |`,

  predictions: {
    predictions: [
      {
        service: "payment-service",
        risk_type: "memory_exhaustion",
        confidence_pct: 91,
        eta_minutes: 38,
        current_value: 847,
        threshold_value: 1024,
        unit: "Mi",
        trend_description: "Memory growing at 8.4 Mi/min for the past 52 minutes — consistent leak pattern. Linear projection hits OOM limit in ~38 minutes.",
        recommended_action: "Restart payment-service pods now (rolling) OR increase memory limit to 2Gi and open memory leak investigation with heap profiler.",
      },
      {
        service: "auth-service",
        risk_type: "latency_degradation",
        confidence_pct: 78,
        eta_minutes: 65,
        current_value: 312,
        threshold_value: 500,
        unit: "ms p99",
        trend_description: "p99 latency trending up 12ms/5min for the past hour. Correlates with Redis cache hit rate dropping from 94% → 71%. At current trend, SLO breach in ~65 minutes.",
        recommended_action: "Check Redis memory usage — likely near eviction threshold. Run MEMORY DOCTOR in redis-cli. Consider increasing Redis maxmemory or flushing stale session keys.",
      },
      {
        service: "notification-svc",
        risk_type: "error_rate_spike",
        confidence_pct: 74,
        eta_minutes: 20,
        current_value: 3.8,
        threshold_value: 5.0,
        unit: "% errors",
        trend_description: "Error rate crept from 0.2% → 3.8% in the last 25 minutes. Pattern matches upstream order-service dependency failures — notification-svc retries are amplifying load.",
        recommended_action: "Order-service recovery (already in progress) should resolve this automatically. If not resolved in 5 minutes, circuit-break the order-service dependency in notification-svc config.",
      },
    ],
    services_analyzed: 5,
    highest_risk_service: "payment-service",
    analysis_timestamp: _ago(2),
  },

  capacity: {
    overall_health_score: 58,
    runway: { cpu_days: 21, memory_days: 3, pod_slots_days: 14 },
    bottlenecks: [
      { resource: "node-2 memory", current_pct: 92, projected_exhaustion_days: 3, recommendation: "Add 1 node to ng-general-purpose OR evict elasticsearch-data pod (2Gi) to node-3" },
      { resource: "payment-service pods (memory leak)", current_pct: 83, projected_exhaustion_days: 1, recommendation: "Rolling restart payment-service — memory leak fix in v1.9.7 release planned tomorrow" },
    ],
    hpa_risks: [
      { service: "payment-service", current_replicas: 7, max_replicas: 10, pct_of_max: 70, risk: "high" },
      { service: "auth-service", current_replicas: 3, max_replicas: 8, pct_of_max: 38, risk: "low" },
    ],
    recommendations: [
      "Add 1 node to ng-general-purpose before node-2 memory exhaustion (< 3 days)",
      "Rolling restart payment-service pods to clear memory leak — safe, zero downtime",
      "Enable cluster autoscaler scale-down — 2 idle nodes on node-3 costing $640/mo",
      "Resize elasticsearch-data PVC from 2TB → 300GB (only 180GB used)",
    ],
    namespace: "production",
    forecast_timestamp: _ago(2),
  },
};

// ─── Types ────────────────────────────────────────────────────────
interface User { id: string; username: string; email: string; full_name: string; role: string; team: string; }
interface AuthState { token: string; user: User | null; }
interface Alert { name: string; severity: string; service: string; message: string; firing_since: string; }
interface ServiceHealth { name: string; status: string; uptime_pct: number; }
interface Connector { id: string; name: string; type: string; enabled: boolean; healthy?: boolean; error?: string; }

// ─── API helper ───────────────────────────────────────────────────
function useApi(token: string) {
  const get = useCallback(async (path: string) => {
    const r = await fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } });
    if (r.status === 401) throw new Error("unauthorized");
    return r.json();
  }, [token]);

  const post = useCallback(async (path: string, body?: object) => {
    const r = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (r.status === 401) throw new Error("unauthorized");
    return r.json();
  }, [token]);

  const del = useCallback(async (path: string) => {
    const r = await fetch(`${API}${path}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    return r.json();
  }, [token]);

  return { get, post, del };
}

// ─── Small reusables ──────────────────────────────────────────────
function StatusDot({ status }: { status: string }) {
  const c: Record<string, string> = {
    healthy: "bg-green-400", down: "bg-red-400 animate-pulse",
    degraded: "bg-amber-400 animate-pulse", pending: "bg-purple-400",
  };
  return <span className={`inline-block w-2 h-2 rounded-full ${c[status] ?? "bg-slate-500"}`} />;
}

function SeverityBadge({ sev }: { sev: string }) {
  const s: Record<string, string> = {
    critical: "bg-red-950 text-red-400 border border-red-800",
    warning: "bg-amber-950 text-amber-400 border border-amber-800",
    info: "bg-blue-950 text-blue-400 border border-blue-800",
  };
  return <span className={`px-2 py-0.5 rounded text-xs font-mono uppercase ${s[sev] ?? "bg-slate-800 text-slate-400"}`}>{sev}</span>;
}

function RoleBadge({ role }: { role: string }) {
  const s: Record<string, string> = {
    admin: "bg-purple-900/60 text-purple-300 border border-purple-700",
    sre: "bg-blue-900/60 text-blue-300 border border-blue-700",
    finops: "bg-green-900/60 text-green-300 border border-green-700",
    viewer: "bg-slate-800 text-slate-400 border border-slate-600",
  };
  return <span className={`px-2 py-0.5 rounded text-xs font-mono ${s[role] ?? s.viewer}`}>{role}</span>;
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`bg-[#161b27] border border-[#1e2535] rounded-xl ${className}`}>{children}</div>;
}

function Spinner() {
  return <div className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />;
}

// ─── Login page ───────────────────────────────────────────────────
function LoginPage({ onLogin }: { onLogin: (auth: AuthState) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const r = await fetch(`${API}/auth/login?username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`, { method: "POST" });
      if (!r.ok) { setError("Invalid credentials"); return; }
      const data = await r.json();
      onLogin({ token: data.access_token, user: data.user });
    } catch {
      setError("Cannot connect to OpsBrain backend");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0f1117] flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-2">
            <Brain size={28} className="text-indigo-400" />
            <span className="text-2xl font-bold text-white">OpsBrain</span>
          </div>
          <p className="text-slate-500 text-sm">AI-Native AIOps Platform</p>
        </div>

        <Card className="p-6">
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-xs text-slate-400 block mb-1.5">Username</label>
              <input
                value={username} onChange={e => setUsername(e.target.value)}
                className="w-full bg-[#0f1117] border border-[#1e2535] focus:border-indigo-600/50 rounded-lg px-3 py-2.5 text-sm text-slate-200 outline-none transition-colors"
                placeholder="username" autoFocus
              />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  value={password} onChange={e => setPassword(e.target.value)}
                  className="w-full bg-[#0f1117] border border-[#1e2535] focus:border-indigo-600/50 rounded-lg px-3 py-2.5 pr-10 text-sm text-slate-200 outline-none transition-colors"
                  placeholder="password"
                />
                <button type="button" onClick={() => setShowPw(p => !p)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                  {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>
            {error && <p className="text-xs text-red-400 bg-red-950/50 border border-red-800/50 rounded-lg px-3 py-2">{error}</p>}
            <button type="submit" disabled={loading}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-medium flex items-center justify-center gap-2 transition-colors">
              {loading ? <><Spinner /> Signing in…</> : "Sign In"}
            </button>
          </form>
        </Card>

        <p className="text-center text-xs text-slate-600 mt-4">
          Plug-and-play deployment · Any cloud · Air-gap ready
        </p>
      </div>
    </div>
  );
}

// ─── Main app ─────────────────────────────────────────────────────
export default function App() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [setupDone, setSetupDone] = useState<boolean | null>(null); // null = checking

  // 1. Check if LLM is configured before showing login
  useEffect(() => {
    async function checkSetup() {
      try {
        const r = await fetch(`${API}/setup/status`);
        const data = await r.json();
        setSetupDone(!data.setup_required);
      } catch {
        // Backend not reachable — still show setup page
        setSetupDone(false);
      }
    }
    checkSetup();
  }, []);

  // 2. Restore saved session
  useEffect(() => {
    const saved = localStorage.getItem("opsbrain_auth");
    if (saved) {
      try { setAuth(JSON.parse(saved)); } catch {}
    }
  }, []);

  function handleLogin(a: AuthState) {
    setAuth(a);
    localStorage.setItem("opsbrain_auth", JSON.stringify(a));
  }

  function handleLogout() {
    setAuth(null);
    localStorage.removeItem("opsbrain_auth");
  }

  // Still checking
  if (setupDone === null) {
    return (
      <div className="min-h-screen bg-[#0f1117] flex items-center justify-center">
        <div className="flex items-center gap-3 text-slate-500">
          <Brain size={20} className="text-indigo-400 animate-pulse" />
          <span className="text-sm">Connecting to OpsBrain…</span>
        </div>
      </div>
    );
  }

  // LLM not configured — show setup instructions
  if (!setupDone) {
    return <SetupPage apiUrl={API} onDone={() => setSetupDone(true)} />;
  }

  // Ready — show login or dashboard
  if (!auth) return <LoginPage onLogin={handleLogin} />;
  return <Dashboard auth={auth} onLogout={handleLogout} onUnauthorized={handleLogout} />;
}

// ─── Dashboard shell ──────────────────────────────────────────────
function Dashboard({ auth, onLogout, onUnauthorized }: { auth: AuthState; onLogout: () => void; onUnauthorized: () => void }) {
  type Tab = "dashboard" | "predict" | "checkouts" | "knowledge" | "chat" | "cost" | "postmortem" | "connectors" | "environments" | "admin";
  const [tab, setTab] = useState<Tab>("dashboard");
  const { get, post, del } = useApi(auth.token);
  const isAdmin = auth.user?.role === "admin";

  const navItems: { id: Tab; icon: React.ElementType; label: string; adminOnly?: boolean }[] = [
    { id: "dashboard",    icon: Activity,      label: "Dashboard" },
    { id: "predict",      icon: TrendingUp,    label: "Predict" },
    { id: "checkouts",    icon: CheckCircle2,  label: "Checkouts" },
    { id: "knowledge",    icon: FileText,      label: "Knowledge Base" },
    { id: "chat",         icon: MessageSquare, label: "AI Assistant" },
    { id: "cost",         icon: DollarSign,    label: "Cost Optimizer" },
    { id: "postmortem",   icon: FileText,      label: "Post-Mortems" },
    { id: "environments", icon: Server,        label: "Environments" },
    { id: "connectors",   icon: Plug,          label: "Connectors" },
    { id: "admin",        icon: Shield,        label: "Admin", adminOnly: true },
  ];

  const apiCall = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    try { return await fn(); }
    catch (e: any) {
      if (e?.message === "unauthorized") { onUnauthorized(); }
      return null;
    }
  }, [onUnauthorized]);

  // Memoized typed wrappers — stable references prevent useEffect loops in child components
  const ag = useCallback((p: string) => apiCall(() => get(p)), [apiCall, get]);
  const ap = useCallback((p: string, b?: object) => apiCall(() => post(p, b)), [apiCall, post]);
  const ad = useCallback((p: string) => apiCall(() => del(p)), [apiCall, del]);

  return (
    <div className="flex h-screen overflow-hidden bg-[#0f1117]">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-[#0b0e16] border-r border-[#1e2535] flex flex-col">
        <div className="p-4 border-b border-[#1e2535]">
          <div className="flex items-center gap-2">
            <Brain size={20} className="text-indigo-400" />
            <span className="font-bold text-white">OpsBrain</span>
          </div>
          <p className="text-xs text-slate-600 mt-0.5">AI-Native AIOps</p>
        </div>

        <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
          {navItems.filter(n => !n.adminOnly || isAdmin).map(({ id, icon: Icon, label }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                tab === id
                  ? "bg-indigo-600/20 text-indigo-300 border border-indigo-600/30"
                  : "text-slate-400 hover:text-slate-200 hover:bg-[#161b27]"
              }`}>
              <Icon size={15} /> {label}
            </button>
          ))}
        </nav>

        {/* User info */}
        <div className="p-3 border-t border-[#1e2535]">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 bg-indigo-600/30 border border-indigo-600/40 rounded-full flex items-center justify-center">
              <User size={13} className="text-indigo-300" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-slate-300 truncate">{auth.user?.full_name}</div>
              <RoleBadge role={auth.user?.role ?? "viewer"} />
            </div>
          </div>
          <button onClick={onLogout}
            className="w-full flex items-center gap-2 px-2 py-1.5 text-xs text-slate-500 hover:text-red-400 hover:bg-red-950/20 rounded-lg transition-colors">
            <LogOut size={12} /> Sign out
          </button>
        </div>
      </aside>

      {/* Content */}
      <main className="flex-1 overflow-auto">
        {tab === "dashboard"    && <DashboardTab     get={ag} post={ap} />}
        {tab === "predict"      && <PredictiveTab    get={ag} post={ap} />}
        {tab === "chat"         && <ChatTab           get={ag} post={ap} role={auth.user?.role ?? "viewer"} />}
        {tab === "cost"         && <CostTab           get={ag} post={ap} />}
        {tab === "postmortem"   && <PostMortemTab     get={ag} post={ap} />}
        {tab === "environments" && <EnvironmentsPage  get={ag} post={ap} del={ad} isAdmin={isAdmin} />}
        {tab === "connectors"   && <ConnectorsTab     get={ag} post={ap} del={ad} isAdmin={isAdmin} />}
        {tab === "checkouts"    && <CheckoutsTab get={ag} post={ap} del={ad} />}
        {tab === "knowledge"    && <KnowledgeTab get={ag} post={ap} del={ad} isAdmin={isAdmin} />}
        {tab === "admin"        && isAdmin && <AdminTab get={ag} post={ap} />}
      </main>
    </div>
  );
}

// ─── Chat tab ─────────────────────────────────────────────────────
function ChatTab({ get, post, role }: { get: any; post: any; role: string }) {
  const [messages, setMessages] = useState<{ role: string; content: string; thinking?: string }[]>(DEMO.chatMessages);
  const [input, setInput] = useState("");
  const [agent, setAgent] = useState("sre");
  const [useThinking, setUseThinking] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showThinking, setShowThinking] = useState<Record<number, boolean>>({});
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const agentOptions = [
    { value: "sre", label: "AI-SRE", allowed: ["admin", "sre"] },
    { value: "finops", label: "AI-FinOps", allowed: ["admin", "finops"] },
    { value: "k8s", label: "AI-K8s", allowed: ["admin", "sre"] },
    { value: "postmortem", label: "Post-Mortem", allowed: ["admin", "sre"] },
  ].filter(a => a.allowed.includes(role));

  async function send() {
    if (!input.trim() || loading) return;
    const msg = input.trim();
    setInput("");
    setMessages(p => [...p, { role: "user", content: msg }]);
    setLoading(true);
    const r = await post("/api/v1/chat", { agent_type: agent, message: msg, use_thinking: useThinking, stream: false });
    setMessages(p => [...p, { role: "assistant", content: r?.text ?? "No response.", thinking: r?.thinking ?? "" }]);
    setLoading(false);
  }

  const suggestions = [
    "Why is order-service crashing?",
    "What's wasting the most money?",
    "Scale payment-service to 5 replicas",
    "Generate a post-mortem for today",
  ];

  return (
    <div className="flex flex-col h-full p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <MessageSquare size={18} className="text-indigo-400" /> AI Operations Assistant
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">Chat with your infrastructure in plain English</p>
        </div>
        <div className="flex items-center gap-3">
          <select value={agent} onChange={e => setAgent(e.target.value)}
            className="bg-[#161b27] border border-[#1e2535] text-slate-300 text-xs rounded-lg px-3 py-1.5">
            {agentOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
            <input type="checkbox" checked={useThinking} onChange={e => setUseThinking(e.target.checked)} className="rounded" />
            <Brain size={12} className="text-indigo-400" /> Extended thinking
          </label>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 mb-4">
        {messages.length === 0 && (
          <div className="text-center py-12">
            <Brain size={36} className="text-indigo-600/30 mx-auto mb-3" />
            <p className="text-slate-500 text-sm mb-4">Ask anything about your infrastructure</p>
            <div className="grid grid-cols-2 gap-2 max-w-lg mx-auto">
              {suggestions.map((q, i) => (
                <button key={i} onClick={() => setInput(q)}
                  className="text-left text-xs bg-[#161b27] hover:bg-[#1a2236] border border-[#1e2535] rounded-lg p-3 text-slate-400 hover:text-slate-200 transition-colors">
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-3xl rounded-xl p-4 ${m.role === "user" ? "bg-indigo-600/20 border border-indigo-600/30" : "bg-[#161b27] border border-[#1e2535]"}`}>
              {m.role === "assistant" && m.thinking && (
                <div className="mb-3">
                  <button onClick={() => setShowThinking(p => ({ ...p, [i]: !p[i] }))}
                    className="flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 mb-2">
                    <Brain size={11} /> {showThinking[i] ? "Hide" : "Show"} AI reasoning
                  </button>
                  {showThinking[i] && (
                    <div className="thinking-block bg-[#0b0e16] rounded-lg p-3 text-xs text-slate-400 font-mono whitespace-pre-wrap max-h-40 overflow-y-auto">
                      {m.thinking}
                    </div>
                  )}
                </div>
              )}
              <div className="prose-ops text-sm"><ReactMarkdown>{m.content}</ReactMarkdown></div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-[#161b27] border border-[#1e2535] rounded-xl p-4 flex items-center gap-2">
              <div className="flex gap-1">
                {[0, 1, 2].map(n => (
                  <span key={n} className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: `${n * 0.15}s` }} />
                ))}
              </div>
              <span className="text-xs text-slate-500">{useThinking ? "Thinking deeply…" : "Analyzing…"}</span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="flex gap-2">
        <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
          placeholder={`Ask AI-${agent.toUpperCase()}…`}
          className="flex-1 bg-[#161b27] border border-[#1e2535] focus:border-indigo-600/50 text-slate-200 rounded-xl px-4 py-3 text-sm outline-none transition-colors placeholder:text-slate-600"
        />
        <button onClick={send} disabled={loading || !input.trim()}
          className="px-5 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white rounded-xl text-sm font-medium transition-colors flex items-center gap-2">
          <ChevronRight size={15} /> Send
        </button>
      </div>
    </div>
  );
}

// ─── Cost tab ─────────────────────────────────────────────────────
function CostTab({ get, post }: { get: any; post: any }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(DEMO.costAnalysis);

  async function analyze() {
    setLoading(true); setResult("");
    const r = await post("/api/v1/cost/analyze", { cloud: "all" });
    setResult(r?.analysis ?? "No analysis returned.");
    setLoading(false);
  }

  const waste = [
    { name: "Idle RDS", waste: 1520 }, { name: "Oversized EC2", waste: 480 },
    { name: "Node Groups", waste: 960 }, { name: "Unused PVCs", waste: 182 },
    { name: "Log Volume", waste: 820 }, { name: "HPA nodes", waste: 640 },
  ];

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <DollarSign size={18} className="text-green-400" /> AI Cloud Cost Optimizer
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">Identify waste · generate rightsizing PRs · save up to 60%</p>
        </div>
        <button onClick={analyze} disabled={loading}
          className="px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white rounded-lg text-sm flex items-center gap-2 transition-colors">
          {loading ? <><Spinner /> Analyzing…</> : <><Brain size={13} /> Run Analysis</>}
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Monthly Spend", value: "$34.8k", sub: "+10.7% MoM" },
          { label: "Identified Waste", value: "$7.2k/mo", sub: "21% of total spend" },
          { label: "Quick Wins", value: "$4.6k/mo", sub: "Low risk, high savings" },
        ].map(({ label, value, sub }, i) => (
          <Card key={i} className="p-4">
            <div className="text-xs text-slate-500 uppercase tracking-wider">{label}</div>
            <div className="text-xl font-semibold text-white mt-0.5">{value}</div>
            <div className="text-xs text-green-400 mt-0.5">{sub}</div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-5">
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-white mb-4">Waste by Category ($/month)</h2>
          <div className="space-y-3">
            {waste.map((d, i) => (
              <div key={i}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-400">{d.name}</span>
                  <span className="text-green-400 font-mono">${d.waste}/mo</span>
                </div>
                <div className="h-1.5 bg-[#1e2535] rounded-full overflow-hidden">
                  <div className="h-full bg-green-500/60 rounded-full transition-all" style={{ width: `${(d.waste / 1600) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-semibold text-white mb-3">AI Analysis</h2>
          {result ? (
            <div className="prose-ops text-sm max-h-80 overflow-y-auto"><ReactMarkdown>{result}</ReactMarkdown></div>
          ) : (
            <div className="flex flex-col items-center justify-center h-48 text-slate-600 text-sm">
              <DollarSign size={28} className="mb-2 opacity-30" />
              Click "Run Analysis" to identify savings
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

// ─── Post-mortem tab ──────────────────────────────────────────────
function PostMortemTab({ get, post }: { get: any; post: any }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(DEMO.postMortem);

  const incident = {
    title: "order-service CrashLoopBackOff — DB connection pool exhaustion",
    service: "order-service", severity: "P1 (SEV2)",
    started_at: new Date(Date.now() - 9 * 60000).toISOString(),
    resolved_at: new Date().toISOString(),
    detected_by: "PodCrashLoopBackOff alert", resolved_by: "On-call SRE",
    affected_users: 4200, error_rate_peak_pct: 100,
    timeline_events: [
      { time: "-9m", event: "Deployment of order-service v2.4.1 completed" },
      { time: "-8m", event: "PodCrashLoopBackOff alert fired" },
      { time: "-7m", event: "HighErrorRate alert fired — 97.8% errors" },
      { time: "-5m", event: "Team identified recent deployment as cause" },
      { time: "-3m", event: "Rollback initiated" },
      { time: "-1m", event: "Service recovered" },
    ],
    root_cause_notes: "Migration to connection pool v3 reduced pool size from 10 to 2.",
    actions_taken: ["kubectl rollout undo deployment/order-service -n production"],
  };

  async function generate() {
    setLoading(true); setResult("");
    const r = await post("/api/v1/postmortem/generate", incident);
    setResult(r?.document ?? "Generation failed.");
    setLoading(false);
  }

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <FileText size={18} className="text-purple-400" /> Auto Post-Mortem Generator
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">Generate blameless post-mortems instantly from incident data</p>
        </div>
        <button onClick={generate} disabled={loading}
          className="px-4 py-2 bg-purple-700 hover:bg-purple-600 disabled:opacity-50 text-white rounded-lg text-sm flex items-center gap-2">
          {loading ? <><Spinner /> Generating…</> : <><Brain size={13} /> Generate Post-Mortem</>}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-5">
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Incident Data</h2>
          <div className="space-y-1.5">
            {[["Title", incident.title], ["Service", incident.service], ["Severity", incident.severity],
              ["Duration", "~8 minutes"], ["Affected Users", incident.affected_users.toLocaleString()],
              ["Peak Error Rate", `${incident.error_rate_peak_pct}%`]].map(([k, v], i) => (
              <div key={i} className="flex gap-2 text-xs">
                <span className="text-slate-500 w-32 flex-shrink-0">{k}:</span>
                <span className="text-slate-300">{v}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 pt-3 border-t border-[#1e2535]">
            <div className="text-xs text-slate-500 mb-2 uppercase tracking-wider">Timeline</div>
            <div className="space-y-1">
              {incident.timeline_events.map((e, i) => (
                <div key={i} className="flex gap-2 text-xs">
                  <span className="text-indigo-400 font-mono w-8 flex-shrink-0">{e.time}</span>
                  <span className="text-slate-400">{e.event}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Generated Post-Mortem</h2>
          {result ? (
            <div className="prose-ops text-sm max-h-[480px] overflow-y-auto"><ReactMarkdown>{result}</ReactMarkdown></div>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 text-slate-600 text-sm">
              <FileText size={28} className="mb-2 opacity-30" />
              Click "Generate Post-Mortem" to create a blameless report
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

// ─── Predictive Intelligence tab ──────────────────────────────────
function PredictiveTab({ get, post }: { get: any; post: any }) {
  const [anomalies, setAnomalies] = useState<any>(DEMO.predictions);
  const [capacity, setCapacity] = useState<any>(DEMO.capacity);
  const [loadingA, setLoadingA] = useState(false);
  const [loadingC, setLoadingC] = useState(false);
  const [sweeping, setSweeping] = useState(false);
  const [sweepResult, setSweepResult] = useState<any>({ critical_count: 1, urgent_actions: ["Restart payment-service pods immediately — memory exhaustion in ~38 minutes"] });

  async function runAnomalyDetection() {
    setLoadingA(true);
    const r = await get("/api/v1/predict/anomalies");
    if (r) setAnomalies(r);
    setLoadingA(false);
  }

  async function runCapacityForecast() {
    setLoadingC(true);
    const r = await get("/api/v1/predict/capacity");
    if (r) setCapacity(r);
    setLoadingC(false);
  }

  async function runFullSweep() {
    setSweeping(true);
    setSweepResult(null);
    const r = await get("/api/v1/predict/sweep");
    if (r) {
      setSweepResult(r);
      setAnomalies(r.anomaly_predictions);
      setCapacity(r.capacity_forecast);
    }
    setSweeping(false);
  }

  const predictions: any[] = anomalies?.predictions ?? [];
  const bottlenecks: any[] = capacity?.bottlenecks ?? [];
  const runway = capacity?.runway;

  const riskColor = (confidence: number) => {
    if (confidence >= 85) return "text-red-400";
    if (confidence >= 70) return "text-amber-400";
    return "text-yellow-300";
  };

  const etaLabel = (eta: number) => {
    if (eta < 15) return `~${eta}m (imminent)`;
    if (eta < 60) return `~${eta}m`;
    return `~${Math.round(eta / 60)}h`;
  };

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <TrendingUp size={18} className="text-indigo-400" /> Predictive Intelligence
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Detect anomalies before they become incidents · Forecast capacity limits
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={runAnomalyDetection} disabled={loadingA || sweeping}
            className="px-3 py-2 bg-[#161b27] hover:bg-[#1a2236] border border-[#1e2535] text-slate-300 rounded-lg text-xs flex items-center gap-1.5 transition-colors disabled:opacity-40">
            {loadingA ? <><Spinner /> Detecting…</> : <><Zap size={12} /> Anomaly Scan</>}
          </button>
          <button onClick={runCapacityForecast} disabled={loadingC || sweeping}
            className="px-3 py-2 bg-[#161b27] hover:bg-[#1a2236] border border-[#1e2535] text-slate-300 rounded-lg text-xs flex items-center gap-1.5 transition-colors disabled:opacity-40">
            {loadingC ? <><Spinner /> Forecasting…</> : <><TrendingUp size={12} /> Capacity Forecast</>}
          </button>
          <button onClick={runFullSweep} disabled={sweeping || loadingA || loadingC}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-sm flex items-center gap-2 transition-colors">
            {sweeping ? <><Spinner /> Sweeping…</> : <><Brain size={13} /> Full Sweep</>}
          </button>
        </div>
      </div>

      {/* Sweep summary */}
      {sweepResult && (
        <div className={`flex items-center gap-3 p-3 rounded-xl border text-sm ${
          sweepResult.critical_count > 0
            ? "bg-red-950/30 border-red-800/40 text-red-300"
            : "bg-green-950/30 border-green-800/40 text-green-300"
        }`}>
          {sweepResult.critical_count > 0
            ? <AlertCircle size={16} className="flex-shrink-0" />
            : <CheckCircle2 size={16} className="flex-shrink-0" />}
          <span>
            {sweepResult.critical_count > 0
              ? `${sweepResult.critical_count} imminent risk(s) detected — action required within 30 minutes`
              : "No imminent risks detected across all services"}
          </span>
        </div>
      )}

      {/* Empty state */}
      {!anomalies && !capacity && !sweeping && !loadingA && !loadingC && (
        <Card className="flex flex-col items-center justify-center py-16">
          <TrendingUp size={36} className="text-indigo-600/30 mb-3" />
          <p className="text-slate-500 text-sm mb-1">No predictions loaded yet</p>
          <p className="text-slate-600 text-xs">Run "Full Sweep" to analyse all services proactively</p>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-5">
        {/* Anomaly predictions */}
        {(anomalies || loadingA) && (
          <Card className="p-4">
            <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <Zap size={14} className="text-amber-400" /> Anomaly Predictions
              {anomalies && (
                <span className="ml-auto text-xs text-slate-500">
                  {predictions.length} signal{predictions.length !== 1 ? "s" : ""}
                </span>
              )}
            </h2>
            {loadingA ? (
              <div className="flex items-center justify-center py-10"><Spinner /></div>
            ) : predictions.length === 0 ? (
              <div className="flex flex-col items-center py-8 text-slate-600 text-xs">
                <CheckCircle2 size={24} className="mb-2 text-green-600" />
                No anomalies predicted — all services look stable
              </div>
            ) : (
              <div className="space-y-3">
                {predictions.map((p: any, i: number) => (
                  <div key={i} className="p-3 bg-[#0f1117] rounded-lg border border-[#1e2535]">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-mono text-slate-300">{p.service}</span>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-semibold ${riskColor(p.confidence_pct)}`}>
                          {p.confidence_pct}% confidence
                        </span>
                        <span className="text-xs text-slate-500 font-mono">{etaLabel(p.eta_minutes)}</span>
                      </div>
                    </div>
                    <div className="text-xs text-slate-500 mb-2 uppercase tracking-wider">{p.risk_type?.replace(/_/g, " ")}</div>
                    <p className="text-xs text-slate-400 mb-2">{p.trend_description}</p>
                    <div className="flex items-center gap-2 p-2 bg-indigo-950/30 border border-indigo-800/30 rounded-lg">
                      <ChevronRight size={11} className="text-indigo-400 flex-shrink-0" />
                      <span className="text-xs text-indigo-300">{p.recommended_action}</span>
                    </div>
                    {p.current_value !== undefined && p.threshold_value !== undefined && (
                      <div className="mt-2">
                        <div className="flex justify-between text-xs text-slate-600 mb-0.5">
                          <span>Current: {p.current_value}{p.unit ?? ""}</span>
                          <span>Threshold: {p.threshold_value}{p.unit ?? ""}</span>
                        </div>
                        <div className="h-1 bg-[#1e2535] rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${p.confidence_pct >= 85 ? "bg-red-500" : "bg-amber-500"}`}
                            style={{ width: `${Math.min(100, (p.current_value / p.threshold_value) * 100)}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}

        {/* Capacity forecast */}
        {(capacity || loadingC) && (
          <Card className="p-4">
            <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <TrendingUp size={14} className="text-indigo-400" /> Capacity Forecast
              {capacity?.overall_health_score !== undefined && (
                <span className={`ml-auto text-sm font-bold ${
                  capacity.overall_health_score >= 80 ? "text-green-400"
                    : capacity.overall_health_score >= 60 ? "text-amber-400"
                    : "text-red-400"
                }`}>
                  {capacity.overall_health_score}/100
                </span>
              )}
            </h2>

            {loadingC ? (
              <div className="flex items-center justify-center py-10"><Spinner /></div>
            ) : (
              <div className="space-y-4">
                {/* Runway */}
                {runway && (
                  <div>
                    <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">Resource Runway</div>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { label: "CPU", days: runway.cpu_days },
                        { label: "Memory", days: runway.memory_days },
                        { label: "Pod Slots", days: runway.pod_slots_days },
                      ].map(({ label, days }) => (
                        <div key={label} className={`p-2 rounded-lg text-center border ${
                          days < 7 ? "border-red-800/40 bg-red-950/20"
                            : days < 14 ? "border-amber-800/40 bg-amber-950/20"
                            : "border-green-800/40 bg-green-950/20"
                        }`}>
                          <div className={`text-lg font-bold ${
                            days < 7 ? "text-red-400" : days < 14 ? "text-amber-400" : "text-green-400"
                          }`}>{days}d</div>
                          <div className="text-xs text-slate-500">{label}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Bottlenecks */}
                {bottlenecks.length > 0 && (
                  <div>
                    <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">Bottlenecks</div>
                    <div className="space-y-2">
                      {bottlenecks.map((b: any, i: number) => (
                        <div key={i} className="p-2 bg-[#0f1117] rounded-lg border border-[#1e2535]">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-mono text-slate-300">{b.resource}</span>
                            <span className="text-xs text-red-400">{b.projected_exhaustion_days}d left</span>
                          </div>
                          <div className="h-1.5 bg-[#1e2535] rounded-full overflow-hidden mb-1">
                            <div className="h-full bg-red-500 rounded-full" style={{ width: `${b.current_pct}%` }} />
                          </div>
                          <p className="text-xs text-slate-500">{b.recommendation}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recommendations */}
                {capacity?.recommendations?.length > 0 && (
                  <div>
                    <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">Actions</div>
                    <div className="space-y-1.5">
                      {capacity.recommendations.map((r: string, i: number) => (
                        <div key={i} className="flex gap-2 text-xs text-slate-400">
                          <ChevronRight size={12} className="text-indigo-400 flex-shrink-0 mt-0.5" />
                          {r}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

// ─── Checkouts tab ────────────────────────────────────────────────

const CHECKOUT_TYPES = [
  { value: "infra_health",    label: "Infrastructure Health", desc: "Pod health, node pressure, alerts, deployments",    color: "text-indigo-400"  },
  { value: "cost_review",     label: "Cost Review",           desc: "Cloud spend, waste, anomalies, rightsizing",        color: "text-green-400"   },
  { value: "capacity_review", label: "Capacity Planning",     desc: "Resource runway, HPA headroom, scheduling pressure", color: "text-amber-400"   },
  { value: "slo_review",      label: "SLO Review",            desc: "Error rates, latency, uptime, alert volume",        color: "text-blue-400"    },
  { value: "incident_review", label: "Incident Review",       desc: "Active incidents, MTTR, recurring patterns",        color: "text-red-400"     },
  { value: "custom",          label: "Custom",                desc: "Your own Claude prompt for any operational question", color: "text-purple-400" },
];
const FREQUENCIES = ["daily","weekly","monthly","quarterly","half-yearly","yearly"];
const STATUS_STYLES: Record<string, { cls: string; icon: string }> = {
  passed:  { cls: "text-green-400 bg-green-950/40 border-green-800/40",  icon: "✅" },
  warning: { cls: "text-amber-400 bg-amber-950/40 border-amber-800/40",  icon: "⚠️" },
  failed:  { cls: "text-red-400   bg-red-950/40   border-red-800/40",    icon: "🔴" },
  pending: { cls: "text-slate-400 bg-slate-800/40 border-slate-700/40",  icon: "⏳" },
  running: { cls: "text-indigo-400 bg-indigo-950/40 border-indigo-800/40", icon: "⚙️" },
};

// next Monday 09:00, next 1st of month 09:00, etc.
function _nextWeekday(day: number, hour: number) {
  const d = new Date(); d.setUTCHours(hour, 0, 0, 0);
  const diff = (day - d.getUTCDay() + 7) % 7 || 7;
  d.setUTCDate(d.getUTCDate() + diff);
  return d.toISOString();
}
function _nextMonthDay(dayOfMonth: number, hour: number) {
  const d = new Date(); d.setUTCDate(dayOfMonth); d.setUTCHours(hour, 0, 0, 0);
  if (d <= new Date()) d.setUTCMonth(d.getUTCMonth() + 1);
  return d.toISOString();
}
function _nextDailyAt(hour: number) {
  const d = new Date(); d.setUTCHours(hour, 0, 0, 0);
  if (d <= new Date()) d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString();
}
function _nextQuarterAt(hour: number) {
  const d = new Date(); d.setUTCHours(hour,0,0,0);
  d.setUTCMonth(d.getUTCMonth() + 3);
  return d.toISOString();
}

const DEMO_CHECKOUTS = [
  {
    id: "co_weekly_infra", name: "Weekly Infrastructure Health",
    description: "Full K8s + AWS health sweep — pods, nodes, alerts, deployments",
    checkout_type: "infra_health", frequency: "weekly",
    scheduled_hour: 9, scheduled_weekday: 1, scheduled_day: 1,
    enabled: true,
    audience_emails: ["platform-sre@company.com"], audience_slack: ["#ops-reports"],
    report_format: "markdown", namespace: "production", custom_prompt: "",
    created_at: _ago(30 * 24 * 60), updated_at: _ago(2 * 60),
    last_run_at: _ago(2 * 60), next_run_at: _nextWeekday(1, 9),
    last_status: "passed", run_count: 12,
    last_summary: "Health score 74/100. All 14 pods healthy. node-2 memory at 92% — 3-day runway before OOM. No AWS CloudWatch alarms.",
  },
  {
    id: "co_monthly_cost", name: "Monthly Cost Review",
    description: "AWS Cost Explorer + rightsizing — sent to FinOps and VP Eng on 1st of month",
    checkout_type: "cost_review", frequency: "monthly",
    scheduled_hour: 8, scheduled_weekday: 1, scheduled_day: 1,
    enabled: true,
    audience_emails: ["finops@company.com", "vp-eng@company.com"], audience_slack: ["#finops"],
    report_format: "markdown", namespace: "production", custom_prompt: "",
    created_at: _ago(90 * 24 * 60), updated_at: _ago(24 * 60),
    last_run_at: _ago(24 * 60), next_run_at: _nextMonthDay(1, 8),
    last_status: "warning", run_count: 3,
    last_summary: "$34.8k spend (+10.7% MoM). $7.2k/mo waste. CloudWatch logging +366% anomaly — fix saves $820/mo immediately.",
  },
  {
    id: "co_daily_slo", name: "Daily SLO Scorecard",
    description: "Per-service error rate, latency p99, uptime — Slack #engineering at 08:00 UTC",
    checkout_type: "slo_review", frequency: "daily",
    scheduled_hour: 8, scheduled_weekday: 1, scheduled_day: 1,
    enabled: true,
    audience_emails: [], audience_slack: ["#engineering"],
    report_format: "markdown", namespace: "production", custom_prompt: "",
    created_at: _ago(14 * 24 * 60), updated_at: _ago(60),
    last_run_at: _ago(60), next_run_at: _nextDailyAt(8),
    last_status: "warning", run_count: 14,
    last_summary: "🔴 order-service 97.8% error rate (active incident). 🟡 notification-svc 3.8% errors. 🟢 auth-service, payment-service, api-gateway within SLO.",
  },
  {
    id: "co_monthly_cap", name: "Monthly Capacity Planning",
    description: "Node + pod resource runway, HPA headroom, cluster autoscaler review",
    checkout_type: "capacity_review", frequency: "monthly",
    scheduled_hour: 10, scheduled_weekday: 1, scheduled_day: 15,
    enabled: true,
    audience_emails: ["infra@company.com"], audience_slack: [],
    report_format: "markdown", namespace: "production", custom_prompt: "",
    created_at: _ago(60 * 24 * 60), updated_at: _ago(5 * 24 * 60),
    last_run_at: _ago(5 * 24 * 60), next_run_at: _nextMonthDay(15, 10),
    last_status: "passed", run_count: 2,
    last_summary: "CPU runway 21 days ✅. Memory runway 3 days ⚠️ (node-2 at 92%). Recommend adding 1 node before Apr 25.",
  },
  {
    id: "co_q_security", name: "Quarterly Security Audit",
    description: "RBAC review, exposed services, pods running as root, secrets age",
    checkout_type: "custom", frequency: "quarterly",
    scheduled_hour: 9, scheduled_weekday: 1, scheduled_day: 1,
    enabled: true,
    audience_emails: ["security@company.com", "cto@company.com"], audience_slack: ["#security"],
    report_format: "markdown", namespace: "production",
    custom_prompt: "Perform a Kubernetes security audit. Check: 1) RBAC bindings — any ClusterAdmin granted to non-platform teams? 2) Services of type LoadBalancer without ingress annotations 3) Pods with securityContext.runAsRoot=true or no securityContext 4) Container images without pinned digest or version 5) Kubernetes Secrets not rotated in 90+ days. Rate each finding P0/P1/P2 and provide remediation steps.",
    created_at: _ago(30 * 24 * 60), updated_at: _ago(30 * 24 * 60),
    last_run_at: null, next_run_at: _nextQuarterAt(9),
    last_status: "pending", run_count: 0,
    last_summary: "",
  },
];

const DEMO_RUNS: Record<string, any[]> = {
  co_weekly_infra: [
    { id: "r1", checkout_id: "co_weekly_infra", checkout_name: "Weekly Infrastructure Health", checkout_type: "infra_health", started_at: _ago(2 * 60), completed_at: _ago(2 * 60 - 1), status: "passed", triggered_by: "scheduler", duration_seconds: 48, summary: "All 14 pods healthy. No alerts firing. node-2 memory at 92% — flagged for monitoring.", full_report: "## Infrastructure Health Report\n\n**Date:** " + new Date().toUTCString() + "\n\n### Pod Status ✅\nAll 14 pods running. No CrashLoopBackOff. payment-service pod `bv3r1` has 14 restarts (memory pressure — see capacity section).\n\n### Node Utilization ⚠️\n| Node | CPU | Memory | Pods |\n|------|-----|--------|------|\n| node-1 | 71% | 83% | 18/30 |\n| node-2 | 45% | **92%** | 22/30 |\n| node-3 | 12% | 34% | 9/30 |\n\nnode-2 memory at 92% — risk of OOM eviction if payment-service memory leak continues.\n\n### Active Alerts ⚠️\n- `NodeMemoryPressure` (warning) — node-2 for 15 minutes\n- `HPAMaxReplicas` (warning) — payment-service at 7/10 replicas\n\n### Recent Deployments ✅\n- `payment-service:v1.9.6` deployed 2h ago — success\n\n### Health Score: 74/100\n\n## Recommendations\n- Add 1 node to ng-general-purpose before node-2 OOM (< 3 days)\n- Investigate payment-service memory leak\n- Enable cluster autoscaler scale-down" },
    { id: "r2", checkout_id: "co_weekly_infra", checkout_name: "Weekly Infrastructure Health", checkout_type: "infra_health", started_at: _ago(9 * 24 * 60), completed_at: _ago(9 * 24 * 60 - 1), status: "warning", triggered_by: "scheduler", duration_seconds: 52, summary: "HPA near max on payment-service (8/10). order-service had 3 failed deployments this week. Node memory trending up.", full_report: "## Infrastructure Health Report\n\n**Previous week review.**\n\nPayment-service HPA at 8/10 replicas — approaching ceiling. Recommend increasing max to 15 or rightsizing pods." },
  ],
  co_monthly_cost: [
    { id: "r3", checkout_id: "co_monthly_cost", checkout_name: "Monthly Cost Review", checkout_type: "cost_review", started_at: _ago(24 * 60), completed_at: _ago(24 * 60 - 2), status: "warning", triggered_by: "scheduler", duration_seconds: 71, summary: "$34.8k spend (+10.7% MoM). $7.2k waste identified. CloudWatch logging spike +366% needs immediate fix.", full_report: "## Monthly Cost Review — April 2026\n\n**Total Spend:** $34,820 (+10.7% MoM)\n\n### Top Cost Drivers\n| Service | Monthly Cost | MoM |\n|---------|-------------|-----|\n| EC2 (compute) | $12,400 | +8% |\n| RDS (databases) | $8,200 | +2% |\n| EKS clusters | $6,800 | +22% |\n| CloudWatch/Logging | $1,920 | **+45%** |\n\n### ⚠️ Cost Anomaly — CloudWatch Logging\nDaily cost jumped from $45 → $210 on Apr 18. Debug logging left enabled in production (8× log volume).\n\n**Fix:** `kubectl set env deployment/order-service LOG_LEVEL=INFO -n production` — saves $820/mo immediately.\n\n### Waste Identified: $7,240/month\n- Idle RDS `prod-reporting-db`: $1,520/mo savings available\n- Oversized EC2 `analytics-worker-01`: $480/mo\n- EKS node group (6→4 nodes): $960/mo\n\n## Recommendations\n- Fix debug logging immediately ($820/mo, 2 min fix)\n- Migrate prod-reporting-db to Aurora Serverless v2 ($1,520/mo)\n- Enable cluster autoscaler ($960/mo)" },
  ],
  co_daily_slo: [
    { id: "r4", checkout_id: "co_daily_slo", checkout_name: "Daily SLO Scorecard", checkout_type: "slo_review", started_at: _ago(60), completed_at: _ago(59), status: "warning", triggered_by: "scheduler", duration_seconds: 43, summary: "order-service 100% error rate (active incident). payment-service and auth-service within SLO.", full_report: "## Daily SLO Scorecard\n\n| Service | Error Rate | p99 Latency | Status |\n|---------|-----------|-------------|--------|\n| api-gateway | 0.1% | 12ms | 🟢 |\n| auth-service | 0.2% | 43ms | 🟢 |\n| payment-service | 0.3% | 46ms | 🟢 |\n| order-service | **97.8%** | N/A (crashing) | 🔴 |\n| inventory-service | 0.1% | 28ms | 🟢 |\n| notification-svc | 3.8% | 112ms | 🟡 |\n\n### Active Incidents\n- `order-service` CrashLoopBackOff — 8 minutes — P1 active\n\n### Recommendations\n- Resolve order-service incident (rollback in progress)\n- Monitor notification-svc error rate (3.8% → trending toward 5% SLO breach)" },
    { id: "r5", checkout_id: "co_daily_slo", checkout_name: "Daily SLO Scorecard", checkout_type: "slo_review", started_at: _ago(25 * 60), completed_at: _ago(25 * 60 - 1), status: "passed", triggered_by: "scheduler", duration_seconds: 39, summary: "All services within SLO. No active incidents. auth-service p99 trending up (212ms, SLO 500ms).", full_report: "## Daily SLO Scorecard\n\nAll green. auth-service p99 at 212ms — still well within 500ms SLO but worth watching." },
  ],
};

function CheckoutsTab({ get, post, del }: { get: any; post: any; del: any }) {
  const [checkouts, setCheckouts] = useState<any[]>(DEMO_CHECKOUTS);
  const [stats, setStats] = useState({ total: 5, passed: 2, warning: 2, failed: 0, due_today: 2 });
  const [runs, setRuns] = useState<Record<string, any[]>>(DEMO_RUNS);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedReport, setExpandedReport] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [compilingId, setCompilingId] = useState<string | null>(null);
  const [compileSummary, setCompileSummary] = useState<Record<string, any>>({});
  const [knowledgeSets, setKnowledgeSets] = useState<any[]>([]);
  const [setPickerForId, setSetPickerForId] = useState<string | null>(null);
  const [assigningSet, setAssigningSet] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [filter, setFilter] = useState<"all" | "failed" | "due_today">("all");
  const [newCo, setNewCo] = useState({
    name: "", description: "", checkout_type: "infra_health", frequency: "weekly",
    scheduled_hour: 9, scheduled_weekday: 1, scheduled_day: 1,
    namespace: "production", custom_prompt: "", audience_emails: "", audience_slack: "",
    enabled: true,
  });
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    const [list, st] = await Promise.all([
      get("/api/v1/checkouts"),
      get("/api/v1/checkouts/stats"),
    ]);
    if (list && list.length > 0) setCheckouts(list);
    if (st) setStats(st);
  }, [get]);

  useEffect(() => {
    load();
    get("/api/v1/knowledge/sets/all").then((s: any) => { if (s) setKnowledgeSets(s); });
  }, [load, get]);

  async function assignKnowledgeSet(checkoutId: string, setId: string) {
    setAssigningSet(true);
    await post(`/api/v1/knowledge/sets/${setId}/assign/${checkoutId}`);
    setCheckouts(p => p.map(c => c.id === checkoutId ? { ...c, knowledge_set_id: setId } : c));
    setSetPickerForId(null);
    setAssigningSet(false);
  }

  async function loadRuns(id: string) {
    const r = await get(`/api/v1/checkouts/${id}/runs`);
    if (r && r.length > 0) setRuns(p => ({ ...p, [id]: r }));
  }

  async function runNow(id: string) {
    setRunningId(id);
    const r = await post(`/api/v1/checkouts/${id}/run`);
    if (r) {
      setCheckouts(p => p.map(c => c.id === id
        ? { ...c, last_status: r.status, last_summary: r.summary, last_run_at: r.started_at }
        : c));
      setRuns(p => ({ ...p, [id]: [r, ...(p[id] || [])] }));
    }
    setRunningId(null);
    load();
  }

  async function compileCheckout(id: string) {
    setCompilingId(id);
    const r = await post(`/api/v1/checkouts/${id}/compile`);
    if (r?.compiled) {
      setCheckouts(p => p.map(c => c.id === id ? { ...c, ...r.checkout } : c));
      setCompileSummary(p => ({ ...p, [id]: r.plan_summary }));
    }
    setCompilingId(null);
  }

  async function resetPlan(id: string) {
    await del(`/api/v1/checkouts/${id}/compile`);
    setCheckouts(p => p.map(c => c.id === id ? { ...c, is_compiled: false, compiled_at: null, tokens_saved_pct: 0 } : c));
    setCompileSummary(p => { const n = { ...p }; delete n[id]; return n; });
  }

  async function deleteCheckout(id: string) {
    if (!confirm("Delete this checkout?")) return;
    await del(`/api/v1/checkouts/${id}`);
    setCheckouts(p => p.filter(c => c.id !== id));
    load();
  }

  async function createCheckout() {
    setCreating(true);
    const body = {
      ...newCo,
      audience_emails: newCo.audience_emails.split(",").map((s: string) => s.trim()).filter(Boolean),
      audience_slack:  newCo.audience_slack.split(",").map((s: string) => s.trim()).filter(Boolean),
    };
    const r = await post("/api/v1/checkouts", body);
    if (r?.id) {
      setCheckouts(p => [r, ...p]);
      setShowCreate(false);
      setNewCo({ name: "", description: "", checkout_type: "infra_health", frequency: "weekly",
                 scheduled_hour: 9, scheduled_weekday: 1, scheduled_day: 1,
                 namespace: "production", custom_prompt: "", audience_emails: "", audience_slack: "", enabled: true });
      load();
    }
    setCreating(false);
  }

  // Show absolute UTC datetime with relative hint
  function fmtTime(iso: string | null, past = true): string {
    if (!iso) return "Never";
    const d = new Date(iso);
    const abs = d.toUTCString().replace(" GMT", " UTC").replace(/:\d\d UTC/, " UTC");
    const diff = Math.abs(Date.now() - d.getTime());
    const m = Math.floor(diff / 60_000);
    const rel = m < 1 ? "just now" : m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m/60)}h` : `${Math.floor(m/1440)}d`;
    return past ? `${abs} (${rel} ago)` : abs;
  }

  function fmtNextRun(iso: string | null): string {
    if (!iso) return "—";
    const d = new Date(iso);
    const diff = d.getTime() - Date.now();
    if (diff < 0) return "Overdue — " + d.toUTCString().replace(" GMT", " UTC");
    const abs = d.toUTCString().replace(" GMT", " UTC").replace(/:\d\d UTC/, " UTC");
    const m = Math.round(diff / 60_000);
    const rel = m < 60 ? `in ${m}m` : m < 1440 ? `in ${Math.floor(m/60)}h` : `in ${Math.floor(m/1440)}d`;
    return `${abs} (${rel})`;
  }

  function scheduleLabel(co: any): string {
    const h = String(co.scheduled_hour ?? 9).padStart(2, "0");
    const freq = co.frequency;
    if (freq === "daily")    return `Daily at ${h}:00 UTC`;
    if (freq === "weekly")   return `Every ${["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][co.scheduled_weekday ?? 1]} at ${h}:00 UTC`;
    if (freq === "monthly")  return `${co.scheduled_day ?? 1}${["","st","nd","rd"][co.scheduled_day ?? 1] ?? "th"} of month at ${h}:00 UTC`;
    if (freq === "quarterly") return `Quarterly, ${co.scheduled_day ?? 1}st at ${h}:00 UTC`;
    if (freq === "half-yearly") return `Half-yearly at ${h}:00 UTC`;
    if (freq === "yearly")   return `Yearly at ${h}:00 UTC`;
    return freq;
  }

  const typeInfo = (ct: string) => CHECKOUT_TYPES.find(t => t.value === ct) || CHECKOUT_TYPES[0];
  const stStyle = (s: string) => STATUS_STYLES[s] || STATUS_STYLES.pending;

  const now = new Date();
  const filtered = checkouts.filter(c => {
    if (filter === "failed") return c.last_status === "failed" || c.last_status === "warning";
    if (filter === "due_today") {
      if (!c.next_run_at) return false;
      const diff = new Date(c.next_run_at).getTime() - now.getTime();
      return diff < 24 * 3600_000;
    }
    return true;
  });

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <CalendarClock size={18} className="text-indigo-400" /> Scheduled Checkouts
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Automated AI-powered reviews · daily, weekly, monthly, and beyond
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="p-2 text-slate-500 hover:text-white hover:bg-[#161b27] rounded-lg transition-colors">
            <RotateCcw size={14} />
          </button>
          <button onClick={() => setShowCreate(p => !p)}
            className="flex items-center gap-1.5 px-3 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg transition-colors">
            {showCreate ? <><X size={14} /> Cancel</> : <><Plus size={14} /> New Checkout</>}
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { label: "Total",     value: stats.total,     color: "text-slate-300" },
          { label: "Passed",    value: stats.passed,    color: "text-green-400" },
          { label: "Warning",   value: stats.warning,   color: "text-amber-400" },
          { label: "Failed",    value: stats.failed,    color: "text-red-400"   },
          { label: "Due Today", value: stats.due_today, color: "text-indigo-400" },
        ].map(({ label, value, color }) => (
          <Card key={label} className="p-3 text-center">
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
            <div className="text-xs text-slate-500 mt-0.5">{label}</div>
          </Card>
        ))}
      </div>

      {/* Create form */}
      {showCreate && (
        <Card className="p-5">
          <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <Plus size={14} className="text-indigo-400" /> New Checkout
          </h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2 grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-slate-400 block mb-1">Name *</label>
                <input value={newCo.name} onChange={e => setNewCo(p => ({ ...p, name: e.target.value }))}
                  placeholder="Weekly Infra Health" className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50" />
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1">Description</label>
                <input value={newCo.description} onChange={e => setNewCo(p => ({ ...p, description: e.target.value }))}
                  placeholder="Brief description of what this checkout reviews" className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50" />
              </div>
            </div>

            {/* Type selector */}
            <div className="col-span-2">
              <label className="text-xs text-slate-400 block mb-2">Checkout Type *</label>
              <div className="grid grid-cols-3 gap-2">
                {CHECKOUT_TYPES.map(t => (
                  <button key={t.value} onClick={() => setNewCo(p => ({ ...p, checkout_type: t.value }))}
                    className={`p-2.5 rounded-lg border text-left transition-all ${newCo.checkout_type === t.value ? "border-indigo-600/60 bg-indigo-950/30" : "border-[#1e2535] hover:border-[#2a3548]"}`}>
                    <div className={`text-xs font-medium ${t.color}`}>{t.label}</div>
                    <div className="text-xs text-slate-600 mt-0.5 leading-tight">{t.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Custom prompt */}
            {newCo.checkout_type === "custom" && (
              <div className="col-span-2">
                <label className="text-xs text-slate-400 block mb-1">Custom Prompt *</label>
                <textarea value={newCo.custom_prompt} onChange={e => setNewCo(p => ({ ...p, custom_prompt: e.target.value }))}
                  rows={3} placeholder="Describe what Claude should check, analyze, or review..."
                  className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50 resize-none" />
              </div>
            )}

            <div>
              <label className="text-xs text-slate-400 block mb-1">Frequency *</label>
              <select value={newCo.frequency} onChange={e => setNewCo(p => ({ ...p, frequency: e.target.value }))}
                className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-300 text-xs rounded-lg px-3 py-2">
                {FREQUENCIES.map(f => <option key={f} value={f}>{f.charAt(0).toUpperCase() + f.slice(1)}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Run time (UTC hour, 0–23)</label>
              <input type="number" min={0} max={23} value={newCo.scheduled_hour}
                onChange={e => setNewCo(p => ({ ...p, scheduled_hour: Number(e.target.value) }))}
                className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50" />
              <span className="text-xs text-slate-600 mt-0.5 block">Runs at HH:00 UTC — e.g. 9 = 09:00 UTC</span>
            </div>
            {newCo.frequency === "weekly" && (
              <div>
                <label className="text-xs text-slate-400 block mb-1">Day of week</label>
                <select value={newCo.scheduled_weekday} onChange={e => setNewCo(p => ({ ...p, scheduled_weekday: Number(e.target.value) }))}
                  className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-300 text-xs rounded-lg px-3 py-2">
                  {["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"].map((d,i) => (
                    <option key={i} value={i}>{d}</option>
                  ))}
                </select>
              </div>
            )}
            {["monthly","quarterly","half-yearly","yearly"].includes(newCo.frequency) && (
              <div>
                <label className="text-xs text-slate-400 block mb-1">Day of month (1–28)</label>
                <input type="number" min={1} max={28} value={newCo.scheduled_day}
                  onChange={e => setNewCo(p => ({ ...p, scheduled_day: Number(e.target.value) }))}
                  className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50" />
              </div>
            )}
            <div>
              <label className="text-xs text-slate-400 block mb-1">Namespace</label>
              <input value={newCo.namespace} onChange={e => setNewCo(p => ({ ...p, namespace: e.target.value }))}
                placeholder="production" className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50" />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Email Audience <span className="text-slate-600">(comma-separated)</span></label>
              <input value={newCo.audience_emails} onChange={e => setNewCo(p => ({ ...p, audience_emails: e.target.value }))}
                placeholder="sre@co.com, vp@co.com" className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50" />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Slack Channels <span className="text-slate-600">(comma-separated)</span></label>
              <input value={newCo.audience_slack} onChange={e => setNewCo(p => ({ ...p, audience_slack: e.target.value }))}
                placeholder="#ops-reports, #engineering" className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50" />
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button onClick={createCheckout} disabled={creating || !newCo.name}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-lg flex items-center gap-2 transition-colors">
              {creating ? <><Spinner /> Creating…</> : <><CalendarClock size={13} /> Create Checkout</>}
            </button>
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 bg-[#1e2535] hover:bg-[#2a3548] text-slate-300 text-sm rounded-lg transition-colors">Cancel</button>
          </div>
        </Card>
      )}

      {/* Filter tabs */}
      <div className="flex gap-1">
        {(["all","due_today","failed"] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${filter === f ? "bg-indigo-600/20 text-indigo-300 border border-indigo-600/30" : "text-slate-500 hover:text-slate-200 hover:bg-[#161b27]"}`}>
            {f === "all" ? `All (${checkouts.length})` : f === "due_today" ? "Due Today" : "Needs Attention"}
          </button>
        ))}
      </div>

      {/* Checkout list */}
      <div className="space-y-3">
        {filtered.map(co => {
          const ti = typeInfo(co.checkout_type);
          const ss = stStyle(co.last_status);
          const isExpanded = expandedId === co.id;
          const coRuns: any[] = runs[co.id] || [];

          return (
            <Card key={co.id} className="overflow-hidden">
              {/* Main row */}
              <div className="p-4 flex items-start gap-3">
                <div className={`mt-0.5 text-xs px-2 py-0.5 rounded-full border font-mono flex-shrink-0 ${ss.cls}`}>
                  {ss.icon} {co.last_status}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-white">{co.name}</span>
                    <span className={`text-xs ${ti.color} bg-[#0f1117] border border-[#1e2535] px-1.5 py-0.5 rounded`}>{ti.label}</span>
                    <span className="text-xs text-slate-600 bg-[#0f1117] border border-[#1e2535] px-1.5 py-0.5 rounded capitalize">{co.frequency}</span>
                    {!co.enabled && <span className="text-xs text-red-400 bg-red-950/30 border border-red-800/40 px-1.5 py-0.5 rounded">disabled</span>}
                  </div>

                  {co.last_summary && (
                    <p className="text-xs text-slate-400 mt-1 line-clamp-2">{co.last_summary}</p>
                  )}

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 mt-1.5 text-xs text-slate-600">
                    <span className="flex items-center gap-1"><CalendarClock size={10} className="text-slate-500" /> <span className="text-slate-400">{scheduleLabel(co)}</span></span>
                    <span className="flex items-center gap-1"><Clock size={10} /> Last: <span className="text-slate-500">{fmtTime(co.last_run_at)}</span></span>
                    <span className="flex items-center gap-1">Next: <span className={`${!co.next_run_at || new Date(co.next_run_at) < new Date() ? "text-amber-400" : "text-slate-400"}`}>{fmtNextRun(co.next_run_at)}</span></span>
                    <span className="text-slate-600">{co.run_count} run{co.run_count !== 1 ? "s" : ""}</span>
                    {co.audience_slack?.length > 0 && <span>📢 {co.audience_slack.join(", ")}</span>}
                    {co.audience_emails?.length > 0 && <span>✉️ {co.audience_emails.join(", ")}</span>}
                    {/* Knowledge Set indicator */}
                    {co.knowledge_set_id ? (
                      <span className="flex items-center gap-1 text-green-400">
                        📦 {knowledgeSets.find(s => s.id === co.knowledge_set_id)?.name || "Set assigned"}
                        <button onClick={() => setSetPickerForId(setPickerForId === co.id ? null : co.id)}
                          className="text-slate-500 hover:text-slate-300 ml-0.5">(change)</button>
                      </span>
                    ) : (
                      <button onClick={() => setSetPickerForId(setPickerForId === co.id ? null : co.id)}
                        className="text-amber-400 hover:text-amber-300 flex items-center gap-1">
                        📦 Assign Knowledge Set
                      </button>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1.5 flex-shrink-0">
                  {/* Compile / compiled badge */}
                  {co.is_compiled ? (
                    <div className="flex items-center gap-1">
                      <span className="flex items-center gap-1 px-2 py-1 text-xs bg-green-950/40 border border-green-800/40 text-green-300 rounded-lg">
                        <CheckCircle2 size={11} /> Compiled · {co.tokens_saved_pct}% tokens saved
                      </span>
                      <button onClick={() => resetPlan(co.id)} title="Reset plan — recompile on next run"
                        className="p-1.5 text-slate-600 hover:text-amber-400 rounded-lg transition-colors text-xs">↺</button>
                    </div>
                  ) : (
                    <button onClick={() => compileCheckout(co.id)} disabled={compilingId === co.id}
                      title="Compile: Claude reads the SOP once and generates a reusable execution plan (~78% fewer tokens per run)"
                      className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-amber-950/30 hover:bg-amber-950/60 border border-amber-800/40 text-amber-300 rounded-lg transition-colors disabled:opacity-40">
                      {compilingId === co.id ? <><Spinner /> Compiling…</> : <><Zap size={11} /> Compile</>}
                    </button>
                  )}
                  <button onClick={() => runNow(co.id)} disabled={runningId === co.id}
                    className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-600/30 text-indigo-300 rounded-lg transition-colors disabled:opacity-40">
                    {runningId === co.id ? <><Spinner /> Running</> : <><PlayCircle size={12} /> Run Now</>}
                  </button>
                  <button onClick={async () => {
                    setExpandedId(p => p === co.id ? null : co.id);
                    setExpandedReport(null);
                    if (expandedId !== co.id) await loadRuns(co.id);
                  }} className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-slate-400 hover:text-white hover:bg-[#1e2535] rounded-lg transition-colors">
                    {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />} History
                  </button>
                  <button onClick={() => deleteCheckout(co.id)} className="p-1.5 text-slate-600 hover:text-red-400 hover:bg-red-950/20 rounded-lg transition-colors">
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>

              {/* Run history */}
              {/* Compile plan summary */}
              {/* Knowledge Set picker */}
              {setPickerForId === co.id && (
                <div className="px-4 pb-3">
                  <div className="bg-[#0b0e16] border border-[#1e2535] rounded-lg p-3">
                    <div className="text-xs text-slate-400 mb-2 flex items-center gap-2">
                      📦 <span>Select a Knowledge Set for this checkout</span>
                      <span className="text-slate-600 ml-auto">SOP + Template + Context bundled together</span>
                    </div>
                    {knowledgeSets.length === 0 ? (
                      <div className="text-xs text-slate-600 py-2">
                        No knowledge sets yet — go to <span className="text-indigo-400">Knowledge Base → Knowledge Sets</span> to create one
                      </div>
                    ) : (
                      <div className="space-y-1.5">
                        {knowledgeSets.map((s: any) => (
                          <button key={s.id} onClick={() => assignKnowledgeSet(co.id, s.id)}
                            disabled={assigningSet}
                            className={`w-full text-left flex items-start gap-3 p-2.5 rounded-lg border transition-colors text-xs
                              ${co.knowledge_set_id === s.id ? "border-indigo-600/50 bg-indigo-950/30" : "border-[#1e2535] hover:border-[#2a3548] hover:bg-[#161b27]"}`}>
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-white flex items-center gap-2">
                                {s.name}
                                {s.is_default && <span className="text-xs text-indigo-400">(default)</span>}
                                {co.knowledge_set_id === s.id && <CheckCircle2 size={11} className="text-green-400" />}
                              </div>
                              <div className="text-slate-500 mt-0.5 flex items-center gap-3">
                                {s.sop_doc_name && <span>📋 {s.sop_doc_name}</span>}
                                {s.template_doc_name && <span>📄 {s.template_doc_name}</span>}
                                {s.context_doc_names?.length > 0 && <span>🗂️ {s.context_doc_names.length} context</span>}
                              </div>
                            </div>
                            {assigningSet && <Spinner />}
                          </button>
                        ))}
                        <button onClick={() => setSetPickerForId(null)} className="w-full text-center text-xs text-slate-600 hover:text-slate-400 pt-1">Close</button>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {compileSummary[co.id] && (
                <div className="px-4 pb-3">
                  <div className="bg-green-950/20 border border-green-800/30 rounded-lg p-3 text-xs">
                    <div className="flex items-center gap-2 mb-2 text-green-300 font-medium">
                      <Zap size={11} /> Execution Plan Compiled
                    </div>
                    <div className="grid grid-cols-4 gap-3 text-slate-400">
                      <div><div className="text-slate-300 font-mono text-sm">{compileSummary[co.id].tool_steps}</div>tool calls</div>
                      <div><div className="text-slate-300 font-mono text-sm">{compileSummary[co.id].thresholds_critical}</div>critical rules</div>
                      <div><div className="text-slate-300 font-mono text-sm">{compileSummary[co.id].thresholds_warning}</div>warning rules</div>
                      <div><div className="text-green-400 font-mono text-sm">{compileSummary[co.id].tokens_saved_pct}%</div>tokens saved/run</div>
                    </div>
                    <div className="mt-2 text-slate-500">
                      Compiled from: {compileSummary[co.id].compiled_from?.join(", ") || "knowledge base docs"}
                    </div>
                  </div>
                </div>
              )}

              {isExpanded && (
                <div className="border-t border-[#1e2535] bg-[#0b0e16]">
                  {coRuns.length === 0 ? (
                    <div className="p-4 text-xs text-slate-600 text-center">No runs yet — click "Run Now" to execute</div>
                  ) : (
                    <div className="divide-y divide-[#1e2535]">
                      {coRuns.map((r: any) => {
                        const rs = stStyle(r.status);
                        const isReportOpen = expandedReport === r.id;
                        return (
                          <div key={r.id} className="p-3">
                            <div className="flex items-start gap-3">
                              <span className={`text-xs px-1.5 py-0.5 rounded border flex-shrink-0 ${rs.cls}`}>{rs.icon} {r.status}</span>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-3 text-xs text-slate-500">
                                  <span className="flex items-center gap-1"><Clock size={10} /> {fmtTime(r.started_at)}</span>
                                  {r.duration_seconds && <span>{r.duration_seconds.toFixed(0)}s</span>}
                                  <span className="text-slate-600">{r.triggered_by}</span>
                                </div>
                                <p className="text-xs text-slate-400 mt-1">{r.summary}</p>
                                {r.error && <p className="text-xs text-red-400 mt-1 font-mono">{r.error}</p>}
                              </div>
                              {r.full_report && (
                                <button onClick={() => setExpandedReport(p => p === r.id ? null : r.id)}
                                  className="flex-shrink-0 text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors">
                                  <FileText size={11} /> {isReportOpen ? "Hide" : "Report"}
                                </button>
                              )}
                            </div>
                            {isReportOpen && r.full_report && (
                              <div className="mt-3 p-3 bg-[#0f1117] border border-[#1e2535] rounded-lg max-h-96 overflow-y-auto">
                                <div className="prose-ops text-xs"><ReactMarkdown>{r.full_report}</ReactMarkdown></div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </Card>
          );
        })}

        {filtered.length === 0 && (
          <Card className="flex flex-col items-center justify-center py-16">
            <CalendarClock size={36} className="text-indigo-600/30 mb-3" />
            <p className="text-slate-500 text-sm mb-1">No checkouts match this filter</p>
            <p className="text-slate-600 text-xs">Create a new checkout to start automating your reviews</p>
          </Card>
        )}
      </div>
    </div>
  );
}

// ─── Knowledge Base tab ───────────────────────────────────────────

const DOC_TYPE_META: Record<string, { label: string; color: string; desc: string }> = {
  sop:             { label: "SOP",             color: "text-indigo-400 bg-indigo-950/40 border-indigo-800/40", desc: "Standard Operating Procedure — step-by-step instructions Claude follows during each checkout" },
  report_template: { label: "Report Template", color: "text-green-400  bg-green-950/40  border-green-800/40",  desc: "Sample output format — Claude formats every report to match this exactly" },
  context:         { label: "Context",         color: "text-amber-400  bg-amber-950/40  border-amber-800/40",  desc: "Background knowledge — AWS architecture, SLO definitions, team contacts, runbooks" },
};

const CHECKOUT_TYPE_COLORS: Record<string, string> = {
  infra_health:    "text-indigo-300",
  cost_review:     "text-green-300",
  capacity_review: "text-amber-300",
  slo_review:      "text-blue-300",
  incident_review: "text-red-300",
  custom:          "text-purple-300",
  "*":             "text-slate-400",
};



// ─── Admin tab ────────────────────────────────────────────────────
function AdminTab({ get, post }: { get: any; post: any }) {
  const [users, setUsers] = useState<any[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [loading, setLoading] = useState(true);
  const [newUser, setNewUser] = useState({ username: "", email: "", full_name: "", role: "sre", password: "", team: "" });
  const [adding, setAdding] = useState(false);

  const loadUsers = useCallback(async () => {
    const u = await get("/auth/users");
    if (u) setUsers(u);
    setLoading(false);
  }, [get]);

  useEffect(() => { loadUsers(); }, [loadUsers]);

  async function addUser() {
    setAdding(true);
    await post("/auth/users", newUser);
    setNewUser({ username: "", email: "", full_name: "", role: "sre", password: "", team: "" });
    setShowAdd(false);
    await loadUsers();
    setAdding(false);
  }

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <Shield size={18} className="text-purple-400" /> User Management
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">Manage users and roles · Admin only</p>
        </div>
        <button onClick={() => setShowAdd(p => !p)}
          className="flex items-center gap-1.5 px-3 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg transition-colors">
          <Plus size={14} /> Add User
        </button>
      </div>

      {/* Role reference */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { role: "admin", desc: "Full access · manage users, connectors, all agents", color: "border-purple-700/40 bg-purple-950/20" },
          { role: "sre", desc: "Incidents · K8s ops · chat · post-mortems", color: "border-blue-700/40 bg-blue-950/20" },
          { role: "finops", desc: "Cost analysis · optimization · chat", color: "border-green-700/40 bg-green-950/20" },
          { role: "viewer", desc: "Read-only dashboard access", color: "border-slate-600/40 bg-slate-800/20" },
        ].map(({ role, desc, color }) => (
          <div key={role} className={`p-3 rounded-xl border ${color}`}>
            <RoleBadge role={role} />
            <p className="text-xs text-slate-500 mt-1.5">{desc}</p>
          </div>
        ))}
      </div>

      {/* Add user form */}
      {showAdd && (
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-white mb-3">New User</h2>
          <div className="grid grid-cols-3 gap-3">
            {[
              { key: "full_name", label: "Full Name", placeholder: "Jane Smith" },
              { key: "username", label: "Username", placeholder: "jsmith" },
              { key: "email", label: "Email", placeholder: "jane@company.com" },
              { key: "password", label: "Password", placeholder: "secure-password" },
              { key: "team", label: "Team", placeholder: "platform-sre" },
            ].map(({ key, label, placeholder }) => (
              <div key={key}>
                <label className="text-xs text-slate-400 block mb-1">{label}</label>
                <input type={key === "password" ? "password" : "text"}
                  value={(newUser as any)[key]} onChange={e => setNewUser(p => ({ ...p, [key]: e.target.value }))}
                  placeholder={placeholder}
                  className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50" />
              </div>
            ))}
            <div>
              <label className="text-xs text-slate-400 block mb-1">Role</label>
              <select value={newUser.role} onChange={e => setNewUser(p => ({ ...p, role: e.target.value }))}
                className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-300 text-xs rounded-lg px-3 py-2">
                {["admin", "sre", "finops", "viewer"].map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={addUser} disabled={adding || !newUser.username || !newUser.password}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-lg flex items-center gap-2">
              {adding ? <><Spinner /> Adding…</> : "Create User"}
            </button>
            <button onClick={() => setShowAdd(false)} className="px-4 py-2 bg-[#1e2535] hover:bg-[#2a3548] text-slate-300 text-sm rounded-lg">Cancel</button>
          </div>
        </Card>
      )}

      {/* User list */}
      <Card>
        <div className="p-4 border-b border-[#1e2535]">
          <h2 className="text-sm font-semibold text-white">Users ({users.length})</h2>
        </div>
        {loading ? (
          <div className="flex items-center justify-center py-8"><Spinner /></div>
        ) : (
          <div className="divide-y divide-[#1e2535]">
            {users.map((u: any) => (
              <div key={u.id} className="flex items-center gap-4 p-4">
                <div className="w-8 h-8 bg-indigo-600/20 border border-indigo-600/30 rounded-full flex items-center justify-center flex-shrink-0">
                  <User size={13} className="text-indigo-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{u.full_name}</span>
                    <span className="text-xs text-slate-500 font-mono">@{u.username}</span>
                    <RoleBadge role={u.role} />
                    {!u.active && <span className="text-xs text-red-400 bg-red-950/40 px-2 rounded">disabled</span>}
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-3">
                    <span>{u.email}</span>
                    {u.team && <span className="text-slate-600">· {u.team}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

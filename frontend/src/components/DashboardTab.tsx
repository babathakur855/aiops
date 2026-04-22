"use client";
/**
 * OpsBrain Multi-Dashboard
 * Inspired by: Dynatrace Smartscape, Datadog APM, PagerDuty Analytics,
 *              New Relic SLO, Grafana, Kubecost
 *
 * Tabs:
 *  1. Overview      — Executive health, active incidents, MTTA/MTTR, deployments
 *  2. App Perf      — Latency p99/p50, error rate, Apdex, throughput per service
 *  3. Infrastructure — Node utilization (USE metrics), pods, network, storage
 *  4. Cost          — Cloud spend, waste, budget, anomalies, savings (Kubecost-style)
 *  5. Reliability   — SLO scorecards, error budgets, DORA metrics, alert quality
 *  6. Diagnostics   — Log volume, error patterns, K8s events, deployment timeline
 */

import { useState, useCallback, useEffect } from "react";
import {
  Activity, AlertTriangle, DollarSign, Server, TrendingUp, TrendingDown,
  Clock, CheckCircle2, XCircle, Target, Shield, Zap, RotateCcw,
  Brain, Layers, GitBranch, Database, Wifi, HardDrive,
  ArrowUp, ArrowDown, Minus, ChevronRight,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  PieChart, Pie, Cell, RadialBarChart, RadialBar,
  CartesianGrid, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

// ── Palette ───────────────────────────────────────────────────────────────────
const C = {
  indigo: "#6366f1", green: "#22c55e", amber: "#f59e0b", red: "#ef4444",
  blue: "#3b82f6", pink: "#ec4899", teal: "#14b8a6", purple: "#a855f7",
  slate: "#64748b", orange: "#f97316",
};
const PIE_COLORS = [C.indigo, C.green, C.amber, C.red, C.blue, C.pink, C.teal, C.orange];

// ── Shared mini-components ────────────────────────────────────────────────────
function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`bg-[#161b27] border border-[#1e2535] rounded-xl ${className}`}>{children}</div>;
}
function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-sm font-semibold text-white mb-4">{children}</h2>;
}
function MetricCard({ icon: Icon, label, value, sub, color = "text-indigo-400", trend, trendVal }:
  { icon: any; label: string; value: string; sub?: string; color?: string; trend?: "up"|"down"|"flat"; trendVal?: string }) {
  const trendIcon = trend === "up" ? <ArrowUp size={10}/> : trend === "down" ? <ArrowDown size={10}/> : <Minus size={10}/>;
  const trendColor = trend === "up" ? "text-red-400" : trend === "down" ? "text-green-400" : "text-slate-500";
  return (
    <Card className="p-4 flex items-start gap-3">
      <div className="p-2 bg-[#1a2236] rounded-lg flex-shrink-0"><Icon size={16} className={color}/></div>
      <div className="min-w-0 flex-1">
        <div className="text-xs text-slate-500 uppercase tracking-wider truncate">{label}</div>
        <div className="text-xl font-bold text-white mt-0.5">{value}</div>
        {(sub || trendVal) && (
          <div className="flex items-center gap-1 mt-0.5">
            {trendVal && <span className={`text-xs flex items-center gap-0.5 ${trendColor}`}>{trendIcon}{trendVal}</span>}
            {sub && <span className="text-xs text-slate-500">{sub}</span>}
          </div>
        )}
      </div>
    </Card>
  );
}
function StatusDot({ status }: { status: string }) {
  const c: Record<string,string> = {
    healthy:"bg-green-400", degraded:"bg-amber-400 animate-pulse",
    down:"bg-red-400 animate-pulse", pending:"bg-purple-400",
  };
  return <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${c[status]??"bg-slate-500"}`}/>;
}
function SeverityBadge({ sev }: { sev: string }) {
  const s: Record<string,string> = {
    critical:"bg-red-950 text-red-400 border border-red-800",
    warning:"bg-amber-950 text-amber-400 border border-amber-800",
    info:"bg-blue-950 text-blue-400 border border-blue-800",
  };
  return <span className={`px-1.5 py-0.5 rounded text-xs font-mono uppercase ${s[sev]??"bg-slate-800 text-slate-400"}`}>{sev}</span>;
}
function TrafficLight({ pct }: { pct: number }) {
  const color = pct >= 99 ? "text-green-400" : pct >= 95 ? "text-amber-400" : "text-red-400";
  const icon  = pct >= 99 ? <CheckCircle2 size={14}/> : pct >= 95 ? <AlertTriangle size={14}/> : <XCircle size={14}/>;
  return <span className={`flex items-center gap-1 ${color}`}>{icon}<span className="font-mono text-xs">{pct.toFixed(2)}%</span></span>;
}
const customTooltip = {
  contentStyle: { background:"#161b27", border:"1px solid #1e2535", borderRadius:6, fontSize:11 },
};

// ── ALL DEMO DATA ─────────────────────────────────────────────────────────────

const now = new Date();
const hAgo = (h: number) => new Date(now.getTime() - h * 3600_000).toLocaleTimeString("en-US", { hour:"2-digit", minute:"2-digit", hour12:false });
const dAgo = (d: number) => new Date(now.getTime() - d * 86400_000).toLocaleDateString("en-US", { month:"short", day:"numeric" });

// ── Overview ──────────────────────────────────────────────────────────────────
const ALERTS_24H = Array.from({ length: 24 }, (_, i) => ({
  h: hAgo(23 - i),
  critical: i < 14 ? 0 : i < 16 ? 2 : i === 16 ? 4 : i < 20 ? 2 : 1,
  warning:  i < 12 ? 1 : i < 15 ? 2 : i < 18 ? 3 : 2,
}));

const RECENT_INCIDENTS = [
  { id:"INC-4821", service:"order-service",   severity:"critical", title:"CrashLoopBackOff — DB connection pool exhausted", started: hAgo(0.2), duration:"8m", status:"active", mtta:"1m", mttr:"—" },
  { id:"INC-4820", service:"payment-service", severity:"warning",  title:"HPA at 7/10 replicas — CPU 84%", started: hAgo(0.5), duration:"12m", status:"active", mtta:"3m", mttr:"—" },
  { id:"INC-4819", service:"node-2",          severity:"warning",  title:"Memory pressure — 92% utilization", started: hAgo(1), duration:"45m", status:"active", mtta:"5m", mttr:"—" },
  { id:"INC-4818", service:"auth-service",    severity:"warning",  title:"p99 latency spike to 312ms (SLO: 200ms)", started: hAgo(6), duration:"22m", status:"resolved", mtta:"4m", mttr:"22m" },
  { id:"INC-4817", service:"inventory-service",severity:"info",    title:"Deployment v1.3.2 completed with 1 failed pod", started: hAgo(10), duration:"5m", status:"resolved", mtta:"2m", mttr:"5m" },
];

const DEPLOYS_7D = [
  { day:dAgo(6), success:3, failed:0 }, { day:dAgo(5), success:4, failed:0 },
  { day:dAgo(4), success:2, failed:1 }, { day:dAgo(3), success:5, failed:0 },
  { day:dAgo(2), success:3, failed:0 }, { day:dAgo(1), success:4, failed:1 },
  { day:dAgo(0), success:1, failed:1 },
];

// ── Application Performance ───────────────────────────────────────────────────
const SERVICES_APM = [
  { name:"api-gateway",       error_rate:0.1,  latency_p99:12,  latency_p50:8,   rps:1240, apdex:0.98, status:"healthy"  },
  { name:"auth-service",      error_rate:0.2,  latency_p99:312, latency_p50:45,  rps:890,  apdex:0.81, status:"degraded" },
  { name:"payment-service",   error_rate:0.3,  latency_p99:46,  latency_p50:22,  rps:340,  apdex:0.96, status:"healthy"  },
  { name:"order-service",     error_rate:97.8, latency_p99:0,   latency_p50:0,   rps:3,    apdex:0.0,  status:"down"     },
  { name:"inventory-service", error_rate:0.1,  latency_p99:28,  latency_p50:14,  rps:220,  apdex:0.99, status:"healthy"  },
  { name:"notification-svc",  error_rate:3.8,  latency_p99:112, latency_p50:67,  rps:180,  apdex:0.87, status:"degraded" },
];

const ERROR_RATE_SERIES = Array.from({ length: 24 }, (_, i) => ({
  t: hAgo(23 - i),
  "order-service":     i < 15 ? 0.2 : i < 17 ? 12 : i < 19 ? 58 : 97.8,
  "payment-service":   0.3 + Math.random() * 0.2,
  "auth-service":      0.2 + (i > 18 ? 2 + Math.random() * 1 : Math.random() * 0.3),
  "notification-svc":  1.2 + (i > 15 ? 2 + Math.random() * 1 : Math.random() * 0.5),
}));

const LATENCY_SERIES = Array.from({ length: 24 }, (_, i) => ({
  t: hAgo(23 - i),
  "api-gateway":    10 + Math.random() * 5,
  "auth-service":   45 + (i > 18 ? 80 + Math.random() * 50 : Math.random() * 20),
  "payment-service":22 + Math.random() * 15,
  "inventory-service": 14 + Math.random() * 8,
}));

const APDEX_DATA = SERVICES_APM.map(s => ({ name: s.name.replace("-service","").replace("notification-svc","notif"), value: s.apdex * 100 }));

const TOP_ENDPOINTS = [
  { endpoint:"POST /api/orders", service:"order-service",   p99:"∞ (crashing)", rps:3,   errors:"97.8%" },
  { endpoint:"GET /api/auth/verify", service:"auth-service",p99:"312ms",        rps:890, errors:"0.2%"  },
  { endpoint:"POST /api/payments", service:"payment-service",p99:"46ms",        rps:340, errors:"0.3%"  },
  { endpoint:"GET /api/inventory", service:"inventory-service",p99:"28ms",      rps:220, errors:"0.1%"  },
  { endpoint:"POST /api/notifications", service:"notification-svc",p99:"112ms", rps:180, errors:"3.8%"  },
];

// ── Infrastructure ────────────────────────────────────────────────────────────
const NODES = [
  { name:"node-1", cpu:71, memory:83, pods:18, max_pods:30, disk:44, net_in:245, net_out:189 },
  { name:"node-2", cpu:45, memory:92, pods:22, max_pods:30, disk:67, net_in:312, net_out:280 },
  { name:"node-3", cpu:12, memory:34, pods:9,  max_pods:30, disk:28, net_in:98,  net_out:76  },
];
const POD_STATUS = [
  { name:"Running",         value:14, color:C.green  },
  { name:"CrashLoopBackOff",value:1,  color:C.red    },
  { name:"Pending",         value:1,  color:C.amber  },
  { name:"Succeeded",       value:4,  color:C.teal   },
];
const CPU_TREND_24H = Array.from({ length: 24 }, (_, i) => ({
  t: hAgo(23 - i),
  "node-1": 65 + Math.sin(i * 0.4) * 12 + (i > 18 ? 8 : 0),
  "node-2": 38 + Math.cos(i * 0.3) * 10,
  "node-3": 8  + Math.random() * 8,
}));
const MEM_TREND_24H = Array.from({ length: 24 }, (_, i) => ({
  t: hAgo(23 - i),
  "node-1": 80 + i * 0.15,
  "node-2": 85 + i * 0.3,
  "node-3": 30 + Math.random() * 8,
}));
const NETWORK_IO = Array.from({ length: 12 }, (_, i) => ({
  t: hAgo(11 - i),
  in_mbps:  180 + Math.sin(i * 0.5) * 60 + (i > 8 ? 40 : 0),
  out_mbps: 140 + Math.cos(i * 0.5) * 40 + (i > 8 ? 30 : 0),
}));
const RESTARTS_TREND = Array.from({ length: 12 }, (_, i) => ({
  t: hAgo(11 - i),
  restarts: i < 8 ? Math.floor(Math.random() * 2) : i < 10 ? 8 + i : 23,
}));

// ── Cost ──────────────────────────────────────────────────────────────────────
const COST_30D = Array.from({ length: 30 }, (_, i) => ({
  d: new Date(now.getTime() - (29 - i) * 86400_000).toLocaleDateString("en-US", {month:"short",day:"numeric"}),
  actual:  980 + Math.sin(i * 0.3) * 120 + i * 18 + (i === 21 ? 390 : 0), // spike on day 21
  budget:  1267,
}));
const SPEND_BY_SVC = [
  { name:"EC2 Compute",    value:12400 }, { name:"RDS Databases",  value:8200  },
  { name:"EKS Clusters",   value:6800  }, { name:"Data Transfer",  value:3100  },
  { name:"S3 Storage",     value:2400  }, { name:"CloudWatch",     value:1920  },
];
const WASTE = [
  { category:"Idle RDS (prod-reporting-db)",    waste:1520, pct:21 },
  { category:"EKS node group overprovisioned",  waste:960,  pct:13 },
  { category:"CloudWatch debug logging",         waste:820,  pct:11 },
  { category:"Oversized EC2 analytics workers",  waste:480,  pct:7  },
  { category:"Unattached EBS volumes",           waste:280,  pct:4  },
  { category:"Unused Elastic IPs",              waste:180,  pct:2  },
];
const COST_BY_TEAM = [
  { team:"Platform SRE",  cost:14200 }, { team:"Order Squad",  cost:8400 },
  { team:"Payment Tribe", cost:6200  }, { team:"Data Eng",     cost:3800 },
  { team:"Auth Team",     cost:2220  },
];

// ── Reliability ───────────────────────────────────────────────────────────────
const SLO_DATA = [
  { service:"api-gateway",       error_slo:0.1,  error_actual:0.1,  lat_slo:50,   lat_actual:12,  avail:99.99, budget_pct:100, status:"healthy"  },
  { service:"auth-service",      error_slo:0.5,  error_actual:0.2,  lat_slo:200,  lat_actual:312, avail:99.95, budget_pct:72,  status:"warning"  },
  { service:"payment-service",   error_slo:0.5,  error_actual:0.3,  lat_slo:500,  lat_actual:46,  avail:99.10, budget_pct:88,  status:"healthy"  },
  { service:"order-service",     error_slo:1.0,  error_actual:97.8, lat_slo:1000, lat_actual:0,   avail:0.0,   budget_pct:0,   status:"critical" },
  { service:"notification-svc",  error_slo:2.0,  error_actual:3.8,  lat_slo:2000, lat_actual:112, avail:99.50, budget_pct:0,   status:"critical" },
];
const MTTR_BY_SVC = [
  { service:"order-svc",    mttr:8  }, { service:"payment-svc", mttr:14 },
  { service:"auth-svc",     mttr:22 }, { service:"notif-svc",   mttr:31 },
  { service:"inventory",    mttr:11 },
];
const ALERT_VOL_7D = [
  { d:dAgo(6), critical:2, warning:8,  info:14 },
  { d:dAgo(5), critical:0, warning:6,  info:11 },
  { d:dAgo(4), critical:3, warning:11, info:18 },
  { d:dAgo(3), critical:1, warning:7,  info:12 },
  { d:dAgo(2), critical:0, warning:5,  info:9  },
  { d:dAgo(1), critical:2, warning:9,  info:15 },
  { d:dAgo(0), critical:4, warning:12, info:20 },
];
const BUDGET_BURN = Array.from({ length: 30 }, (_, i) => ({
  d: dAgo(29 - i),
  remaining: Math.max(0, 100 - (i === 29 ? 100 : i > 25 ? 90 + (i - 25) * 2.5 : i * 2.5 + Math.random() * 3)),
  ideal: 100 - (i / 30) * 100,
}));
const DORA = [
  { metric:"Deployment Frequency",    value:"8/week",  rating:"Elite",  color:C.green  },
  { metric:"Lead Time for Changes",   value:"2.4 days",rating:"High",   color:C.blue   },
  { metric:"Change Failure Rate",     value:"12.5%",   rating:"Medium", color:C.amber  },
  { metric:"Mean Time to Restore",    value:"23 min",  rating:"Elite",  color:C.green  },
];

// ── Diagnostics ───────────────────────────────────────────────────────────────
const LOG_VOL_TREND = Array.from({ length: 24 }, (_, i) => ({
  t: hAgo(23 - i),
  error: 120  + (i > 15 ? (i - 15) * 180 : Math.random() * 40),
  warn:  480  + Math.sin(i * 0.3) * 100,
  info:  8400 + Math.cos(i * 0.2) * 800 + (i === 21 ? 6000 : 0), // CloudWatch spike
}));
const TOP_ERRORS = [
  { pattern:"FATAL: connection pool exhausted after 3 retries", service:"order-service",    count:2847, first_seen: hAgo(0.3), trend:"up"   },
  { pattern:"panic: nil pointer dereference in db.QueryRow()",  service:"order-service",    count:1203, first_seen: hAgo(0.3), trend:"up"   },
  { pattern:"redis: connection refused (timeout 500ms)",        service:"auth-service",     count:184,  first_seen: hAgo(6),   trend:"flat" },
  { pattern:"stripe webhook: context deadline exceeded",         service:"payment-service",  count:47,   first_seen: hAgo(10),  trend:"down" },
  { pattern:"EmailProvider: rate limit exceeded (429)",          service:"notification-svc", count:892,  first_seen: hAgo(2),   trend:"up"   },
];
const K8S_EVENTS = [
  { time:hAgo(0.1),  type:"Warning",  reason:"CrashLoopBackOff", object:"pod/order-service-8f9g0h",     message:"Back-off restarting failed container" },
  { time:hAgo(0.15), type:"Warning",  reason:"Failed",           object:"pod/order-service-8f9g0h",     message:"Error: failed to start container: OCI runtime error" },
  { time:hAgo(0.3),  type:"Normal",   reason:"Pulled",           object:"pod/order-service-8f9g0h",     message:"Successfully pulled image order-service:v2.4.1" },
  { time:hAgo(0.3),  type:"Normal",   reason:"Killing",          object:"pod/order-service-8f9g0h-old", message:"Stopping container order-service (deadline exceeded)" },
  { time:hAgo(0.5),  type:"Normal",   reason:"ScalingReplicaSet",object:"deployment/payment-service",   message:"Scaled up replica set to 7" },
  { time:hAgo(1),    type:"Warning",  reason:"FailedMount",      object:"pod/notification-svc-2b3c",    message:"Unable to attach volume: timeout" },
  { time:hAgo(2),    type:"Normal",   reason:"Completed",        object:"job/db-migration-4821",        message:"Job completed successfully" },
];

// ══════════════════════════════════════════════════════════════════════════════
//  Sub-dashboards
// ══════════════════════════════════════════════════════════════════════════════

function OverviewDash() {
  return (
    <div className="space-y-5">
      {/* KPI row */}
      <div className="grid grid-cols-4 gap-3">
        <MetricCard icon={Activity}       label="Health Score"    value="72/100"  color="text-amber-400"  sub="Degraded" trend="down" trendVal="-8 pts today"/>
        <MetricCard icon={AlertTriangle}  label="Active Incidents" value="3"      color="text-red-400"    sub="2 critical, 1 warning" trend="up" trendVal="+2"/>
        <MetricCard icon={Target}         label="SLO Compliance"  value="84.2%"   color="text-amber-400"  sub="Target: 99%" trend="down" trendVal="-14.8%"/>
        <MetricCard icon={DollarSign}     label="Monthly Spend"   value="$34.8k"  color="text-green-400"  sub="91.6% of $38k budget" trend="up" trendVal="+10.7% MoM"/>
        <MetricCard icon={Clock}          label="MTTA (30d avg)"  value="3.2 min" color="text-indigo-400"  sub="↓ improved vs 4.8m" trend="down" trendVal="-33%"/>
        <MetricCard icon={Zap}            label="MTTR (30d avg)"  value="23 min"  color="text-indigo-400"  sub="↓ improved vs 31m" trend="down" trendVal="-26%"/>
        <MetricCard icon={GitBranch}      label="Deploys / week"  value="8"       color="text-blue-400"   sub="Elite tier (DORA)" trend="flat" trendVal="stable"/>
        <MetricCard icon={Shield}         label="Change Fail Rate" value="12.5%"  color="text-amber-400"  sub="Target: < 15%" trend="up" trendVal="+2.5%"/>
      </div>

      <div className="grid grid-cols-3 gap-5">
        {/* Alert timeline */}
        <Card className="col-span-2 p-4">
          <SectionTitle>Alert Volume — Last 24 Hours</SectionTitle>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={ALERTS_24H}>
              <defs>
                <linearGradient id="gcrit" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={C.red}   stopOpacity={0.4}/>
                  <stop offset="95%" stopColor={C.red}   stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="gwarn" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={C.amber} stopOpacity={0.3}/>
                  <stop offset="95%" stopColor={C.amber} stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis dataKey="h" tick={{fill:"#64748b",fontSize:9}} interval={3}/>
              <YAxis tick={{fill:"#64748b",fontSize:9}} allowDecimals={false}/>
              <Tooltip {...customTooltip}/>
              <Legend wrapperStyle={{fontSize:11}}/>
              <Area type="monotone" dataKey="critical" stroke={C.red}   fill="url(#gcrit)" strokeWidth={2} name="Critical"/>
              <Area type="monotone" dataKey="warning"  stroke={C.amber} fill="url(#gwarn)" strokeWidth={2} name="Warning"/>
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        {/* Service health grid */}
        <Card className="p-4">
          <SectionTitle>Service Health</SectionTitle>
          <div className="space-y-2">
            {[
              {name:"api-gateway",       status:"healthy",  uptime:99.99},
              {name:"auth-service",      status:"degraded", uptime:99.95},
              {name:"payment-service",   status:"degraded", uptime:99.1 },
              {name:"order-service",     status:"down",     uptime:0    },
              {name:"inventory-service", status:"healthy",  uptime:99.97},
              {name:"notification-svc",  status:"degraded", uptime:99.5 },
            ].map(s => (
              <div key={s.name} className="flex items-center gap-2">
                <StatusDot status={s.status}/>
                <span className="text-xs text-slate-300 font-mono flex-1 truncate">{s.name}</span>
                <span className={`text-xs font-mono ${s.uptime>=99.5?"text-green-400":s.uptime>0?"text-amber-400":"text-red-400"}`}>
                  {s.uptime===0?"DOWN":`${s.uptime.toFixed(2)}%`}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-[#1e2535] grid grid-cols-3 gap-2 text-center">
            <div><div className="text-lg font-bold text-green-400">3</div><div className="text-xs text-slate-500">Healthy</div></div>
            <div><div className="text-lg font-bold text-amber-400">3</div><div className="text-xs text-slate-500">Degraded</div></div>
            <div><div className="text-lg font-bold text-red-400">1</div><div className="text-xs text-slate-500">Down</div></div>
          </div>
        </Card>
      </div>

      {/* Active incidents + deploys */}
      <div className="grid grid-cols-3 gap-5">
        <Card className="col-span-2 p-4">
          <SectionTitle>Active Incidents</SectionTitle>
          <div className="space-y-2">
            {RECENT_INCIDENTS.slice(0, 5).map(inc => (
              <div key={inc.id} className="flex items-start gap-3 p-3 bg-[#0f1117] rounded-lg border border-[#1e2535]">
                <SeverityBadge sev={inc.severity}/>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-white truncate">{inc.title}</div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                    <span className="font-mono">{inc.service}</span>
                    <span className="flex items-center gap-1"><Clock size={10}/> {inc.duration}</span>
                    <span>MTTA {inc.mtta}</span>
                    {inc.mttr !== "—" && <span>MTTR {inc.mttr}</span>}
                  </div>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded flex-shrink-0 ${inc.status==="active"?"bg-red-950/40 text-red-400":"bg-green-950/40 text-green-400"}`}>
                  {inc.status}
                </span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-4">
          <SectionTitle>Deployments — 7 Days</SectionTitle>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={DEPLOYS_7D}>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis dataKey="day" tick={{fill:"#64748b",fontSize:9}}/>
              <YAxis tick={{fill:"#64748b",fontSize:9}} allowDecimals={false}/>
              <Tooltip {...customTooltip}/>
              <Bar dataKey="success" fill={C.green}  name="Success" stackId="a" radius={[0,0,0,0]}/>
              <Bar dataKey="failed"  fill={C.red}    name="Failed"  stackId="a" radius={[3,3,0,0]}/>
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-2 flex justify-between text-xs text-slate-500">
            <span>✅ 22 succeeded</span>
            <span>❌ 3 failed (12.5%)</span>
          </div>
        </Card>
      </div>
    </div>
  );
}

function AppPerfDash() {
  return (
    <div className="space-y-5">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <MetricCard icon={Zap}          label="Avg Apdex Score" value="0.72"    color="text-amber-400"  sub="Target: > 0.94" trend="down" trendVal="-0.22"/>
        <MetricCard icon={Activity}     label="Total RPS"       value="2,873"   color="text-indigo-400" sub="across 6 services"/>
        <MetricCard icon={AlertTriangle}label="Error Rate (avg)"value="17.1%"   color="text-red-400"    sub="order-service driving spike" trend="up" trendVal="+16.9%"/>
        <MetricCard icon={Clock}        label="p99 Latency (avg)"value="92ms"   color="text-amber-400"  sub="excl. order-service" trend="up" trendVal="+18ms"/>
      </div>

      {/* Error rate + Latency charts */}
      <div className="grid grid-cols-2 gap-5">
        <Card className="p-4">
          <SectionTitle>Error Rate by Service — Last 24h</SectionTitle>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={ERROR_RATE_SERIES}>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis dataKey="t" tick={{fill:"#64748b",fontSize:9}} interval={5}/>
              <YAxis tick={{fill:"#64748b",fontSize:9}} domain={[0,100]}/>
              <Tooltip {...customTooltip}/>
              <Legend wrapperStyle={{fontSize:10}}/>
              <Line type="monotone" dataKey="order-service"    stroke={C.red}    strokeWidth={2} dot={false} name="order-svc"/>
              <Line type="monotone" dataKey="notification-svc" stroke={C.amber}  strokeWidth={1.5} dot={false} name="notif-svc"/>
              <Line type="monotone" dataKey="auth-service"     stroke={C.blue}   strokeWidth={1.5} dot={false} name="auth-svc"/>
              <Line type="monotone" dataKey="payment-service"  stroke={C.green}  strokeWidth={1}   dot={false} name="payment-svc"/>
            </LineChart>
          </ResponsiveContainer>
        </Card>
        <Card className="p-4">
          <SectionTitle>p99 Latency (ms) — Last 24h</SectionTitle>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={LATENCY_SERIES}>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis dataKey="t" tick={{fill:"#64748b",fontSize:9}} interval={5}/>
              <YAxis tick={{fill:"#64748b",fontSize:9}}/>
              <Tooltip {...customTooltip}/>
              <Legend wrapperStyle={{fontSize:10}}/>
              <Line type="monotone" dataKey="auth-service"      stroke={C.amber}  strokeWidth={2} dot={false} name="auth-svc"/>
              <Line type="monotone" dataKey="api-gateway"       stroke={C.indigo} strokeWidth={1.5} dot={false} name="api-gw"/>
              <Line type="monotone" dataKey="payment-service"   stroke={C.green}  strokeWidth={1.5} dot={false} name="payment-svc"/>
              <Line type="monotone" dataKey="inventory-service" stroke={C.teal}   strokeWidth={1} dot={false} name="inventory"/>
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Apdex + Service table */}
      <div className="grid grid-cols-5 gap-5">
        <Card className="col-span-2 p-4">
          <SectionTitle>Apdex Score by Service</SectionTitle>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={APDEX_DATA} layout="vertical" margin={{left:40}}>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis type="number" domain={[0,100]} tick={{fill:"#64748b",fontSize:9}}/>
              <YAxis type="category" dataKey="name" tick={{fill:"#94a3b8",fontSize:9}} width={55}/>
              <Tooltip {...customTooltip} formatter={(v: any) => [(v/100).toFixed(2),"Apdex"]}/>
              <Bar dataKey="value" radius={[0,3,3,0]}>
                {APDEX_DATA.map((e,i)=><Cell key={i} fill={e.value>=94?C.green:e.value>=70?C.amber:C.red}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card className="col-span-3 p-4">
          <SectionTitle>Service Performance Table</SectionTitle>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-[#1e2535]">
                <th className="text-left pb-2">Service</th>
                <th className="text-right pb-2">Error %</th>
                <th className="text-right pb-2">p99 (ms)</th>
                <th className="text-right pb-2">RPS</th>
                <th className="text-right pb-2">Apdex</th>
                <th className="text-right pb-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e2535]">
              {SERVICES_APM.map(s => (
                <tr key={s.name} className="hover:bg-[#1a2236]/50">
                  <td className="py-2 font-mono text-slate-300">{s.name.replace("-service","")}</td>
                  <td className={`py-2 text-right font-mono ${s.error_rate>1?"text-red-400":s.error_rate>0.5?"text-amber-400":"text-green-400"}`}>{s.error_rate.toFixed(1)}%</td>
                  <td className={`py-2 text-right font-mono ${s.latency_p99>500?"text-red-400":s.latency_p99>200?"text-amber-400":"text-slate-300"}`}>{s.latency_p99||"—"}</td>
                  <td className="py-2 text-right font-mono text-slate-400">{s.rps.toLocaleString()}</td>
                  <td className={`py-2 text-right font-mono ${s.apdex>=0.94?"text-green-400":s.apdex>=0.7?"text-amber-400":"text-red-400"}`}>{s.apdex.toFixed(2)}</td>
                  <td className="py-2 text-right"><StatusDot status={s.status}/></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {/* Top endpoints */}
      <Card className="p-4">
        <SectionTitle>Top Endpoints by Error Rate</SectionTitle>
        <table className="w-full text-xs">
          <thead><tr className="text-slate-500 border-b border-[#1e2535]">
            <th className="text-left pb-2">Endpoint</th>
            <th className="text-left pb-2">Service</th>
            <th className="text-right pb-2">p99</th>
            <th className="text-right pb-2">RPS</th>
            <th className="text-right pb-2">Error Rate</th>
          </tr></thead>
          <tbody className="divide-y divide-[#1e2535]">
            {TOP_ENDPOINTS.map((e,i)=>(
              <tr key={i} className="hover:bg-[#1a2236]/50">
                <td className="py-2 font-mono text-slate-300">{e.endpoint}</td>
                <td className="py-2 text-slate-500">{e.service.replace("-service","")}</td>
                <td className={`py-2 text-right font-mono ${e.p99.includes("∞")?"text-red-400":"text-slate-300"}`}>{e.p99}</td>
                <td className="py-2 text-right font-mono text-slate-400">{e.rps}</td>
                <td className={`py-2 text-right font-mono ${parseFloat(e.errors)>1?"text-red-400":parseFloat(e.errors)>0.5?"text-amber-400":"text-green-400"}`}>{e.errors}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function InfraDash() {
  return (
    <div className="space-y-5">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <MetricCard icon={Server}    label="Nodes"          value="3 / 3"   color="text-indigo-400" sub="All healthy"/>
        <MetricCard icon={Layers}    label="Pods Running"   value="14 / 16" color="text-amber-400"  sub="1 CrashLoop · 1 Pending" trend="down" trendVal="-2 pods"/>
        <MetricCard icon={Wifi}      label="Network In"     value="655 MB/s" color="text-blue-400"   sub="cluster total"/>
        <MetricCard icon={HardDrive} label="Storage Used"   value="46%"     color="text-teal-400"   sub="avg across nodes" trend="up" trendVal="+3% today"/>
      </div>

      {/* Node table */}
      <Card className="p-4">
        <SectionTitle>Node Utilization (USE Metrics)</SectionTitle>
        <table className="w-full text-xs">
          <thead><tr className="text-slate-500 border-b border-[#1e2535]">
            <th className="text-left pb-2">Node</th>
            <th className="text-right pb-2">CPU %</th>
            <th className="text-right pb-2">Memory %</th>
            <th className="text-right pb-2">Pods</th>
            <th className="text-right pb-2">Disk %</th>
            <th className="text-right pb-2">Net In (MB/s)</th>
            <th className="text-right pb-2">Net Out (MB/s)</th>
          </tr></thead>
          <tbody className="divide-y divide-[#1e2535]">
            {NODES.map(n=>(
              <tr key={n.name} className="hover:bg-[#1a2236]/50">
                <td className="py-2 font-mono text-slate-300">{n.name}</td>
                <td className={`py-2 text-right font-mono ${n.cpu>85?"text-red-400":n.cpu>70?"text-amber-400":"text-green-400"}`}>{n.cpu}%</td>
                <td className={`py-2 text-right font-mono ${n.memory>90?"text-red-400":n.memory>80?"text-amber-400":"text-green-400"}`}>{n.memory}%</td>
                <td className="py-2 text-right font-mono text-slate-400">{n.pods}/{n.max_pods}</td>
                <td className={`py-2 text-right font-mono ${n.disk>80?"text-red-400":n.disk>60?"text-amber-400":"text-slate-300"}`}>{n.disk}%</td>
                <td className="py-2 text-right font-mono text-slate-400">{n.net_in}</td>
                <td className="py-2 text-right font-mono text-slate-400">{n.net_out}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="grid grid-cols-3 gap-5">
        {/* Pod status donut */}
        <Card className="p-4 flex flex-col">
          <SectionTitle>Pod Status Distribution</SectionTitle>
          <div className="flex-1 flex flex-col items-center justify-center">
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie data={POD_STATUS} cx="50%" cy="50%" innerRadius={45} outerRadius={70} dataKey="value" paddingAngle={2}>
                  {POD_STATUS.map((e,i)=><Cell key={i} fill={e.color}/>)}
                </Pie>
                <Tooltip {...customTooltip}/>
              </PieChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-x-4 gap-y-1 justify-center mt-1">
              {POD_STATUS.map(p=>(
                <span key={p.name} className="text-xs flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full" style={{background:p.color}}/>
                  <span className="text-slate-400">{p.name}</span>
                  <span className="text-white font-mono">{p.value}</span>
                </span>
              ))}
            </div>
          </div>
        </Card>

        {/* CPU trend */}
        <Card className="p-4">
          <SectionTitle>CPU Utilization — 24h</SectionTitle>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={CPU_TREND_24H}>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis dataKey="t" tick={{fill:"#64748b",fontSize:9}} interval={5}/>
              <YAxis tick={{fill:"#64748b",fontSize:9}} domain={[0,100]}/>
              <Tooltip {...customTooltip}/>
              <Legend wrapperStyle={{fontSize:10}}/>
              <Line type="monotone" dataKey="node-1" stroke={C.indigo} strokeWidth={2} dot={false}/>
              <Line type="monotone" dataKey="node-2" stroke={C.amber}  strokeWidth={2} dot={false}/>
              <Line type="monotone" dataKey="node-3" stroke={C.green}  strokeWidth={1.5} dot={false}/>
            </LineChart>
          </ResponsiveContainer>
        </Card>

        {/* Memory trend */}
        <Card className="p-4">
          <SectionTitle>Memory Utilization — 24h</SectionTitle>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={MEM_TREND_24H}>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis dataKey="t" tick={{fill:"#64748b",fontSize:9}} interval={5}/>
              <YAxis tick={{fill:"#64748b",fontSize:9}} domain={[0,100]}/>
              <Tooltip {...customTooltip}/>
              <Legend wrapperStyle={{fontSize:10}}/>
              <Line type="monotone" dataKey="node-1" stroke={C.indigo} strokeWidth={2} dot={false}/>
              <Line type="monotone" dataKey="node-2" stroke={C.red}    strokeWidth={2} dot={false} name="node-2 ⚠️"/>
              <Line type="monotone" dataKey="node-3" stroke={C.green}  strokeWidth={1.5} dot={false}/>
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-5">
        <Card className="p-4">
          <SectionTitle>Network I/O — Last Hour</SectionTitle>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={NETWORK_IO}>
              <defs>
                <linearGradient id="gin"  x1="0" y1="0" x2="0" y2="1"><stop offset="5%"  stopColor={C.indigo} stopOpacity={0.3}/><stop offset="95%" stopColor={C.indigo} stopOpacity={0}/></linearGradient>
                <linearGradient id="gout" x1="0" y1="0" x2="0" y2="1"><stop offset="5%"  stopColor={C.teal}   stopOpacity={0.3}/><stop offset="95%" stopColor={C.teal}   stopOpacity={0}/></linearGradient>
              </defs>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis dataKey="t" tick={{fill:"#64748b",fontSize:9}}/>
              <YAxis tick={{fill:"#64748b",fontSize:9}}/>
              <Tooltip {...customTooltip}/>
              <Legend wrapperStyle={{fontSize:10}}/>
              <Area type="monotone" dataKey="in_mbps"  stroke={C.indigo} fill="url(#gin)"  name="In (MB/s)"/>
              <Area type="monotone" dataKey="out_mbps" stroke={C.teal}   fill="url(#gout)" name="Out (MB/s)"/>
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card className="p-4">
          <SectionTitle>Container Restarts — Last Hour</SectionTitle>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={RESTARTS_TREND}>
              <defs>
                <linearGradient id="grest" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={C.red} stopOpacity={0.4}/>
                  <stop offset="95%" stopColor={C.red} stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis dataKey="t" tick={{fill:"#64748b",fontSize:9}}/>
              <YAxis tick={{fill:"#64748b",fontSize:9}} allowDecimals={false}/>
              <Tooltip {...customTooltip}/>
              <Area type="monotone" dataKey="restarts" stroke={C.red} fill="url(#grest)" strokeWidth={2} name="Restarts"/>
            </AreaChart>
          </ResponsiveContainer>
        </Card>
      </div>
    </div>
  );
}

function CostDash() {
  return (
    <div className="space-y-5">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <MetricCard icon={DollarSign}   label="MTD Spend"         value="$34,820" color="text-green-400"  sub="91.6% of $38k budget" trend="up" trendVal="+10.7% MoM"/>
        <MetricCard icon={AlertTriangle}label="Identified Waste"  value="$7,240"  color="text-amber-400"  sub="20.8% of total spend" trend="up" trendVal="+18.7%"/>
        <MetricCard icon={TrendingDown} label="Quick Win Savings"  value="$4,600"  color="text-teal-400"   sub="Low effort, this week"/>
        <MetricCard icon={Target}       label="Projected Month-end"value="$40.2k" color="text-red-400"    sub="Exceeds $38k budget" trend="up" trendVal="+5.8%"/>
      </div>

      <div className="grid grid-cols-3 gap-5">
        {/* 30-day trend */}
        <Card className="col-span-2 p-4">
          <SectionTitle>30-Day Spend vs Budget ($)</SectionTitle>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={COST_30D}>
              <defs>
                <linearGradient id="gcost" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={C.indigo} stopOpacity={0.3}/>
                  <stop offset="95%" stopColor={C.indigo} stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis dataKey="d" tick={{fill:"#64748b",fontSize:9}} interval={4}/>
              <YAxis tick={{fill:"#64748b",fontSize:9}} tickFormatter={(v: number)=>`$${(v/1000).toFixed(1)}k`}/>
              <Tooltip {...customTooltip} formatter={(v: any) => [`$${Number(v).toLocaleString()}`, ""]}/>
              <Legend wrapperStyle={{fontSize:10}}/>
              <Area type="monotone" dataKey="actual" stroke={C.indigo} fill="url(#gcost)" strokeWidth={2} name="Actual Spend"/>
              <Line type="monotone" dataKey="budget" stroke={C.red} strokeWidth={1} strokeDasharray="5 5" dot={false} name="Daily Budget" data={COST_30D}/>
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        {/* Spend by service pie */}
        <Card className="p-4">
          <SectionTitle>Spend by Service</SectionTitle>
          <ResponsiveContainer width="100%" height={150}>
            <PieChart>
              <Pie data={SPEND_BY_SVC} cx="50%" cy="50%" outerRadius={65} dataKey="value" paddingAngle={2}>
                {SPEND_BY_SVC.map((_,i)=><Cell key={i} fill={PIE_COLORS[i]}/>)}
              </Pie>
              <Tooltip {...customTooltip} formatter={(v: any)=>[`$${Number(v).toLocaleString()}`,""]}/>
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-1 mt-1">
            {SPEND_BY_SVC.slice(0,4).map((s,i)=>(
              <div key={s.name} className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{background:PIE_COLORS[i]}}/><span className="text-slate-400">{s.name}</span></span>
                <span className="font-mono text-white">${(s.value/1000).toFixed(1)}k</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-5">
        {/* Waste breakdown */}
        <Card className="p-4">
          <SectionTitle>Waste Breakdown ($/month)</SectionTitle>
          <div className="space-y-3">
            {WASTE.map(w=>(
              <div key={w.category}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-400 truncate pr-2">{w.category}</span>
                  <span className="text-amber-400 font-mono flex-shrink-0">${w.waste.toLocaleString()}/mo</span>
                </div>
                <div className="h-1.5 bg-[#1e2535] rounded-full overflow-hidden">
                  <div className="h-full bg-amber-500/60 rounded-full" style={{width:`${w.pct*4}%`}}/>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Cost by team */}
        <Card className="p-4">
          <SectionTitle>Cost by Team (Chargeback)</SectionTitle>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={COST_BY_TEAM} layout="vertical" margin={{left:50}}>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis type="number" tick={{fill:"#64748b",fontSize:9}} tickFormatter={(v:number)=>`$${(v/1000).toFixed(1)}k`}/>
              <YAxis type="category" dataKey="team" tick={{fill:"#94a3b8",fontSize:10}} width={60}/>
              <Tooltip {...customTooltip} formatter={(v:any)=>[`$${Number(v).toLocaleString()}`,""]}/>
              <Bar dataKey="cost" fill={C.indigo} radius={[0,3,3,0]}>
                {COST_BY_TEAM.map((_,i)=><Cell key={i} fill={PIE_COLORS[i]}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Savings opportunities */}
      <Card className="p-4">
        <SectionTitle>Savings Opportunities — Ranked by ROI</SectionTitle>
        <table className="w-full text-xs">
          <thead><tr className="text-slate-500 border-b border-[#1e2535]">
            <th className="text-left pb-2">Action</th>
            <th className="text-right pb-2">Savings/mo</th>
            <th className="text-right pb-2">Effort</th>
            <th className="text-right pb-2">Risk</th>
          </tr></thead>
          <tbody className="divide-y divide-[#1e2535]">
            {[
              {action:"Fix CloudWatch debug logging (kubectl set env)", savings:820, effort:"Low (2 min)", risk:"None"},
              {action:"Downsize analytics-worker EC2 m5.4xl → m5.lg", savings:480, effort:"Low (30 min)", risk:"Low"},
              {action:"Enable cluster autoscaler (6 → 4 nodes)",        savings:960, effort:"Medium (1h)", risk:"Low"},
              {action:"Migrate prod-reporting-db to Aurora Serverless",  savings:1520,effort:"Medium (3h)", risk:"Low"},
              {action:"Resize elasticsearch PVC 2TB → 300GB",           savings:182, effort:"Low (30 min)",risk:"Low"},
            ].map((r,i)=>(
              <tr key={i} className="hover:bg-[#1a2236]/50">
                <td className="py-2 text-slate-300">{r.action}</td>
                <td className="py-2 text-right font-mono text-green-400">${r.savings.toLocaleString()}</td>
                <td className="py-2 text-right text-slate-400">{r.effort}</td>
                <td className="py-2 text-right text-slate-400">{r.risk}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function ReliabilityDash() {
  return (
    <div className="space-y-5">
      {/* DORA KPIs */}
      <div className="grid grid-cols-4 gap-3">
        {DORA.map(d=>(
          <Card key={d.metric} className="p-4">
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">{d.metric}</div>
            <div className="text-xl font-bold text-white">{d.value}</div>
            <div className="text-xs mt-1 font-medium" style={{color:d.color}}>{d.rating}</div>
          </Card>
        ))}
      </div>

      {/* SLO Scorecard */}
      <Card className="p-4">
        <SectionTitle>SLO Scorecard — Current Period</SectionTitle>
        <table className="w-full text-xs">
          <thead><tr className="text-slate-500 border-b border-[#1e2535]">
            <th className="text-left pb-2">Service</th>
            <th className="text-right pb-2">Error Rate</th>
            <th className="text-right pb-2">SLO</th>
            <th className="text-right pb-2">p99 Latency</th>
            <th className="text-right pb-2">SLO</th>
            <th className="text-right pb-2">Availability</th>
            <th className="text-right pb-2">Budget Left</th>
          </tr></thead>
          <tbody className="divide-y divide-[#1e2535]">
            {SLO_DATA.map(s=>(
              <tr key={s.service} className="hover:bg-[#1a2236]/50">
                <td className="py-2 font-mono text-slate-300">{s.service.replace("-service","")}</td>
                <td className={`py-2 text-right font-mono ${s.error_actual>s.error_slo?"text-red-400":"text-green-400"}`}>{s.error_actual.toFixed(1)}%</td>
                <td className="py-2 text-right text-slate-600">&lt;{s.error_slo}%</td>
                <td className={`py-2 text-right font-mono ${s.lat_actual>s.lat_slo?"text-red-400":s.lat_actual>s.lat_slo*0.8?"text-amber-400":"text-green-400"}`}>{s.lat_actual||"—"}ms</td>
                <td className="py-2 text-right text-slate-600">&lt;{s.lat_slo}ms</td>
                <td className="py-2 text-right"><TrafficLight pct={s.avail}/></td>
                <td className="py-2 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <div className="w-16 h-1.5 bg-[#1e2535] rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${s.budget_pct>50?"bg-green-500":s.budget_pct>20?"bg-amber-500":"bg-red-500"}`} style={{width:`${s.budget_pct}%`}}/>
                    </div>
                    <span className={`font-mono text-xs ${s.budget_pct>50?"text-green-400":s.budget_pct>20?"text-amber-400":"text-red-400"}`}>{s.budget_pct}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        {/* Alert volume */}
        <Card className="p-4">
          <SectionTitle>Alert Volume — 7 Days</SectionTitle>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={ALERT_VOL_7D}>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis dataKey="d" tick={{fill:"#64748b",fontSize:9}}/>
              <YAxis tick={{fill:"#64748b",fontSize:9}} allowDecimals={false}/>
              <Tooltip {...customTooltip}/>
              <Legend wrapperStyle={{fontSize:10}}/>
              <Bar dataKey="critical" fill={C.red}   stackId="a" name="Critical"/>
              <Bar dataKey="warning"  fill={C.amber} stackId="a" name="Warning"/>
              <Bar dataKey="info"     fill={C.slate} stackId="a" name="Info" radius={[3,3,0,0]}/>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        {/* MTTR by service */}
        <Card className="p-4">
          <SectionTitle>MTTR by Service (minutes)</SectionTitle>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={MTTR_BY_SVC} layout="vertical" margin={{left:30}}>
              <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
              <XAxis type="number" tick={{fill:"#64748b",fontSize:9}}/>
              <YAxis type="category" dataKey="service" tick={{fill:"#94a3b8",fontSize:10}} width={50}/>
              <Tooltip {...customTooltip} formatter={(v:any)=>[`${v} min`,"MTTR"]}/>
              <Bar dataKey="mttr" radius={[0,3,3,0]}>
                {MTTR_BY_SVC.map((e,i)=><Cell key={i} fill={e.mttr<15?C.green:e.mttr<30?C.amber:C.red}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Error budget burndown */}
      <Card className="p-4">
        <SectionTitle>Error Budget Burndown — order-service (30 days)</SectionTitle>
        <ResponsiveContainer width="100%" height={160}>
          <AreaChart data={BUDGET_BURN}>
            <defs>
              <linearGradient id="gbudget" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={C.indigo} stopOpacity={0.3}/>
                <stop offset="95%" stopColor={C.indigo} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
            <XAxis dataKey="d" tick={{fill:"#64748b",fontSize:9}} interval={4}/>
            <YAxis tick={{fill:"#64748b",fontSize:9}} domain={[0,100]} tickFormatter={(v:number)=>`${v}%`}/>
            <Tooltip {...customTooltip} formatter={(v:any)=>[`${Number(v).toFixed(1)}%`,""]}/>
            <Legend wrapperStyle={{fontSize:10}}/>
            <Area type="monotone" dataKey="remaining" stroke={C.indigo} fill="url(#gbudget)" strokeWidth={2} name="Budget Remaining"/>
            <Line type="monotone" dataKey="ideal" stroke={C.green} strokeWidth={1} strokeDasharray="4 4" dot={false} name="Ideal Burn"/>
          </AreaChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}

function DiagnosticsDash() {
  return (
    <div className="space-y-5">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <MetricCard icon={Activity}     label="Log Volume (1h)"  value="128k lines" color="text-indigo-400" sub="incl. CloudWatch spike" trend="up" trendVal="+340%"/>
        <MetricCard icon={AlertTriangle}label="Error Logs (1h)"  value="4,050"      color="text-red-400"   sub="order-service driving" trend="up" trendVal="+2800%"/>
        <MetricCard icon={Zap}          label="K8s Events (1h)"  value="47"         color="text-amber-400" sub="6 Warning type"/>
        <MetricCard icon={GitBranch}    label="Deploys Today"    value="2"          color="text-blue-400"  sub="1 failed (order-svc)"/>
      </div>

      {/* Log volume trend */}
      <Card className="p-4">
        <SectionTitle>Log Volume by Severity — Last 24h</SectionTitle>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={LOG_VOL_TREND}>
            <defs>
              <linearGradient id="gerr" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={C.red}    stopOpacity={0.4}/><stop offset="95%" stopColor={C.red}    stopOpacity={0}/></linearGradient>
              <linearGradient id="gwrn" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={C.amber}  stopOpacity={0.3}/><stop offset="95%" stopColor={C.amber}  stopOpacity={0}/></linearGradient>
              <linearGradient id="ginf" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={C.slate}  stopOpacity={0.3}/><stop offset="95%" stopColor={C.slate}  stopOpacity={0}/></linearGradient>
            </defs>
            <CartesianGrid stroke="#1e2535" strokeDasharray="3 3"/>
            <XAxis dataKey="t" tick={{fill:"#64748b",fontSize:9}} interval={5}/>
            <YAxis tick={{fill:"#64748b",fontSize:9}} tickFormatter={(v:number)=>`${(v/1000).toFixed(0)}k`}/>
            <Tooltip {...customTooltip} formatter={(v:any)=>[Number(v).toLocaleString(),""]}/>
            <Legend wrapperStyle={{fontSize:10}}/>
            <Area type="monotone" dataKey="info"  stroke={C.slate} fill="url(#ginf)" strokeWidth={1} name="Info"/>
            <Area type="monotone" dataKey="warn"  stroke={C.amber} fill="url(#gwrn)" strokeWidth={1.5} name="Warning"/>
            <Area type="monotone" dataKey="error" stroke={C.red}   fill="url(#gerr)" strokeWidth={2} name="Error"/>
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        {/* Top errors */}
        <Card className="p-4">
          <SectionTitle>Top Error Patterns</SectionTitle>
          <div className="space-y-2">
            {TOP_ERRORS.map((e,i)=>(
              <div key={i} className="flex items-start gap-2 p-2 bg-[#0f1117] rounded-lg border border-[#1e2535]">
                <span className={`text-xs flex-shrink-0 mt-0.5 ${e.trend==="up"?"text-red-400":e.trend==="down"?"text-green-400":"text-slate-500"}`}>
                  {e.trend==="up"?<ArrowUp size={12}/>:e.trend==="down"?<ArrowDown size={12}/>:<Minus size={12}/>}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-slate-300 font-mono truncate">{e.pattern}</div>
                  <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-500">
                    <span>{e.service.replace("-service","")}</span>
                    <span className="text-red-400 font-mono">{e.count.toLocaleString()} occurrences</span>
                    <span>since {e.first_seen}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* K8s events */}
        <Card className="p-4">
          <SectionTitle>Kubernetes Events (recent)</SectionTitle>
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {K8S_EVENTS.map((e,i)=>(
              <div key={i} className="flex items-start gap-2 p-2 bg-[#0f1117] rounded-lg border border-[#1e2535]">
                <span className={`text-xs flex-shrink-0 px-1.5 py-0.5 rounded ${e.type==="Warning"?"bg-amber-950 text-amber-400":"bg-slate-800 text-slate-400"}`}>{e.type}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-slate-400 font-medium">{e.reason}</span>
                    <span className="text-slate-600 truncate">{e.object}</span>
                    <span className="text-slate-600 ml-auto flex-shrink-0">{e.time}</span>
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5 truncate">{e.message}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Deployment + incident correlation */}
      <Card className="p-4">
        <SectionTitle>Deployment Timeline (last 7 days) with Incidents</SectionTitle>
        <div className="relative">
          <ResponsiveContainer width="100%" height={60}>
            <BarChart data={DEPLOYS_7D} margin={{top:5,bottom:5}}>
              <XAxis dataKey="day" tick={{fill:"#64748b",fontSize:9}}/>
              <Bar dataKey="success" fill={C.green} stackId="a" name="Success" radius={[0,0,0,0]}/>
              <Bar dataKey="failed"  fill={C.red}   stackId="a" name="Failed"  radius={[3,3,0,0]}/>
              <Tooltip {...customTooltip}/>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-500/60"/> Successful deploy</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-500/60"/> Failed deploy → correlated incident</span>
          <span className="ml-auto text-slate-600">Correlation: 2/3 failures triggered incidents (67%)</span>
        </div>
      </Card>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
//  Main DashboardTab — multi-dashboard shell
// ══════════════════════════════════════════════════════════════════════════════

const TABS = [
  { id:"overview",     label:"Overview",        icon:Activity,      sub:"Executive" },
  { id:"app",          label:"App Performance", icon:Zap,           sub:"APM" },
  { id:"infra",        label:"Infrastructure",  icon:Server,        sub:"K8s / Cloud" },
  { id:"cost",         label:"Cost Intelligence",icon:DollarSign,   sub:"FinOps" },
  { id:"reliability",  label:"Reliability",     icon:Target,        sub:"SLO / DORA" },
  { id:"diagnostics",  label:"Diagnostics",     icon:Database,      sub:"Logs / Events" },
] as const;

type DashTab = typeof TABS[number]["id"];

export function DashboardTab({ get, post }: { get: any; post: any }) {
  const [active, setActive] = useState<DashTab>("overview");
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState("");

  async function analyzeAlert(alertName: string, service: string, message: string) {
    setAnalyzing(alertName);
    setAnalysisResult("");
    const r = await post("/api/v1/incidents/analyze", {
      alert_name: alertName, service, namespace:"production",
      description: message, deep_analysis: false,
    });
    setAnalysisResult(r?.analysis ?? "Analysis failed.");
    setAnalyzing(null);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Sub-tab bar */}
      <div className="flex items-center gap-1 px-6 pt-4 pb-0 border-b border-[#1e2535] flex-shrink-0 overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon, sub }) => (
          <button key={id} onClick={() => setActive(id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium rounded-t-lg border-b-2 transition-colors whitespace-nowrap flex-shrink-0 ${
              active === id
                ? "border-indigo-500 text-white bg-[#161b27]"
                : "border-transparent text-slate-500 hover:text-slate-300 hover:bg-[#161b27]/50"
            }`}>
            <Icon size={13}/>
            <span>{label}</span>
            <span className={`text-xs ${active===id?"text-slate-400":"text-slate-600"}`}>{sub}</span>
          </button>
        ))}
        <div className="ml-auto pb-2.5 pr-0 flex-shrink-0">
          <button onClick={() => {}} className="flex items-center gap-1 text-xs text-slate-500 hover:text-white transition-colors px-2">
            <RotateCcw size={11}/> Live
          </button>
        </div>
      </div>

      {/* AI analysis result strip */}
      {analysisResult && (
        <div className="mx-6 mt-3 p-3 bg-[#0b0e16] border border-indigo-600/30 rounded-xl flex-shrink-0">
          <div className="flex items-center gap-2 mb-1.5">
            <Brain size={12} className="text-indigo-400"/>
            <span className="text-xs font-semibold text-indigo-300">AI Root Cause Analysis</span>
            <button onClick={() => setAnalysisResult("")} className="ml-auto text-slate-600 hover:text-white text-xs">✕</button>
          </div>
          <div className="prose-ops text-xs max-h-40 overflow-y-auto">
            <ReactMarkdown>{analysisResult}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Dashboard content */}
      <div className="flex-1 overflow-y-auto p-6">
        {active === "overview"    && <OverviewDash/>}
        {active === "app"         && <AppPerfDash/>}
        {active === "infra"       && <InfraDash/>}
        {active === "cost"        && <CostDash/>}
        {active === "reliability" && <ReliabilityDash/>}
        {active === "diagnostics" && <DiagnosticsDash/>}
      </div>
    </div>
  );
}

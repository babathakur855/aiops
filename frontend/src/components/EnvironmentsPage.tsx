"use client";

import { useState, useCallback, useEffect } from "react";
import {
  Plus, Copy, CheckCircle2, XCircle, Loader2, Trash2,
  RefreshCw, Terminal, Download, ChevronDown, ChevronRight,
  Shield, Activity, Server, Clock,
} from "lucide-react";

interface Environment {
  env_id: string;
  env_name: string;
  status: "registered" | "active" | "revoked";
  first_seen: string | null;
  last_seen: string | null;
  data_points_received: number;
  services_tracked: string[];
  capabilities: string[];
}

interface EnrollResult {
  env_id: string;
  env_name: string;
  token: string;
  expires_at: string;
  install_command: string;
  alternative_commands: Record<string, string>;
}

// ─── Platform type definitions ────────────────────────────────────
type PlatformType = "kubernetes" | "ec2_linux" | "ecs" | "windows_vm" | "cloud_api";

interface PlatformDef {
  id: PlatformType;
  label: string;
  emoji: string;
  subtitle: string;
  installLabel: string;
  supports: string[];
  color: string;
  selectedClass: string;
}

const PLATFORM_TYPES: PlatformDef[] = [
  {
    id: "kubernetes",
    label: "Kubernetes",
    emoji: "⎈",
    subtitle: "DaemonSet — one agent per node",
    installLabel: "kubectl one-liner",
    supports: ["AWS EKS", "Azure AKS", "GCP GKE", "OpenShift", "ROSA", "ARO", "Vanilla k8s"],
    color: "text-indigo-400",
    selectedClass: "border-indigo-600/50 bg-indigo-950/20",
  },
  {
    id: "ec2_linux",
    label: "Linux VM / EC2",
    emoji: "🖥️",
    subtitle: "systemd service — curl | bash",
    installLabel: "bash one-liner",
    supports: ["AWS EC2", "Azure VM", "GCP Compute Engine", "On-premises Linux", "Any systemd Linux"],
    color: "text-orange-400",
    selectedClass: "border-orange-600/50 bg-orange-950/20",
  },
  {
    id: "ecs",
    label: "AWS ECS",
    emoji: "📦",
    subtitle: "Sidecar container in task definition",
    installLabel: "JSON task def snippet",
    supports: ["ECS Fargate", "ECS EC2 launch type"],
    color: "text-amber-400",
    selectedClass: "border-amber-600/50 bg-amber-950/20",
  },
  {
    id: "windows_vm",
    label: "Windows VM",
    emoji: "🪟",
    subtitle: "Windows Service — PowerShell",
    installLabel: "PowerShell script",
    supports: ["AWS EC2 Windows", "Azure Windows VM", "Windows Server 2019/2022", "On-premises Windows"],
    color: "text-sky-400",
    selectedClass: "border-sky-600/50 bg-sky-950/20",
  },
  {
    id: "cloud_api",
    label: "Cloud API only",
    emoji: "☁️",
    subtitle: "No agent — cloud APIs polled automatically",
    installLabel: "No install needed",
    supports: ["AWS managed services", "Azure PaaS", "GCP managed services", "Lambda, RDS, App Service…"],
    color: "text-green-400",
    selectedClass: "border-green-600/50 bg-green-950/20",
  },
];

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <button onClick={copy}
      className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-[#1e2535] hover:bg-[#2a3548] text-slate-400 hover:text-white rounded-lg transition-colors">
      {copied ? <><CheckCircle2 size={12} className="text-green-400" /> Copied!</> : <><Copy size={12} /> {label}</>}
    </button>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { cls: string; label: string }> = {
    active:     { cls: "bg-green-950/60 text-green-300 border-green-800/40",  label: "Active" },
    registered: { cls: "bg-amber-950/60 text-amber-300 border-amber-800/40",  label: "Registered" },
    revoked:    { cls: "bg-red-950/60 text-red-300 border-red-800/40",         label: "Revoked" },
  };
  const s = map[status] ?? map.registered;
  return <span className={`text-xs px-2 py-0.5 rounded-full border ${s.cls}`}>{s.label}</span>;
}

// ─── Add environment wizard ───────────────────────────────────────
function AddEnvironmentWizard({ post, onDone }: { post: (path: string, body?: object) => Promise<any>; onDone: () => void }) {
  const [platformType, setPlatformType] = useState<PlatformType>("kubernetes");
  const [envName, setEnvName] = useState("");
  const [capabilities, setCapabilities] = useState(["metrics", "logs", "events"]);
  const [enrollResult, setEnrollResult] = useState<EnrollResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeAltTab, setActiveAltTab] = useState(0);

  const selectedPlatform = PLATFORM_TYPES.find(p => p.id === platformType)!;

  const CAPS = [
    { id: "metrics", label: "Metrics", desc: "CPU, memory, disk, network, process stats" },
    { id: "logs",    label: "Logs / Events", desc: "Container logs, k8s events" },
    { id: "events",  label: "Events", desc: "Kubernetes & system events" },
    { id: "traces",  label: "Traces", desc: "OTLP distributed traces (opt-in)" },
  ];

  function toggleCap(id: string) {
    setCapabilities(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]);
  }

  async function generate() {
    const name = envName.trim();
    if (!name) { setError("Enter an environment name first"); return; }
    setLoading(true);
    setError("");
    try {
      const result = await post("/api/v1/collector/environments", {
        env_name: name,
        platform_type: platformType,
        capabilities,
      });
      if (result && result.token) {
        setEnrollResult(result);
      } else {
        setError(result?.detail || "Failed to generate token — check backend logs");
      }
    } catch (e: any) {
      setError(e?.message || "Unexpected error");
    } finally {
      setLoading(false);
    }
  }

  // Build tabs from the result's alternative_commands
  const altTabs = enrollResult
    ? Object.entries(enrollResult.alternative_commands).map(([key, content]) => ({
        key,
        label: key.replace(/_/g, " "),
        content: content as string,
      }))
    : [];

  // Security notes per platform
  const SECURITY_NOTES: Record<PlatformType, string[]> = {
    kubernetes:  ["Read-only RBAC — cannot exec, access secrets, or modify anything", "NetworkPolicy — egress to OpsBrain + k8s API only", "Non-root · read-only filesystem · all Linux capabilities dropped", "Resource limits: max 200m CPU / 256Mi memory"],
    ec2_linux:   ["Runs as non-root system user (otelcol-contrib)", "systemd hardening: NoNewPrivileges, ProtectSystem, PrivateTmp", "No inbound network ports opened", "Resource limits prevent hogging host CPU/memory"],
    ecs:          ["Sidecar is essential:false — won't take down your app if it crashes", "Separate IAM task role — no access to your app's secrets", "Resource limits: 128 CPU units / 256MB", "No port mappings exposed"],
    windows_vm:  ["Runs as LocalSystem with minimal permissions", "Service is isolated — no access to other services' data", "Resource limits enforced via Windows Job Objects"],
    cloud_api:   ["No agent deployed — zero footprint in your environment", "Cloud APIs are read-only (Cost Explorer, CloudWatch, Monitor)", "Credentials scoped to monitoring permissions only"],
  };

  return (
    <div className="bg-[#161b27] border border-indigo-600/30 rounded-xl p-5 space-y-4">
      <h2 className="text-sm font-semibold text-white">Add Environment</h2>

      {!enrollResult ? (
        <div className="space-y-4">

          {/* Step 1 — Platform type */}
          <div>
            <label className="text-xs text-slate-400 block mb-2">
              <span className="text-indigo-400 font-mono mr-1">1.</span> Choose your platform
            </label>
            <div className="grid grid-cols-1 gap-2">
              {PLATFORM_TYPES.map(pt => (
                <button key={pt.id} onClick={() => setPlatformType(pt.id)} type="button"
                  className={`flex items-center gap-3 p-3 rounded-xl border text-left transition-colors w-full ${
                    platformType === pt.id ? pt.selectedClass : "border-[#1e2535] hover:border-[#2a3548]"
                  }`}>
                  <span className="text-xl flex-shrink-0">{pt.emoji}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-medium ${pt.color}`}>{pt.label}</span>
                      <span className="text-xs text-slate-500">{pt.subtitle}</span>
                    </div>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {pt.supports.map(s => (
                        <span key={s} className="text-xs text-slate-600 bg-[#0f1117] px-1.5 py-0.5 rounded">{s}</span>
                      ))}
                    </div>
                  </div>
                  <div className={`w-4 h-4 rounded-full border-2 flex-shrink-0 ${
                    platformType === pt.id ? "border-indigo-400 bg-indigo-400" : "border-slate-600"
                  }`} />
                </button>
              ))}
            </div>
          </div>

          {/* Step 2 — Name */}
          <div>
            <label className="text-xs text-slate-400 block mb-1.5">
              <span className="text-indigo-400 font-mono mr-1">2.</span> Environment name
            </label>
            <input value={envName} onChange={e => { setEnvName(e.target.value); setError(""); }}
              placeholder={`e.g. Production ${selectedPlatform.supports[0]}`}
              onKeyDown={e => e.key === "Enter" && generate()}
              className="w-full bg-[#0f1117] border border-[#1e2535] focus:border-indigo-500/60 text-slate-200 text-sm rounded-lg px-3 py-2.5 outline-none transition-colors placeholder:text-slate-600" />
          </div>

          {/* Step 3 — Capabilities (collapsed for non-k8s) */}
          {(platformType === "kubernetes" || platformType === "ec2_linux") && (
            <div>
              <label className="text-xs text-slate-400 block mb-2">
                <span className="text-indigo-400 font-mono mr-1">3.</span> What to collect
              </label>
              <div className="grid grid-cols-2 gap-2">
                {CAPS.map(cap => (
                  <label key={cap.id}
                    className={`flex items-start gap-2 p-2.5 rounded-lg border cursor-pointer transition-colors ${
                      capabilities.includes(cap.id) ? "border-indigo-600/40 bg-indigo-950/20" : "border-[#1e2535] hover:border-[#2a3548]"
                    }`}>
                    <input type="checkbox" checked={capabilities.includes(cap.id)} onChange={() => toggleCap(cap.id)} className="mt-0.5" />
                    <div>
                      <div className="text-xs font-medium text-slate-300">{cap.label}</div>
                      <div className="text-xs text-slate-500">{cap.desc}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-950/40 border border-red-800/40 rounded-lg text-xs text-red-300">
              <XCircle size={12} className="flex-shrink-0" /> {error}
            </div>
          )}

          <button onClick={generate} disabled={loading} type="button"
            className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors">
            {loading
              ? <><Loader2 size={14} className="animate-spin" /> Generating…</>
              : <><Plus size={14} /> Generate {selectedPlatform.installLabel}</>}
          </button>
          {!envName.trim() && !error && (
            <p className="text-xs text-slate-600 text-center">Enter a name above then click Generate</p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {/* Success header */}
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} className="text-green-400 flex-shrink-0" />
            <span className="text-sm text-white font-medium">
              {selectedPlatform.emoji} <span className="text-indigo-300">{enrollResult.env_name}</span> — {selectedPlatform.label} install command ready
            </span>
          </div>

          {/* Security notes */}
          <div className="bg-[#0b0e16] border border-[#1e2535] rounded-lg p-3 text-xs text-slate-400 space-y-1">
            <div className="text-white font-medium mb-1.5 flex items-center gap-1.5">
              <Shield size={11} className="text-green-400" /> Security applied automatically:
            </div>
            {SECURITY_NOTES[platformType].map((note, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <CheckCircle2 size={10} className="text-green-400 flex-shrink-0" /> {note}
              </div>
            ))}
          </div>

          {/* Main install command */}
          <div>
            <div className="text-xs text-slate-400 mb-1.5 font-medium">
              {platformType === "ecs" ? "Add to your ECS task definition:" : "Run this command:"}
            </div>
            <div className="relative">
              <div className="absolute top-2 right-2">
                <CopyButton text={enrollResult.install_command} />
              </div>
              <pre className="bg-[#0b0e16] border border-[#1e2535] rounded-lg p-3 pr-20 text-xs text-green-300 font-mono whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto">
                {enrollResult.install_command}
              </pre>
            </div>
          </div>

          {/* Context hint per platform */}
          <p className="text-xs text-slate-500">
            {platformType === "kubernetes" && "Run in any terminal with kubectl access. Auto-detects EKS / AKS / GKE / OpenShift / ROSA / ARO."}
            {platformType === "ec2_linux"  && "Run on the EC2 instance, Azure VM, or GCP VM — requires sudo. Works on Amazon Linux, Ubuntu, RHEL, CentOS, Debian."}
            {platformType === "ecs"         && "Copy the JSON above and add it to your task definition's containerDefinitions array, then deploy a new revision."}
            {platformType === "windows_vm" && "Run in PowerShell as Administrator on the Windows VM or EC2 Windows instance."}
            {platformType === "cloud_api"  && "No agent needed. Add this cloud account as a Data Source in Connectors → Cloud Providers."}
          </p>

          {/* Alternative commands */}
          {altTabs.length > 0 && (
            <div>
              <div className="flex gap-1 mb-2 flex-wrap">
                {altTabs.map((tab, i) => (
                  <button key={tab.key} onClick={() => setActiveAltTab(i)}
                    className={`text-xs px-2.5 py-1 rounded-lg capitalize transition-colors ${
                      activeAltTab === i ? "bg-[#1e2535] text-white" : "text-slate-500 hover:text-slate-300"
                    }`}>
                    {tab.label}
                  </button>
                ))}
              </div>
              {altTabs[activeAltTab] && (
                <div className="relative">
                  <div className="absolute top-2 right-2">
                    <CopyButton text={altTabs[activeAltTab].content} />
                  </div>
                  <pre className="bg-[#0b0e16] border border-[#1e2535] rounded-lg p-3 pr-16 text-xs text-slate-300 font-mono whitespace-pre-wrap overflow-x-auto max-h-48 overflow-y-auto">
                    {altTabs[activeAltTab].content}
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* Waiting for connection */}
          <div className="flex items-center gap-2 p-3 bg-[#0f1117] border border-[#1e2535] rounded-lg">
            <div className="flex gap-1">
              {[0,1,2].map(n => <span key={n} className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: `${n * 0.2}s` }} />)}
            </div>
            <span className="text-xs text-slate-500">Waiting for <span className="text-slate-300">{enrollResult.env_name}</span> to connect…</span>
            <button onClick={onDone} className="ml-auto text-xs text-slate-600 hover:text-white transition-colors">Done</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Environment card ─────────────────────────────────────────────
function EnvironmentCard({ env, onRevoke, isAdmin }: {
  env: Environment;
  onRevoke: (id: string) => Promise<void>;
  isAdmin: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [revoking, setRevoking] = useState(false);

  const isActive  = env.status === "active";
  const isRevoked = env.status === "revoked";

  async function revoke() {
    if (!confirm(`Revoke access for "${env.env_name}"? The collector will stop sending data.`)) return;
    setRevoking(true);
    await onRevoke(env.env_id);
    setRevoking(false);
  }

  function timeAgo(ts: string | null) {
    if (!ts) return "Never";
    const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }

  return (
    <div className={`bg-[#161b27] border rounded-xl overflow-hidden transition-all ${
      isActive ? "border-green-800/30" : isRevoked ? "border-red-800/30 opacity-60" : "border-[#1e2535]"
    }`}>
      <div className="flex items-center gap-3 p-4 cursor-pointer" onClick={() => setExpanded(p => !p)}>
        {/* Status dot */}
        <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
          isActive ? "bg-green-400" : isRevoked ? "bg-red-400" : "bg-amber-400 animate-pulse"
        }`} />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-white">{env.env_name}</span>
            <StatusBadge status={env.status} />
            {env.capabilities.map(c => (
              <span key={c} className="text-xs text-slate-600 bg-[#0f1117] px-1.5 py-0.5 rounded">{c}</span>
            ))}
          </div>
          <div className="flex items-center gap-4 mt-1 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <Activity size={10} />
              {env.data_points_received.toLocaleString()} data points
            </span>
            {env.last_seen && (
              <span className="flex items-center gap-1">
                <Clock size={10} /> Last seen: {timeAgo(env.last_seen)}
              </span>
            )}
            {env.services_tracked.length > 0 && (
              <span className="flex items-center gap-1">
                <Server size={10} /> {env.services_tracked.length} services
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isAdmin && !isRevoked && (
            <button onClick={e => { e.stopPropagation(); revoke(); }} disabled={revoking}
              className="flex items-center gap-1 px-2 py-1 text-xs text-slate-500 hover:text-red-400 hover:bg-red-950/20 rounded-lg transition-colors">
              {revoking ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
              Revoke
            </button>
          )}
          {expanded ? <ChevronDown size={16} className="text-slate-500" /> : <ChevronRight size={16} className="text-slate-500" />}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-[#1e2535] p-4 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Environment ID", value: env.env_id },
              { label: "First Seen", value: env.first_seen ? new Date(env.first_seen).toLocaleString() : "—" },
              { label: "Last Seen", value: env.last_seen ? new Date(env.last_seen).toLocaleString() : "—" },
            ].map(({ label, value }) => (
              <div key={label} className="bg-[#0f1117] rounded-lg p-2.5">
                <div className="text-xs text-slate-500">{label}</div>
                <div className="text-xs text-slate-300 mt-0.5 font-mono truncate">{value}</div>
              </div>
            ))}
          </div>
          {env.services_tracked.length > 0 && (
            <div>
              <div className="text-xs text-slate-500 mb-2">Tracked services ({env.services_tracked.length})</div>
              <div className="flex flex-wrap gap-1.5">
                {env.services_tracked.map(s => (
                  <span key={s} className="text-xs bg-[#0f1117] border border-[#1e2535] text-slate-400 px-2 py-0.5 rounded font-mono">{s}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Demo environments for showcase ──────────────────────────────
const DEMO_ENVS: Environment[] = [
  {
    env_id: "env_prod_eks_use1",
    env_name: "Production EKS — us-east-1",
    status: "active",
    first_seen: new Date(Date.now() - 14 * 24 * 3600_000).toISOString(),
    last_seen: new Date(Date.now() - 45_000).toISOString(),
    data_points_received: 1_847_293,
    services_tracked: ["order-service", "payment-service", "auth-service", "notification-svc", "inventory-service", "api-gateway"],
    capabilities: ["metrics", "logs", "events"],
  },
  {
    env_id: "env_staging_eks_use1",
    env_name: "Staging EKS — us-east-1",
    status: "active",
    first_seen: new Date(Date.now() - 7 * 24 * 3600_000).toISOString(),
    last_seen: new Date(Date.now() - 3 * 60_000).toISOString(),
    data_points_received: 284_511,
    services_tracked: ["order-service", "payment-service", "auth-service"],
    capabilities: ["metrics", "logs"],
  },
  {
    env_id: "env_analytics_ec2",
    env_name: "Analytics Workers — EC2 Linux",
    status: "active",
    first_seen: new Date(Date.now() - 3 * 24 * 3600_000).toISOString(),
    last_seen: new Date(Date.now() - 90_000).toISOString(),
    data_points_received: 52_840,
    services_tracked: ["analytics-worker", "reporting-cron"],
    capabilities: ["metrics", "logs"],
  },
  {
    env_id: "env_dev_laptop",
    env_name: "Dev — Local k3s",
    status: "registered",
    first_seen: null,
    last_seen: null,
    data_points_received: 0,
    services_tracked: [],
    capabilities: ["metrics"],
  },
];

// ─── Main EnvironmentsPage ────────────────────────────────────────
export function EnvironmentsPage({ get, post, del, isAdmin }: {
  get: (p: string) => Promise<any>;
  post: (p: string, b?: any) => Promise<any>;
  del: (p: string) => Promise<any>;
  isAdmin: boolean;
}) {
  const [environments, setEnvironments] = useState<Environment[]>(DEMO_ENVS);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [collectorStatus, setCollectorStatus] = useState<any>(null);

  const load = useCallback(async () => {
    const [envs, status] = await Promise.all([
      get("/api/v1/collector/environments"),
      get("/api/v1/collector/status"),
    ]);
    if (envs) setEnvironments(Array.isArray(envs) ? envs : []);
    if (status) setCollectorStatus(status);
    setLoading(false);
  }, [get]);

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);

  async function revoke(env_id: string) {
    await del(`/api/v1/collector/environments/${env_id}`);
    await load();
  }

  const activeCount   = environments.filter(e => e.status === "active").length;
  const pendingCount  = environments.filter(e => e.status === "registered").length;

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <Server size={18} className="text-indigo-400" /> Monitored Environments
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            {activeCount} active · {pendingCount} awaiting connection · {environments.length} total
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="p-2 text-slate-500 hover:text-white hover:bg-[#161b27] rounded-lg transition-colors">
            <RefreshCw size={14} />
          </button>
          {isAdmin && (
            <button onClick={() => setShowAdd(p => !p)}
              className="flex items-center gap-1.5 px-3 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg transition-colors">
              {showAdd ? "Cancel" : <><Plus size={14} /> Add Environment</>}
            </button>
          )}
        </div>
      </div>

      {/* How it works explainer */}
      {!loading && environments.length === 0 && !showAdd && (
        <div className="bg-[#161b27] border border-[#1e2535] rounded-xl p-5">
          <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Terminal size={14} className="text-indigo-400" /> How to connect a Kubernetes cluster
          </h2>
          <div className="space-y-3 text-sm text-slate-400">
            <div className="flex gap-3">
              <span className="text-indigo-400 font-mono font-bold flex-shrink-0">1.</span>
              <span>Click <span className="text-white">"Add Environment"</span> and give it a name (e.g. "Production EKS us-east-1")</span>
            </div>
            <div className="flex gap-3">
              <span className="text-indigo-400 font-mono font-bold flex-shrink-0">2.</span>
              <span>Copy the one-liner install command that's generated</span>
            </div>
            <div className="flex gap-3">
              <span className="text-indigo-400 font-mono font-bold flex-shrink-0">3.</span>
              <span>Run it in any terminal with <code className="text-slate-300 bg-[#0f1117] px-1 rounded">kubectl</code> access to the cluster — works on EKS, AKS, GKE, OpenShift, ROSA, ARO</span>
            </div>
            <div className="flex gap-3">
              <span className="text-indigo-400 font-mono font-bold flex-shrink-0">4.</span>
              <span>The installer auto-detects the platform, applies security hardening, and the cluster appears here within 2 minutes</span>
            </div>
          </div>
          <div className="mt-4 bg-[#0f1117] border border-[#1e2535] rounded-lg p-3 text-xs text-slate-500">
            <span className="text-white font-medium">Security note:</span> The collector is read-only, network-isolated, and runs with minimal privileges. It cannot access secrets, execute into pods, or communicate with any service other than OpsBrain.
          </div>
          <button onClick={() => setShowAdd(true)}
            className="mt-4 w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg transition-colors">
            <Plus size={14} /> Add your first environment
          </button>
        </div>
      )}

      {/* Add environment wizard */}
      {showAdd && (
        <AddEnvironmentWizard post={post} onDone={() => { setShowAdd(false); load(); }} />
      )}

      {/* Collector cloud poller status */}
      {collectorStatus && (
        <div className="bg-[#161b27] border border-[#1e2535] rounded-xl p-4">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Cloud API Poller (agentless collection)
          </h2>
          <div className="flex items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${collectorStatus.scheduler_running ? "bg-green-400" : "bg-red-400 animate-pulse"}`} />
              <span className="text-slate-300">{collectorStatus.scheduler_running ? "Running" : "Stopped"}</span>
            </div>
            <div className="text-xs text-slate-500">
              {collectorStatus.metrics_summary?.total_series ?? 0} metric series ·
              {" "}{collectorStatus.metrics_summary?.total_data_points ?? 0} data points ·
              {" "}{collectorStatus.metrics_summary?.environments_tracked ?? 0} environments
            </div>
          </div>
        </div>
      )}

      {/* Environment list */}
      {!loading && environments.length > 0 && (
        <div className="space-y-3">
          {environments.map(env => (
            <EnvironmentCard key={env.env_id} env={env} onRevoke={revoke} isAdmin={isAdmin} />
          ))}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-8 text-slate-500">
          <Loader2 size={18} className="animate-spin mr-2" /> Loading environments…
        </div>
      )}
    </div>
  );
}

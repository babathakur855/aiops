"use client";

import { useState, useCallback, useEffect } from "react";
import {
  CheckCircle2, XCircle, Loader2, ChevronDown, ChevronUp,
  Trash2, Eye, EyeOff, RefreshCw, Plus, AlertTriangle,
  ExternalLink, Server, Radio,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────
interface CloudAccount {
  id: string;
  name: string;
  cloud: string;
  auth_method: string;
  account_id: string;
  region: string;
  enabled: boolean;
  healthy?: boolean;
  error?: string;
}

interface CloudSummary {
  hosting: {
    configured: boolean;
    cloud: string | null;
    name: string | null;
    id: string | null;
    region: string | null;
    auth_method: string | null;
  };
  data_sources: CloudAccount[];
}

// ─── Cloud provider metadata ──────────────────────────────────────
const CLOUDS = {
  aws:   { emoji: "☁️",  label: "AWS",   color: "orange", bgClass: "bg-orange-950/30 border-orange-700/50" },
  azure: { emoji: "🔷", label: "Azure", color: "sky",    bgClass: "bg-sky-950/30 border-sky-700/50" },
  gcp:   { emoji: "🌐", label: "GCP",   color: "teal",   bgClass: "bg-teal-950/30 border-teal-700/50" },
} as const;

type CloudKey = keyof typeof CLOUDS;

// ─── Hosting field definitions ───────────────────────────────────
const HOSTING_FIELDS: Record<CloudKey, { key: string; label: string; type: string; placeholder: string; help?: string; options?: {value:string;label:string}[]; showIf?: string }[]> = {
  aws: [
    {
      key: "auth_method", label: "Identity Method", type: "select", placeholder: "",
      options: [
        { value: "irsa", label: "IRSA — Pod Identity (EKS, recommended)" },
        { value: "instance_profile", label: "EC2 Instance Profile" },
        { value: "ecs_task_role", label: "ECS Task Role" },
        { value: "aws_profile", label: "AWS CLI Profile — local / on-prem" },
      ],
      help: "How OpsBrain authenticates as an AWS workload. Running locally? Use AWS CLI Profile or leave this section unconfigured and add accounts under Data Sources.",
    },
    { key: "region", label: "AWS Region", type: "text", placeholder: "us-east-1" },
    { key: "account_id", label: "AWS Account ID", type: "text", placeholder: "123456789012", help: "For display and audit purposes" },
    { key: "eks_cluster", label: "EKS Cluster Name", type: "text", placeholder: "my-eks-cluster", help: "The cluster OpsBrain is deployed on", showIf: "irsa" },
    { key: "irsa_role_arn", label: "IRSA Role ARN", type: "text", placeholder: "arn:aws:iam::123456789012:role/OpsBrainRole", help: "Annotate the OpsBrain k8s ServiceAccount with this role ARN", showIf: "irsa" },
    { key: "profile_name", label: "AWS CLI Profile Name", type: "text", placeholder: "default", help: "Named profile from ~/.aws/credentials or ~/.aws/config — leave blank for [default]", showIf: "aws_profile" },
  ],
  azure: [
    {
      key: "auth_method", label: "Identity Method", type: "select", placeholder: "",
      options: [
        { value: "system_managed_identity", label: "System-assigned Managed Identity (recommended)" },
        { value: "user_managed_identity", label: "User-assigned Managed Identity" },
        { value: "workload_identity", label: "Azure Workload Identity (AKS OIDC)" },
      ],
      help: "OpsBrain uses the AKS pod's identity — no client secrets to rotate",
    },
    { key: "subscription_id", label: "Subscription ID", type: "text", placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" },
    { key: "resource_group", label: "Resource Group", type: "text", placeholder: "rg-opsbrain-prod", help: "Resource group where OpsBrain AKS cluster lives" },
    { key: "aks_cluster", label: "AKS Cluster Name", type: "text", placeholder: "my-aks-cluster" },
    { key: "client_id", label: "Managed Identity Client ID", type: "text", placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", help: "Only required for user-assigned Managed Identity", showIf: "user_managed_identity" },
  ],
  gcp: [
    {
      key: "auth_method", label: "Identity Method", type: "select", placeholder: "",
      options: [
        { value: "workload_identity", label: "Workload Identity Federation (GKE, recommended)" },
        { value: "service_account_file", label: "Service Account JSON (file on pod)" },
      ],
      help: "Workload Identity binds the k8s ServiceAccount to a GCP Service Account — no key files",
    },
    { key: "project_id", label: "GCP Project ID", type: "text", placeholder: "my-gcp-project" },
    { key: "gke_cluster", label: "GKE Cluster Name", type: "text", placeholder: "my-gke-cluster" },
    { key: "region", label: "Region", type: "text", placeholder: "us-central1" },
    { key: "service_account_email", label: "GCP Service Account Email", type: "text", placeholder: "opsbrain@my-project.iam.gserviceaccount.com", help: "The GCP SA bound to the k8s ServiceAccount via Workload Identity" },
  ],
};

// ─── Data source field definitions ───────────────────────────────
const SOURCE_FIELDS: Record<CloudKey, { key: string; label: string; type: string; placeholder?: string; help?: string; options?: {value:string;label:string}[]; showIf?: string; required?: boolean }[]> = {
  aws: [
    { key: "name", label: "Account Name / Alias", type: "text", placeholder: "Production AWS", required: true },
    { key: "account_id", label: "AWS Account ID", type: "text", placeholder: "123456789012", required: true },
    {
      key: "auth_method", label: "Authentication", type: "select", placeholder: "",
      options: [
        { value: "iam_role", label: "IAM Role Assumption (cross-account, recommended)" },
        { value: "access_key", label: "Access Key + Secret (dev/testing only)" },
      ],
      help: "Use IAM Role in production — OpsBrain assumes it from its hosting identity",
    },
    { key: "role_arn", label: "IAM Role ARN", type: "text", placeholder: "arn:aws:iam::123456789012:role/OpsBrainMonitor", help: "Add a trust policy allowing OpsBrain's hosting role to assume this", showIf: "iam_role" },
    { key: "external_id", label: "External ID", type: "text", placeholder: "opsbrain-monitor-xyz", help: "Prevents confused deputy attacks", showIf: "iam_role" },
    { key: "access_key_id", label: "Access Key ID", type: "text", placeholder: "AKIAIOSFODNN7EXAMPLE", showIf: "access_key" },
    { key: "secret_access_key", label: "Secret Access Key", type: "password", placeholder: "", showIf: "access_key" },
    { key: "region", label: "Primary Region", type: "text", placeholder: "us-east-1", required: true },
    { key: "bedrock_model_id", label: "Bedrock Model (optional)", type: "select", placeholder: "",
      options: [
        { value: "", label: "— Not using Bedrock from this account —" },
        { value: "anthropic.claude-3-5-sonnet-20241022-v2:0", label: "Claude 3.5 Sonnet v2" },
        { value: "anthropic.claude-opus-4-7", label: "Claude Opus 4.7" },
      ],
    },
  ],
  azure: [
    { key: "name", label: "Subscription Name", type: "text", placeholder: "Production Azure", required: true },
    { key: "subscription_id", label: "Subscription ID", type: "text", placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", required: true },
    {
      key: "auth_method", label: "Authentication", type: "select", placeholder: "",
      options: [
        { value: "service_principal", label: "Service Principal (client ID + secret)" },
        { value: "delegated_managed_identity", label: "Delegated — use hosting Managed Identity" },
      ],
      help: "Delegated: OpsBrain's hosting Managed Identity is granted Reader on this subscription (no extra credentials)",
    },
    { key: "tenant_id", label: "Tenant ID", type: "text", placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", showIf: "service_principal" },
    { key: "client_id", label: "Client ID", type: "text", placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", showIf: "service_principal" },
    { key: "client_secret", label: "Client Secret", type: "password", placeholder: "", showIf: "service_principal" },
    { key: "openai_endpoint", label: "Azure OpenAI Endpoint (optional)", type: "text", placeholder: "https://your-resource.openai.azure.com/" },
    { key: "openai_deployment", label: "OpenAI Deployment Name", type: "text", placeholder: "gpt-4o" },
    { key: "log_analytics_workspace_id", label: "Log Analytics Workspace ID (optional)", type: "text", placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" },
  ],
  gcp: [
    { key: "name", label: "Project Name", type: "text", placeholder: "ML Platform Project", required: true },
    { key: "project_id", label: "GCP Project ID", type: "text", placeholder: "my-gcp-project", required: true },
    {
      key: "auth_method", label: "Authentication", type: "select", placeholder: "",
      options: [
        { value: "service_account_json", label: "Service Account JSON key" },
        { value: "delegated_workload_identity", label: "Delegated — use hosting Workload Identity" },
      ],
      help: "Delegated: OpsBrain's hosting GCP SA is granted IAM roles on this project (no key file needed)",
    },
    { key: "service_account_json", label: "Service Account JSON", type: "textarea", placeholder: '{"type": "service_account", ...}', showIf: "service_account_json" },
    { key: "region", label: "Region", type: "text", placeholder: "us-central1" },
    { key: "vertex_ai_location", label: "Vertex AI Location (optional)", type: "text", placeholder: "us-central1" },
    { key: "vertex_ai_model", label: "Vertex AI Model (optional)", type: "select", placeholder: "",
      options: [
        { value: "", label: "— Not using Vertex AI from this project —" },
        { value: "gemini-1.5-pro", label: "Gemini 1.5 Pro" },
        { value: "gemini-1.5-flash", label: "Gemini 1.5 Flash" },
      ],
    },
  ],
};

// ─── Field renderer ───────────────────────────────────────────────
function FieldInput({ field, value, onChange }: {
  field: { key: string; type: string; placeholder?: string; options?: {value:string;label:string}[] };
  value: string;
  onChange: (v: string) => void;
}) {
  const [show, setShow] = useState(false);
  const cls = "w-full bg-[#0b0e16] border border-[#1e2535] focus:border-indigo-500/60 text-slate-200 text-sm rounded-lg px-3 py-2 outline-none transition-colors placeholder:text-slate-600";

  if (field.type === "select") return (
    <select value={value} onChange={e => onChange(e.target.value)} className={cls}>
      {field.options?.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
  if (field.type === "textarea") return (
    <textarea value={value} onChange={e => onChange(e.target.value)} placeholder={field.placeholder}
      rows={4} className={`${cls} font-mono text-xs resize-y`} />
  );
  if (field.type === "password") return (
    <div className="relative">
      <input type={show ? "text" : "password"} value={value} onChange={e => onChange(e.target.value)}
        placeholder={field.placeholder} className={`${cls} pr-9`} />
      <button type="button" onClick={() => setShow(p => !p)}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
        {show ? <EyeOff size={13} /> : <Eye size={13} />}
      </button>
    </div>
  );
  return <input type="text" value={value} onChange={e => onChange(e.target.value)} placeholder={field.placeholder} className={cls} />;
}

// ─── Hosting configurator ─────────────────────────────────────────
function HostingConfig({ cloud, existing, onSave, onRemove, isAdmin, get }: {
  cloud: CloudKey;
  existing: any | null;
  onSave: (cloud: CloudKey, config: Record<string, string>) => Promise<void>;
  onRemove: (id: string) => Promise<void>;
  isAdmin: boolean;
  get: any;
}) {
  const meta = CLOUDS[cloud];
  const fields = HOSTING_FIELDS[cloud];
  const [values, setValues] = useState<Record<string, string>>(() => {
    const d: Record<string, string> = {};
    fields.forEach(f => { d[f.key] = ""; });
    if (existing?.config) Object.entries(existing.config).forEach(([k, v]) => { d[k] = String(v); });
    return d;
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);

  const authMethod = values["auth_method"];
  const visibleFields = fields.filter(f => !f.showIf || f.showIf === authMethod);

  async function save() {
    setSaving(true);
    await onSave(cloud, values);
    setSaving(false);
  }

  async function test() {
    if (!existing) { setTestResult({ healthy: false, error: "Save first" }); return; }
    setTesting(true);
    const r = await get(`/api/v1/connectors/${existing.id}/test`);
    setTestResult(r);
    setTesting(false);
  }

  return (
    <div className="space-y-3">
      <div className={`text-xs px-3 py-2 rounded-lg border flex items-start gap-2 ${meta.bgClass}`}>
        <span className="text-lg flex-shrink-0">{meta.emoji}</span>
        <div>
          <span className="font-medium text-white">OpsBrain is deployed on {meta.label}</span>
          <p className="text-slate-400 mt-0.5">
            Configure the workload identity — no static credentials are stored. OpsBrain inherits this identity from the platform automatically.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {visibleFields.map(f => (
          <div key={f.key} className={f.type === "textarea" ? "col-span-2" : ""}>
            <label className="text-xs font-medium text-slate-300 block mb-1">{f.label}</label>
            <FieldInput field={f} value={values[f.key] ?? ""} onChange={v => setValues(p => ({ ...p, [f.key]: v }))} />
            {f.help && <p className="text-xs text-slate-600 mt-1">{f.help}</p>}
          </div>
        ))}
      </div>

      {testResult && (
        <div className={`flex items-start gap-2 p-2.5 rounded-lg text-xs border ${testResult.healthy ? "bg-green-950/30 border-green-800/40 text-green-300" : "bg-red-950/30 border-red-800/40 text-red-300"}`}>
          {testResult.healthy ? <CheckCircle2 size={12} className="mt-0.5 flex-shrink-0" /> : <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />}
          {testResult.healthy ? `Connected — ${testResult.auth_method || "identity verified"}` : testResult.error}
        </div>
      )}

      {isAdmin && (
        <div className="flex gap-2">
          <button onClick={save} disabled={saving}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-white text-xs rounded-lg transition-colors disabled:opacity-50 ${existing ? "bg-indigo-600 hover:bg-indigo-500" : "bg-green-700 hover:bg-green-600"}`}>
            {saving ? <><Loader2 size={11} className="animate-spin" /> Saving…</> : existing ? "Update Hosting" : "Set as Hosting Cloud"}
          </button>
          {existing && (
            <button onClick={test} disabled={testing}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1e2535] hover:bg-[#2a3548] text-slate-300 text-xs rounded-lg disabled:opacity-50">
              {testing ? <><Loader2 size={11} className="animate-spin" /> Testing…</> : <><RefreshCw size={11} /> Test</>}
            </button>
          )}
          {existing && (
            <button onClick={() => onRemove(existing.id)}
              className="ml-auto flex items-center gap-1 px-2.5 py-1.5 bg-red-950/40 hover:bg-red-950/70 text-red-400 text-xs rounded-lg">
              <Trash2 size={11} /> Remove
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Data source form ─────────────────────────────────────────────
function DataSourceForm({ cloud, onSave, onCancel }: {
  cloud: CloudKey;
  onSave: (cloud: CloudKey, name: string, config: Record<string, string>) => Promise<void>;
  onCancel: () => void;
}) {
  const fields = SOURCE_FIELDS[cloud];
  const [values, setValues] = useState<Record<string, string>>(() => {
    const d: Record<string, string> = {};
    fields.forEach(f => { d[f.key] = f.options?.[0]?.value ?? ""; });
    return d;
  });
  const [saving, setSaving] = useState(false);
  const authMethod = values["auth_method"];
  const visibleFields = fields.filter(f => !f.showIf || f.showIf === authMethod);

  async function save() {
    setSaving(true);
    const config: Record<string, string> = {};
    Object.entries(values).forEach(([k, v]) => { if (v) config[k] = v; });
    await onSave(cloud, values["name"] || `${CLOUDS[cloud].label} Account`, config);
    setSaving(false);
  }

  return (
    <div className="bg-[#0f1117] border border-[#1e2535] rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2 mb-1">
        <span>{CLOUDS[cloud].emoji}</span>
        <span className="text-sm font-medium text-white">Add {CLOUDS[cloud].label} Data Source</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {visibleFields.map(f => (
          <div key={f.key} className={f.type === "textarea" || f.type === "select" && f.options && f.options.length > 3 ? "col-span-2" : ""}>
            <label className="text-xs font-medium text-slate-300 block mb-1">
              {f.label} {f.required && <span className="text-red-400">*</span>}
            </label>
            <FieldInput field={f} value={values[f.key] ?? ""} onChange={v => setValues(p => ({ ...p, [f.key]: v }))} />
            {f.help && <p className="text-xs text-slate-600 mt-1">{f.help}</p>}
          </div>
        ))}
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={save} disabled={saving || !values["name"]}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs rounded-lg disabled:opacity-50">
          {saving ? <><Loader2 size={11} className="animate-spin" /> Saving…</> : "Add Data Source"}
        </button>
        <button onClick={onCancel} className="px-3 py-1.5 bg-[#1e2535] hover:bg-[#2a3548] text-slate-400 text-xs rounded-lg">
          Cancel
        </button>
      </div>
    </div>
  );
}

// ─── Data source row ──────────────────────────────────────────────
function DataSourceRow({ account, onTest, onRemove, isAdmin }: {
  account: CloudAccount;
  onTest: (id: string) => Promise<void>;
  onRemove: (id: string) => Promise<void>;
  isAdmin: boolean;
}) {
  const [testing, setTesting] = useState(false);
  const meta = CLOUDS[account.cloud as CloudKey] ?? { emoji: "☁️", label: account.cloud };

  async function test() {
    setTesting(true);
    await onTest(account.id);
    setTesting(false);
  }

  return (
    <div className="flex items-center gap-3 p-3 bg-[#161b27] border border-[#1e2535] rounded-lg hover:border-[#2a3548] transition-colors group">
      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${account.healthy === true ? "bg-green-400" : account.healthy === false ? "bg-red-400 animate-pulse" : "bg-slate-500"}`} />
      <span className="text-base flex-shrink-0">{meta.emoji}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-200">{account.name}</span>
          <span className="text-xs text-slate-500 font-mono">{account.account_id}</span>
          {account.region && <span className="text-xs text-slate-600">{account.region}</span>}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-xs text-slate-500">{account.auth_method}</span>
          {account.healthy === true && <span className="text-xs text-green-500">Connected ✓</span>}
          {account.healthy === false && <span className="text-xs text-red-400">{account.error || "Connection failed"}</span>}
        </div>
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onClick={test} disabled={testing} className="p-1.5 text-slate-500 hover:text-indigo-400 hover:bg-indigo-600/10 rounded transition-colors" title="Test">
          {testing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
        </button>
        {isAdmin && (
          <button onClick={() => onRemove(account.id)} className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-950/20 rounded transition-colors" title="Remove">
            <Trash2 size={13} />
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Main CloudSection ────────────────────────────────────────────
export function CloudSection({ get, post, del, isAdmin }: {
  get: (p: string) => Promise<any>;
  post: (p: string, b?: any) => Promise<any>;
  del: (p: string) => Promise<any>;
  isAdmin: boolean;
}) {
  const [summary, setSummary] = useState<CloudSummary | null>(null);
  const [health, setHealth] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [selectedHostingCloud, setSelectedHostingCloud] = useState<CloudKey | null>(null);
  const [showHostingForm, setShowHostingForm] = useState(false);
  const [addingSource, setAddingSource] = useState<CloudKey | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const [sum, h] = await Promise.all([
      get("/api/v1/connectors/cloud/summary"),
      get("/api/v1/connectors/health"),
    ]);
    if (sum) setSummary(sum);
    if (h) {
      const map: Record<string, any> = {};
      (Array.isArray(h) ? h : []).forEach((item: any) => { map[item.id] = item; });
      setHealth(map);
    }
    setLoading(false);
    setRefreshing(false);
  }, [get]);

  useEffect(() => { load(); }, [load]);

  // When summary loads, pre-select the hosting cloud if already configured
  useEffect(() => {
    if (summary?.hosting.cloud) {
      setSelectedHostingCloud(summary.hosting.cloud as CloudKey);
    }
  }, [summary]);

  function refresh() { setRefreshing(true); load(); }

  function getHostingConnector() {
    if (!summary?.hosting.id) return null;
    return { ...summary.hosting, config: {} };
  }

  async function saveHosting(cloud: CloudKey, config: Record<string, string>) {
    // Remove existing hosting connector first
    if (summary?.hosting.id) {
      await del(`/api/v1/connectors/${summary.hosting.id}`);
    }
    await post("/api/v1/connectors", {
      name: `${CLOUDS[cloud].label} — Hosting`,
      type: cloud,
      config,
      connection_type: "hosting",
    });
    await load();
    setShowHostingForm(false);
  }

  async function saveDataSource(cloud: CloudKey, name: string, config: Record<string, string>) {
    await post("/api/v1/connectors", {
      name,
      type: cloud,
      config,
      connection_type: "data_source",
    });
    await load();
    setAddingSource(null);
  }

  async function removeConnector(id: string) {
    await del(`/api/v1/connectors/${id}`);
    await load();
  }

  async function testConnector(id: string) {
    await post(`/api/v1/connectors/${id}/test`);
    await load();
  }

  const dataSources: CloudAccount[] = (summary?.data_sources ?? []).map(ds => ({
    ...ds,
    healthy: health[ds.id]?.healthy,
    error: health[ds.id]?.error,
  }));

  const hostingCloud = summary?.hosting.cloud as CloudKey | null;

  return (
    <div className="space-y-6">
      {/* ── Section header ─────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-white flex items-center gap-2">
            ☁️ Cloud Providers
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Where OpsBrain runs · What environments it monitors
          </p>
        </div>
        <button onClick={refresh} disabled={refreshing}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-white transition-colors">
          <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* ── Architecture explainer ─────────────────────────────── */}
      <div className="bg-[#0f1117] border border-indigo-800/30 rounded-xl p-4 text-xs text-slate-400 space-y-2">
        <div className="flex items-start gap-3">
          <span className="text-xl">🏠</span>
          <div>
            <span className="text-white font-medium">Hosting Cloud</span> — where OpsBrain itself runs.
            Only configure this if OpsBrain is deployed <span className="text-indigo-300">inside</span> a cloud platform (EKS → IRSA, EC2 → Instance Profile, ECS → Task Role).{" "}
            <span className="text-slate-500">Running locally or in Docker? Leave this blank — add accounts under Data Sources instead.</span>
          </div>
        </div>
        <div className="flex items-start gap-3">
          <span className="text-xl">📡</span>
          <div>
            <span className="text-white font-medium">Data Sources</span> — cloud accounts OpsBrain monitors (access keys go here).
            Supports <span className="text-indigo-300">any cloud, any number of accounts</span>, regardless of where OpsBrain is hosted.
          </div>
        </div>
      </div>

      {/* ── Hosting Cloud ──────────────────────────────────────── */}
      <div className="bg-[#161b27] border border-[#1e2535] rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Server size={14} className="text-indigo-400" /> OpsBrain Deployment Cloud
            {hostingCloud && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-green-950/50 text-green-300 border border-green-800/40">
                <CheckCircle2 size={10} /> {CLOUDS[hostingCloud].emoji} {CLOUDS[hostingCloud].label}
              </span>
            )}
          </h3>
          {isAdmin && (
            <button onClick={() => setShowHostingForm(p => !p)}
              className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
              {showHostingForm ? "Cancel" : hostingCloud ? "Change" : "Configure"}
            </button>
          )}
        </div>

        {!showHostingForm && !hostingCloud && (
          <div className="text-xs text-slate-500 italic py-2">
            Not configured — OpsBrain is running locally or in Docker. This is fine. Add your AWS/Azure/GCP accounts under <span className="text-slate-400">Data Sources</span> below to start monitoring them.
          </div>
        )}

        {!showHostingForm && hostingCloud && (
          <div className="flex items-center gap-3 text-sm">
            <span className="text-2xl">{CLOUDS[hostingCloud].emoji}</span>
            <div>
              <span className="text-white font-medium">{CLOUDS[hostingCloud].label}</span>
              <div className="text-xs text-slate-500 mt-0.5">
                Identity: <span className="text-slate-300">{summary?.hosting.auth_method || "—"}</span>
                {summary?.hosting.region && <> · Region: <span className="text-slate-300">{summary.hosting.region}</span></>}
              </div>
            </div>
          </div>
        )}

        {showHostingForm && (
          <>
            {/* Cloud picker */}
            <div className="flex gap-2 mb-4">
              {(Object.entries(CLOUDS) as [CloudKey, typeof CLOUDS[CloudKey]][]).map(([key, meta]) => (
                <button key={key} onClick={() => setSelectedHostingCloud(key)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors ${
                    selectedHostingCloud === key
                      ? "bg-indigo-600/20 border-indigo-600/40 text-indigo-300"
                      : "border-[#1e2535] text-slate-400 hover:text-white hover:border-[#2a3548]"
                  }`}>
                  {meta.emoji} {meta.label}
                </button>
              ))}
            </div>
            {selectedHostingCloud && (
              <HostingConfig
                cloud={selectedHostingCloud}
                existing={summary?.hosting.id ? { id: summary.hosting.id, config: {} } : null}
                onSave={saveHosting}
                onRemove={removeConnector}
                isAdmin={isAdmin}
                get={get}
              />
            )}
          </>
        )}
      </div>

      {/* ── Data Sources ───────────────────────────────────────── */}
      <div className="bg-[#161b27] border border-[#1e2535] rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Radio size={14} className="text-indigo-400" /> Monitored Cloud Environments
            <span className="text-xs text-slate-500 font-normal">({dataSources.length} connected)</span>
          </h3>
          {isAdmin && !addingSource && (
            <div className="flex gap-1.5">
              {(Object.entries(CLOUDS) as [CloudKey, any][]).map(([key, meta]) => (
                <button key={key} onClick={() => setAddingSource(key)}
                  className="flex items-center gap-1 px-2 py-1 text-xs border border-[#1e2535] hover:border-indigo-600/40 text-slate-400 hover:text-indigo-300 rounded-lg transition-colors">
                  <Plus size={11} /> {meta.emoji} {meta.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {dataSources.length === 0 && !addingSource && (
          <div className="text-xs text-slate-500 italic py-2">
            No data sources configured. Add AWS accounts, Azure subscriptions, or GCP projects to monitor.
          </div>
        )}

        {dataSources.length > 0 && (
          <div className="space-y-2 mb-3">
            {dataSources.map(ds => (
              <DataSourceRow
                key={ds.id}
                account={ds}
                onTest={testConnector}
                onRemove={removeConnector}
                isAdmin={isAdmin}
              />
            ))}
          </div>
        )}

        {addingSource && (
          <DataSourceForm
            cloud={addingSource}
            onSave={saveDataSource}
            onCancel={() => setAddingSource(null)}
          />
        )}
      </div>
    </div>
  );
}

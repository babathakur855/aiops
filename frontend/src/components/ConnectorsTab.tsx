"use client";

import { useState, useCallback, useEffect } from "react";
import {
  CheckCircle2, XCircle, Loader2, ChevronDown, ChevronUp,
  Trash2, Eye, EyeOff, RefreshCw, Plug, AlertTriangle,
  ExternalLink, Plus,
} from "lucide-react";
import { CloudSection } from "./CloudSection";

// ─── Field definition per connector ──────────────────────────────
interface Field {
  key: string;
  label: string;
  type: "text" | "password" | "url" | "number" | "select" | "toggle" | "textarea";
  placeholder?: string;
  help?: string;
  required?: boolean;
  options?: { value: string; label: string }[];
  default?: string | number | boolean;
  showIf?: { key: string; value: string };  // show when field[key] === value
}

interface ConnectorDef {
  type: string;
  label: string;
  emoji: string;
  color: string;
  description: string;
  docsUrl?: string;
  fields: Field[];
}

// ─── Connector definitions with full field specs ──────────────────
const CONNECTORS: ConnectorDef[] = [
  {
    type: "servicenow",
    label: "ServiceNow",
    emoji: "🎫",
    color: "emerald",
    description: "Fetch & update incidents, write RCA as work notes, auto-resolve tickets",
    docsUrl: "https://docs.servicenow.com/bundle/washingtondc-application-development/page/integrate/inbound-rest/concept/c_RESTAPI.html",
    fields: [
      { key: "instance_url", label: "Instance URL", type: "url", placeholder: "https://yourcompany.service-now.com", required: true, help: "Your ServiceNow instance base URL" },
      { key: "username", label: "Username", type: "text", placeholder: "admin", required: true },
      { key: "password", label: "Password", type: "password", required: true },
      { key: "client_id", label: "OAuth Client ID", type: "text", placeholder: "Leave blank to use Basic Auth", required: false, help: "Optional — for OAuth 2.0 authentication" },
      { key: "client_secret", label: "OAuth Client Secret", type: "password", required: false, help: "Required only when OAuth Client ID is set above" },
    ],
  },
  {
    type: "confluence",
    label: "Confluence",
    emoji: "📚",
    color: "blue",
    description: "Search SOPs & runbooks, publish post-mortems as Confluence pages",
    docsUrl: "https://developer.atlassian.com/cloud/confluence/rest/v1/intro/",
    fields: [
      { key: "base_url", label: "Confluence Base URL", type: "url", placeholder: "https://yourcompany.atlassian.net", required: true, help: "Cloud: atlassian.net  |  Server: your-domain.com/confluence" },
      { key: "username", label: "Email / Username", type: "text", placeholder: "user@yourcompany.com", required: true },
      { key: "api_token", label: "API Token", type: "password", required: true, help: "Cloud: create at id.atlassian.com/manage-profile/security/api-tokens  |  Server: use your password" },
      { key: "default_space_key", label: "Default Space Key", type: "text", placeholder: "OPS", required: false, help: "Optional — default space for publishing post-mortems" },
    ],
  },
  {
    type: "dynatrace",
    label: "Dynatrace",
    emoji: "📊",
    color: "purple",
    description: "Fetch problems, query logs, get metrics and service topology",
    docsUrl: "https://docs.dynatrace.com/docs/dynatrace-api",
    fields: [
      { key: "base_url", label: "Environment URL", type: "url", placeholder: "https://xxx.live.dynatrace.com", required: true, help: "Your Dynatrace environment URL (SaaS or Managed)" },
      { key: "api_token", label: "API Token", type: "password", required: true, help: "Create at: Settings → Integration → Dynatrace API  |  Required scopes: problems.read, logs.read, metrics.read" },
    ],
  },
  {
    type: "elasticsearch",
    label: "Elasticsearch / OpenSearch",
    emoji: "🔍",
    color: "amber",
    description: "Full-text log search, error rate aggregation, alert queries across ELK stack",
    fields: [
      { key: "url", label: "Cluster URL", type: "url", placeholder: "https://your-es-host:9200", required: true },
      { key: "auth_method", label: "Auth Method", type: "select", required: true, default: "api_key", options: [{ value: "api_key", label: "API Key" }, { value: "basic", label: "Basic Auth (Username + Password)" }, { value: "none", label: "No Auth" }] },
      { key: "api_key", label: "API Key", type: "password", placeholder: "base64-encoded API key", required: false, showIf: { key: "auth_method", value: "api_key" } },
      { key: "username", label: "Username", type: "text", placeholder: "elastic", required: false, showIf: { key: "auth_method", value: "basic" } },
      { key: "password", label: "Password", type: "password", required: false, showIf: { key: "auth_method", value: "basic" } },
      { key: "index_pattern", label: "Log Index Pattern", type: "text", placeholder: "logs-*", required: false, help: "Default: logs-*  |  Examples: filebeat-*, app-logs-*" },
    ],
  },
  {
    type: "slack",
    label: "Slack",
    emoji: "💬",
    color: "green",
    description: "Send incident alerts, post-mortem summaries, and AI analysis to Slack channels",
    docsUrl: "https://api.slack.com/messaging/webhooks",
    fields: [
      { key: "webhook_url", label: "Incoming Webhook URL", type: "url", placeholder: "https://hooks.slack.com/services/T.../B.../...", required: false, help: "Create at: api.slack.com → Your Apps → Incoming Webhooks" },
      { key: "bot_token", label: "Bot Token", type: "password", placeholder: "xoxb-...", required: false, help: "Optional — needed to post to specific channels via Bot API" },
      { key: "default_channel", label: "Default Channel", type: "text", placeholder: "#incidents", required: false },
    ],
  },
  {
    type: "teams",
    label: "Microsoft Teams",
    emoji: "💼",
    color: "indigo",
    description: "Send adaptive card notifications and incident alerts to Teams channels",
    docsUrl: "https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook",
    fields: [
      { key: "webhook_url", label: "Incoming Webhook URL", type: "url", placeholder: "https://yourorg.webhook.office.com/webhookb2/...", required: true, help: "In Teams: Channel → ... → Connectors → Incoming Webhook → Configure" },
    ],
  },
  {
    type: "email",
    label: "Email (SMTP)",
    emoji: "📧",
    color: "rose",
    description: "Send post-mortems, scheduled digests, and incident reports by email",
    fields: [
      { key: "host", label: "SMTP Host", type: "text", placeholder: "smtp.office365.com", required: true, help: "Gmail: smtp.gmail.com  |  Office 365: smtp.office365.com  |  Exchange: your-exchange-server" },
      { key: "port", label: "Port", type: "number", placeholder: "587", required: true, default: "587", help: "587 = STARTTLS (recommended)  |  465 = SSL  |  25 = No TLS" },
      { key: "username", label: "Username / Email", type: "text", placeholder: "opsbrain@yourcompany.com", required: true },
      { key: "password", label: "Password / App Password", type: "password", required: true, help: "Gmail: use App Password (not account password)  |  Office 365: use account password or app password" },
      { key: "from_email", label: "From Email", type: "text", placeholder: "opsbrain@yourcompany.com", required: true },
    ],
  },

  // AWS / Azure / GCP are handled by CloudSection — see components/CloudSection.tsx
];

// ─── Colour map ───────────────────────────────────────────────────
const COLORS: Record<string, { border: string; badge: string; btn: string; dot: string }> = {
  emerald: { border: "border-emerald-800/40", badge: "bg-emerald-950/40 text-emerald-300", btn: "bg-emerald-700 hover:bg-emerald-600", dot: "bg-emerald-400" },
  blue:    { border: "border-blue-800/40",    badge: "bg-blue-950/40 text-blue-300",    btn: "bg-blue-700 hover:bg-blue-600",    dot: "bg-blue-400" },
  purple:  { border: "border-purple-800/40",  badge: "bg-purple-950/40 text-purple-300",btn: "bg-purple-700 hover:bg-purple-600",dot: "bg-purple-400" },
  amber:   { border: "border-amber-800/40",   badge: "bg-amber-950/40 text-amber-300",  btn: "bg-amber-700 hover:bg-amber-600",  dot: "bg-amber-400" },
  green:   { border: "border-green-800/40",   badge: "bg-green-950/40 text-green-300",  btn: "bg-green-700 hover:bg-green-600",  dot: "bg-green-400" },
  indigo:  { border: "border-indigo-800/40",  badge: "bg-indigo-950/40 text-indigo-300",btn: "bg-indigo-700 hover:bg-indigo-600",dot: "bg-indigo-400" },
  rose:    { border: "border-rose-800/40",    badge: "bg-rose-950/40 text-rose-300",    btn: "bg-rose-700 hover:bg-rose-600",    dot: "bg-rose-400" },
  orange:  { border: "border-orange-800/40",  badge: "bg-orange-950/40 text-orange-300",btn: "bg-orange-700 hover:bg-orange-600",dot: "bg-orange-400" },
  sky:     { border: "border-sky-800/40",     badge: "bg-sky-950/40 text-sky-300",     btn: "bg-sky-700 hover:bg-sky-600",     dot: "bg-sky-400" },
  teal:    { border: "border-teal-800/40",    badge: "bg-teal-950/40 text-teal-300",   btn: "bg-teal-700 hover:bg-teal-600",   dot: "bg-teal-400" },
};

// ─── Single field renderer ────────────────────────────────────────
function FormField({ field, value, onChange }: { field: Field; value: string; onChange: (v: string) => void }) {
  const [show, setShow] = useState(false);
  const inputClass = "w-full bg-[#0b0e16] border border-[#1e2535] focus:border-indigo-500/60 text-slate-200 text-sm rounded-lg px-3 py-2 outline-none transition-colors placeholder:text-slate-600";

  if (field.type === "select") {
    return (
      <select value={value || String(field.default ?? "")} onChange={e => onChange(e.target.value)} className={inputClass}>
        {field.options?.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    );
  }

  if (field.type === "toggle") {
    return (
      <label className="flex items-center gap-2 cursor-pointer">
        <div className={`w-10 h-5 rounded-full transition-colors ${value === "true" ? "bg-indigo-600" : "bg-[#1e2535]"}`}
          onClick={() => onChange(value === "true" ? "false" : "true")}>
          <div className={`w-4 h-4 bg-white rounded-full mt-0.5 transition-transform ${value === "true" ? "translate-x-5" : "translate-x-0.5"}`} />
        </div>
        <span className="text-xs text-slate-400">Enabled</span>
      </label>
    );
  }

  if (field.type === "password") {
    return (
      <div className="relative">
        <input type={show ? "text" : "password"} value={value} onChange={e => onChange(e.target.value)}
          placeholder={field.placeholder} className={`${inputClass} pr-9`} />
        <button type="button" onClick={() => setShow(p => !p)}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors">
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>
    );
  }

  if (field.type === "textarea") {
    return (
      <textarea value={value} onChange={e => onChange(e.target.value)}
        placeholder={field.placeholder} rows={5}
        className={`${inputClass} font-mono text-xs resize-y`} />
    );
  }

  return (
    <input type={field.type === "url" ? "text" : field.type} value={value}
      onChange={e => onChange(e.target.value)} placeholder={field.placeholder}
      className={inputClass} />
  );
}

// ─── Individual connector card with full form ─────────────────────
function ConnectorCard({
  def, existing, isAdmin, onSave, onDelete, onTest,
}: {
  def: ConnectorDef;
  existing: any | null;
  isAdmin: boolean;
  onSave: (type: string, name: string, config: Record<string, string>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onTest: (id: string) => Promise<{ healthy: boolean; message?: string; error?: string }>;
}) {
  const c = COLORS[def.color] ?? COLORS.indigo;
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(() => {
    const defaults: Record<string, string> = {};
    def.fields.forEach(f => { defaults[f.key] = String(f.default ?? ""); });
    if (existing?.config) {
      Object.entries(existing.config).forEach(([k, v]) => { defaults[k] = String(v); });
    }
    return defaults;
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ healthy: boolean; message?: string; error?: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  function set(key: string, val: string) {
    setValues(p => ({ ...p, [key]: val }));
    setTestResult(null);
  }

  async function save() {
    setSaving(true);
    const config: Record<string, string> = {};
    def.fields.forEach(f => { if (values[f.key]) config[f.key] = values[f.key]; });
    await onSave(def.type, `${def.label} Connector`, config);
    setSaving(false);
    setOpen(false);
  }

  async function test() {
    if (!existing) { setTestResult({ healthy: false, error: "Save connector first before testing" }); return; }
    setTesting(true);
    const r = await onTest(existing.id);
    setTestResult(r);
    setTesting(false);
  }

  async function remove() {
    if (!existing) return;
    setDeleting(true);
    await onDelete(existing.id);
    setDeleting(false);
  }

  const isConnected = existing?.healthy === true;
  const hasError = existing?.healthy === false;
  const visibleFields = def.fields.filter(f => {
    if (!f.showIf) return true;
    // showIf: { key, value } means "show this field when values[key] === value"
    return values[f.showIf.key] === f.showIf.value;
  });

  return (
    <div className={`bg-[#161b27] border rounded-xl overflow-hidden transition-all ${open ? c.border : "border-[#1e2535] hover:border-[#2a3548]"}`}>
      {/* Header */}
      <div className="flex items-center gap-3 p-4 cursor-pointer" onClick={() => setOpen(p => !p)}>
        <div className="text-2xl w-10 h-10 bg-[#0f1117] rounded-lg flex items-center justify-center flex-shrink-0">
          {def.emoji}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-white">{def.label}</span>
            {existing ? (
              <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${isConnected ? "bg-green-950/60 text-green-300" : hasError ? "bg-red-950/60 text-red-300" : c.badge}`}>
                {isConnected ? <><CheckCircle2 size={10} /> Connected</> : hasError ? <><XCircle size={10} /> Error</> : <><div className={`w-1.5 h-1.5 rounded-full ${c.dot}`} /> Configured</>}
              </span>
            ) : (
              <span className="text-xs text-slate-600 bg-[#0f1117] px-2 py-0.5 rounded-full border border-[#1e2535]">
                Not configured
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 truncate">{def.description}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {def.docsUrl && (
            <a href={def.docsUrl} target="_blank" rel="noreferrer"
              onClick={e => e.stopPropagation()}
              className="p-1.5 text-slate-600 hover:text-slate-400 transition-colors" title="Documentation">
              <ExternalLink size={13} />
            </a>
          )}
          {open ? <ChevronUp size={16} className="text-slate-500" /> : <ChevronDown size={16} className="text-slate-500" />}
        </div>
      </div>

      {/* Expanded form */}
      {open && (
        <div className="border-t border-[#1e2535] p-4 space-y-4">
          {/* Fields */}
          <div className="space-y-3">
            {visibleFields.map(field => (
              <div key={field.key}>
                <div className="flex items-center gap-1 mb-1">
                  <label className="text-xs font-medium text-slate-300">{field.label}</label>
                  {field.required && <span className="text-red-400 text-xs">*</span>}
                </div>
                <FormField field={field} value={values[field.key] ?? ""} onChange={v => set(field.key, v)} />
                {field.help && <p className="text-xs text-slate-600 mt-1">{field.help}</p>}
              </div>
            ))}
          </div>

          {/* Test result */}
          {testResult && (
            <div className={`flex items-start gap-2 p-3 rounded-lg text-xs border ${
              testResult.healthy
                ? "bg-green-950/30 border-green-800/40 text-green-300"
                : "bg-red-950/30 border-red-800/40 text-red-300"
            }`}>
              {testResult.healthy ? <CheckCircle2 size={13} className="mt-0.5 flex-shrink-0" /> : <AlertTriangle size={13} className="mt-0.5 flex-shrink-0" />}
              <span>{testResult.healthy ? "Connection successful!" : testResult.error ?? "Connection failed"}</span>
            </div>
          )}

          {/* Actions */}
          {isAdmin && (
            <div className="flex items-center gap-2 pt-1">
              <button onClick={save} disabled={saving}
                className={`flex items-center gap-1.5 px-4 py-2 text-white text-xs rounded-lg transition-colors ${c.btn} disabled:opacity-50`}>
                {saving ? <><Loader2 size={12} className="animate-spin" /> Saving…</> : <><Plus size={12} /> {existing ? "Update" : "Connect"}</>}
              </button>

              <button onClick={test} disabled={testing}
                className="flex items-center gap-1.5 px-3 py-2 bg-[#1e2535] hover:bg-[#2a3548] text-slate-300 text-xs rounded-lg transition-colors disabled:opacity-50">
                {testing ? <><Loader2 size={12} className="animate-spin" /> Testing…</> : <><RefreshCw size={12} /> Test Connection</>}
              </button>

              {existing && (
                <button onClick={remove} disabled={deleting}
                  className="flex items-center gap-1.5 px-3 py-2 bg-red-950/40 hover:bg-red-950/70 text-red-400 text-xs rounded-lg transition-colors disabled:opacity-50 ml-auto">
                  {deleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                  Remove
                </button>
              )}
            </div>
          )}

          {!isAdmin && (
            <p className="text-xs text-slate-600 italic">Admin role required to configure connectors</p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main ConnectorsTab component ─────────────────────────────────
export function ConnectorsTab({
  get, post, del, isAdmin,
}: {
  get: (p: string) => Promise<any>;
  post: (p: string, b?: any) => Promise<any>;
  del: (p: string) => Promise<any>;
  isAdmin: boolean;
}) {
  const [configured, setConfigured] = useState<any[]>([]);
  const [health, setHealth] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const [list, h] = await Promise.all([
      get("/api/v1/connectors"),
      get("/api/v1/connectors/health"),
    ]);
    if (list) setConfigured(Array.isArray(list) ? list : []);
    if (h) {
      const map: Record<string, any> = {};
      (Array.isArray(h) ? h : []).forEach((item: any) => { map[item.id] = item; });
      setHealth(map);
    }
    setLoading(false);
    setRefreshing(false);
  }, [get]);

  useEffect(() => { load(); }, [load]);

  function refresh() { setRefreshing(true); load(); }

  // Find existing connector by type
  function getExisting(type: string) {
    const found = configured.find(c => c.type === type);
    if (!found) return null;
    const h = health[found.id];
    return { ...found, healthy: h?.healthy, error: h?.error };
  }

  async function handleSave(type: string, name: string, config: Record<string, string>) {
    const existing = configured.find(c => c.type === type);
    if (existing) {
      // Remove old, add new (update)
      await del(`/api/v1/connectors/${existing.id}`);
    }
    await post("/api/v1/connectors", { name, type, config, enabled: true });
    await load();
  }

  async function handleDelete(id: string) {
    await del(`/api/v1/connectors/${id}`);
    await load();
  }

  async function handleTest(id: string) {
    const r = await post(`/api/v1/connectors/${id}/test`);
    await load();
    return r ?? { healthy: false, error: "No response from backend" };
  }

  const connectedCount = Object.values(health).filter((h: any) => h?.healthy).length;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <Plug size={18} className="text-indigo-400" /> Connectors
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Cloud providers · Tooling integrations — {connectedCount} healthy
          </p>
        </div>
        <button onClick={refresh} disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-2 bg-[#161b27] hover:bg-[#1e2535] border border-[#1e2535] text-slate-400 hover:text-white text-xs rounded-lg transition-colors">
          <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* ── Cloud section (hosting + data sources) ── */}
      <CloudSection get={get} post={post} del={del} isAdmin={isAdmin} />

      {/* ── Tooling connectors divider ── */}
      <div className="flex items-center gap-3">
        <div className="h-px flex-1 bg-[#1e2535]" />
        <span className="text-xs text-slate-500 uppercase tracking-wider">Tooling Integrations</span>
        <div className="h-px flex-1 bg-[#1e2535]" />
      </div>

      {/* Tooling connector cards (SNOW, Confluence, Dynatrace, etc.) */}
      {loading ? (
        <div className="flex items-center justify-center py-8 text-slate-500">
          <Loader2 size={18} className="animate-spin mr-2" /> Loading…
        </div>
      ) : (
        <div className="space-y-3">
          {CONNECTORS.map(def => (
            <ConnectorCard
              key={def.type}
              def={def}
              existing={getExisting(def.type)}
              isAdmin={isAdmin}
              onSave={handleSave}
              onDelete={handleDelete}
              onTest={handleTest}
            />
          ))}
        </div>
      )}

      {!isAdmin && (
        <p className="text-xs text-slate-600 text-center border border-[#1e2535] rounded-xl p-3">
          Read-only access. Admin role required to configure connectors.
        </p>
      )}

      {/* IAM Policy Reference */}
      {isAdmin && <IAMPolicyPanel get={get} configured={configured} />}
    </div>
  );
}

// ─── IAM Policy Reference Panel ───────────────────────────────────
function IAMPolicyPanel({ get, configured }: { get: any; configured: any[] }) {
  const [selected, setSelected] = useState<"aws" | "azure" | "gcp" | null>(null);
  const [policy, setPolicy] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const CLOUD_MAP = {
    aws:   { label: "AWS IAM Policy", emoji: "☁️", endpoint: "/api/v1/connectors/aws/iam-policy" },
    azure: { label: "Azure Custom Role", emoji: "🔷", endpoint: "/api/v1/connectors/azure/required-role" },
    gcp:   { label: "GCP IAM Roles + Setup", emoji: "🌐", endpoint: "/api/v1/connectors/gcp/required-roles" },
  };

  async function loadPolicy(cloud: "aws" | "azure" | "gcp") {
    if (selected === cloud) { setSelected(null); setPolicy(null); return; }
    setSelected(cloud);
    setLoading(true);
    const r = await get(CLOUD_MAP[cloud].endpoint);
    setPolicy(r);
    setLoading(false);
  }

  function copyPolicy() {
    if (!policy) return;
    navigator.clipboard.writeText(JSON.stringify(policy, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="bg-[#161b27] border border-[#1e2535] rounded-xl p-4">
      <h2 className="text-sm font-semibold text-white mb-1 flex items-center gap-2">
        🔐 Required IAM Permissions
      </h2>
      <p className="text-xs text-slate-500 mb-3">
        Exact policies to grant OpsBrain in each cloud — principle of least privilege
      </p>
      <div className="flex gap-2 mb-3">
        {(Object.entries(CLOUD_MAP) as [keyof typeof CLOUD_MAP, typeof CLOUD_MAP[keyof typeof CLOUD_MAP]][]).map(([cloud, info]) => (
          <button key={cloud} onClick={() => loadPolicy(cloud)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-colors ${
              selected === cloud
                ? "bg-indigo-600/20 border-indigo-600/40 text-indigo-300"
                : "border-[#1e2535] text-slate-400 hover:text-white hover:border-[#2a3548]"
            }`}>
            {info.emoji} {info.label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-slate-500 text-xs py-3">
          <Loader2 size={13} className="animate-spin" /> Loading policy…
        </div>
      )}

      {policy && !loading && (
        <div className="relative">
          <button onClick={copyPolicy}
            className="absolute top-2 right-2 px-2 py-1 text-xs bg-[#1e2535] hover:bg-[#2a3548] text-slate-400 rounded">
            {copied ? "Copied ✓" : "Copy"}
          </button>
          <pre className="bg-[#0b0e16] border border-[#1e2535] rounded-lg p-3 text-xs text-slate-300 font-mono overflow-x-auto max-h-72 overflow-y-auto">
            {JSON.stringify(policy, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

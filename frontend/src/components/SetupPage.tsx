"use client";

import { useState, useEffect } from "react";
import { Brain, CheckCircle2, XCircle, RefreshCw, Copy, Terminal, Loader2 } from "lucide-react";

interface SetupStatus {
  setup_required: boolean;
  llm: { ok: boolean; provider: string; model?: string; error?: string };
  requirements: { configured: boolean; provider: string; issues: string[] };
}

const PROVIDER_SETUP: Record<string, { label: string; emoji: string; color: string; steps: string[]; envVars: string[] }> = {
  anthropic: {
    label: "Anthropic (Claude)", emoji: "🤖", color: "indigo",
    steps: [
      "Get your API key at: console.anthropic.com/settings/keys",
      "Copy the key (starts with sk-ant-...)",
      "Add to .env file or run the setup wizard",
    ],
    envVars: ["ANTHROPIC_API_KEY=sk-ant-api03-...", "ANTHROPIC_MODEL=claude-sonnet-4-6", "LLM_PROVIDER=anthropic"],
  },
  aws_bedrock: {
    label: "AWS Bedrock", emoji: "☁️", color: "orange",
    steps: [
      "Enable Claude model access in AWS Bedrock Console: us-east-1 → Model access → Request access",
      "Ensure your IAM role/user has: bedrock:InvokeModel permission",
      "Add AWS credentials to .env or use Instance Profile / IRSA (no credentials needed)",
    ],
    envVars: ["LLM_PROVIDER=aws_bedrock", "AWS_BEDROCK_REGION=us-east-1", "AWS_BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0"],
  },
  azure_openai: {
    label: "Azure OpenAI", emoji: "🔷", color: "sky",
    steps: [
      "Create an Azure OpenAI resource in Azure Portal",
      "Deploy a model (e.g. gpt-4o) in Azure OpenAI Studio → Deployments",
      "Copy the endpoint (https://your-resource.openai.azure.com/) and API key",
      "Add to .env file or use Managed Identity (no API key needed on AKS)",
    ],
    envVars: ["LLM_PROVIDER=azure_openai", "AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/", "AZURE_OPENAI_DEPLOYMENT=gpt-4o", "AZURE_OPENAI_API_KEY=your-key-here"],
  },
  gcp_vertex: {
    label: "GCP Vertex AI", emoji: "🌐", color: "teal",
    steps: [
      "Enable Vertex AI API: console.cloud.google.com/vertex-ai → Enable",
      "Create a Service Account with roles/aiplatform.user",
      "Download the JSON key file or use Workload Identity (GKE — no key needed)",
    ],
    envVars: ["LLM_PROVIDER=gcp_vertex", "GCP_PROJECT_ID=your-project-id", "GCP_VERTEX_AI_LOCATION=us-central1", "GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json"],
  },
  ollama: {
    label: "Ollama (self-hosted)", emoji: "🖥️", color: "green",
    steps: [
      "Install Ollama: curl -fsSL https://ollama.ai/install.sh | sh",
      "Pull a model: ollama pull llama3.1:70b",
      "Ensure Ollama is accessible from the OpsBrain container",
    ],
    envVars: ["LLM_PROVIDER=ollama", "OLLAMA_BASE_URL=http://ollama:11434", "OLLAMA_MODEL=llama3.1:70b"],
  },
};

const COLOR_MAP: Record<string, string> = {
  indigo: "border-indigo-700/50 bg-indigo-950/30",
  orange: "border-orange-700/50 bg-orange-950/30",
  sky:    "border-sky-700/50 bg-sky-950/30",
  teal:   "border-teal-700/50 bg-teal-950/30",
  green:  "border-green-700/50 bg-green-950/30",
};

function CodeBlock({ lines }: { lines: string[] }) {
  const [copied, setCopied] = useState(false);
  const text = lines.join("\n");

  function copy() {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="relative bg-[#0b0e16] border border-[#1e2535] rounded-lg p-3 font-mono text-xs text-slate-300">
      <button onClick={copy}
        className="absolute top-2 right-2 px-2 py-0.5 text-xs text-slate-500 hover:text-white bg-[#161b27] rounded transition-colors">
        {copied ? "Copied ✓" : <Copy size={11} />}
      </button>
      {lines.map((l, i) => <div key={i} className="text-slate-300">{l}</div>)}
    </div>
  );
}

export function SetupPage({ apiUrl, onDone }: { apiUrl: string; onDone: () => void }) {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<string>("anthropic");

  async function check() {
    setChecking(true);
    try {
      const r = await fetch(`${apiUrl}/setup/status`);
      const data: SetupStatus = await r.json();
      setStatus(data);
      if (data.llm?.provider) setSelectedProvider(data.llm.provider);
      if (!data.setup_required) {
        setTimeout(onDone, 1000);
      }
    } catch {
      setStatus({ setup_required: true, llm: { ok: false, provider: "unknown", error: "Cannot reach OpsBrain backend" }, requirements: { configured: false, provider: "unknown", issues: ["Backend not reachable"] } });
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => { check(); }, []);

  const provider = PROVIDER_SETUP[selectedProvider] ?? PROVIDER_SETUP.anthropic;
  const colorClass = COLOR_MAP[provider.color] ?? COLOR_MAP.indigo;

  return (
    <div className="min-h-screen bg-[#0f1117] flex items-center justify-center p-4">
      <div className="w-full max-w-2xl space-y-5">

        {/* Header */}
        <div className="text-center">
          <div className="flex items-center justify-center gap-2 mb-2">
            <Brain size={28} className="text-indigo-400" />
            <span className="text-2xl font-bold text-white">OpsBrain</span>
          </div>
          <h1 className="text-lg font-semibold text-white mt-4">Setup Required</h1>
          <p className="text-sm text-slate-500 mt-1">
            An LLM provider must be configured before OpsBrain can start.
            Run the setup wizard on your server first.
          </p>
        </div>

        {/* LLM status */}
        <div className={`border rounded-xl p-4 ${status?.llm?.ok ? "border-green-700/50 bg-green-950/20" : "border-red-700/50 bg-red-950/20"}`}>
          <div className="flex items-center gap-2">
            {checking ? (
              <Loader2 size={16} className="text-slate-400 animate-spin" />
            ) : status?.llm?.ok ? (
              <CheckCircle2 size={16} className="text-green-400" />
            ) : (
              <XCircle size={16} className="text-red-400" />
            )}
            <span className="text-sm font-medium text-white">
              {checking ? "Checking LLM connection…"
                : status?.llm?.ok ? `LLM connected — ${status.llm.provider} / ${status.llm.model}`
                : `LLM not configured — ${status?.llm?.error ?? "unknown error"}`}
            </span>
          </div>
          {status?.requirements?.issues?.length ? (
            <ul className="mt-2 space-y-1">
              {status.requirements.issues.map((issue, i) => (
                <li key={i} className="text-xs text-red-400 flex items-center gap-1.5">
                  <span className="text-red-600">•</span> {issue}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        {/* Quick start — run setup wizard */}
        <div className="bg-[#161b27] border border-[#1e2535] rounded-xl p-4">
          <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Terminal size={14} className="text-indigo-400" /> Quickest way — run the setup wizard
          </h2>
          <p className="text-xs text-slate-500 mb-3">
            Run this on the machine where OpsBrain is installed. It guides through LLM selection, tests connectivity, and writes the .env file.
          </p>
          <div className="space-y-2">
            <div>
              <div className="text-xs text-slate-500 mb-1">Linux / macOS:</div>
              <CodeBlock lines={["./setup.sh"]} />
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-1">Windows:</div>
              <CodeBlock lines={[".\\setup.ps1"]} />
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-1">or directly:</div>
              <CodeBlock lines={["python setup.py"]} />
            </div>
          </div>
          <p className="text-xs text-slate-600 mt-3">
            After running the wizard, restart the OpsBrain backend then click "Check Again" below.
          </p>
        </div>

        {/* Provider-specific manual instructions */}
        <div className="bg-[#161b27] border border-[#1e2535] rounded-xl p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Or configure manually — pick your LLM provider</h2>
          <div className="flex flex-wrap gap-2 mb-4">
            {Object.entries(PROVIDER_SETUP).map(([key, p]) => (
              <button key={key} onClick={() => setSelectedProvider(key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                  selectedProvider === key
                    ? "bg-indigo-600/20 border-indigo-600/40 text-indigo-300"
                    : "border-[#1e2535] text-slate-400 hover:text-white"
                }`}>
                {p.emoji} {p.label}
              </button>
            ))}
          </div>

          <div className={`border rounded-lg p-3 mb-3 ${colorClass}`}>
            <div className="font-medium text-white text-sm mb-2">{provider.emoji} {provider.label}</div>
            <ol className="space-y-1.5">
              {provider.steps.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-slate-300">
                  <span className="text-slate-500 flex-shrink-0 font-mono">{i + 1}.</span>
                  <span>{s}</span>
                </li>
              ))}
            </ol>
          </div>

          <div>
            <div className="text-xs text-slate-500 mb-1">Add to your .env file:</div>
            <CodeBlock lines={provider.envVars} />
          </div>

          <div className="mt-3 text-xs text-slate-500">
            After updating .env, restart the backend: <code className="text-slate-300 bg-[#0f1117] px-1.5 py-0.5 rounded">docker-compose restart backend</code>
          </div>
        </div>

        {/* Check again */}
        <div className="flex items-center justify-center gap-3">
          <button onClick={check} disabled={checking}
            className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm rounded-lg transition-colors">
            {checking ? <><Loader2 size={14} className="animate-spin" /> Checking…</> : <><RefreshCw size={14} /> Check Again</>}
          </button>
          {status?.llm?.ok && (
            <button onClick={onDone} className="px-6 py-2.5 bg-green-700 hover:bg-green-600 text-white text-sm rounded-lg transition-colors flex items-center gap-2">
              <CheckCircle2 size={14} /> Continue to OpsBrain
            </button>
          )}
        </div>

      </div>
    </div>
  );
}

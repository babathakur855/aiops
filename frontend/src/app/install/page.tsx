"use client";
import Link from "next/link";
import { useState } from "react";
import {
  Brain, ArrowRight, Copy, CheckCircle2,
  Server, Key, ChevronRight, Zap,
} from "lucide-react";

function CodeBlock({ code, lang = "bash" }: { code: string; lang?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="relative bg-[#0a0d14] border border-slate-800 rounded-lg overflow-hidden group">
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800 bg-slate-900/50">
        <span className="text-xs text-slate-500 font-mono">{lang}</span>
        <button onClick={copy} className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors">
          {copied ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <pre className="px-4 py-4 text-sm text-slate-300 font-mono overflow-x-auto leading-relaxed whitespace-pre">{code}</pre>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-5">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-violet-600 text-white text-sm font-bold flex items-center justify-center mt-0.5">{n}</div>
      <div className="flex-1 pb-10 border-l border-slate-800 pl-8 -ml-4">
        <h3 className="text-lg font-semibold text-white mb-4">{title}</h3>
        {children}
      </div>
    </div>
  );
}

type TabId = "docker" | "local" | "vps";

export default function InstallPage() {
  const [tab, setTab] = useState<TabId>("docker");

  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-200">
      {/* Nav */}
      <nav className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-lg font-bold text-white">
          <Brain className="w-6 h-6 text-violet-400" /> OpsBrain
        </Link>
        <div className="flex items-center gap-6 text-sm text-slate-400">
          <Link href="/why"     className="hover:text-white transition-colors">Why OpsBrain</Link>
          <Link href="/install" className="text-white font-medium">Install</Link>
          <Link href="/pricing" className="hover:text-white transition-colors">Pricing</Link>
          <Link href="/" className="flex items-center gap-1 bg-violet-600 hover:bg-violet-500 text-white px-4 py-1.5 rounded-lg transition-colors">
            Open App <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>

      <div className="max-w-3xl mx-auto px-6 py-16">
        {/* Header */}
        <div className="mb-12">
          <div className="inline-flex items-center gap-2 bg-emerald-900/30 border border-emerald-700/40 text-emerald-300 text-sm px-4 py-1.5 rounded-full mb-5">
            <Zap className="w-4 h-4" /> Up and running in ~10 minutes
          </div>
          <h1 className="text-4xl font-bold text-white mb-4">Install OpsBrain</h1>
          <p className="text-slate-400 text-lg">
            OpsBrain runs anywhere Docker runs. Pick an install method below.
          </p>
        </div>

        {/* Prerequisites */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-10">
          <h2 className="font-semibold text-white mb-4 flex items-center gap-2">
            <Key className="w-5 h-5 text-violet-400" /> Before you start — you'll need
          </h2>
          <ul className="space-y-3">
            {[
              { label: "Anthropic API key", note: "Get one at console.anthropic.com — all AI runs through Claude", required: true },
              { label: "Docker 24+ with Docker Compose v2", note: "For the recommended Docker install", required: true },
              { label: "Python 3.11+ and Node.js 18+", note: "Only for local (no-Docker) install", required: false },
            ].map(p => (
              <li key={p.label} className="flex items-start gap-3 text-sm">
                <CheckCircle2 className={`w-4 h-4 mt-0.5 flex-shrink-0 ${p.required ? "text-emerald-400" : "text-slate-600"}`} />
                <span>
                  <span className="text-slate-200 font-medium">{p.label}</span>
                  <span className="text-slate-500 ml-2">— {p.note}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        {/* Tab selector */}
        <div className="flex gap-2 mb-8 border-b border-slate-800 pb-0">
          {([
            { id: "docker", label: "Docker (recommended)", icon: "🐳" },
            { id: "local",  label: "Local (no Docker)",    icon: "💻" },
            { id: "vps",    label: "VPS / Production",     icon: "🖥️" },
          ] as { id: TabId; label: string; icon: string }[]).map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
                tab === t.id
                  ? "border-violet-500 text-violet-300 bg-violet-900/20"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* Docker tab */}
        {tab === "docker" && (
          <div className="space-y-2">
            <Step n={1} title="Clone the repository">
              <CodeBlock code={`git clone https://github.com/babathakur855/aiops.git
cd aiops`} />
            </Step>
            <Step n={2} title="Add your Anthropic API key">
              <p className="text-slate-400 text-sm mb-3">Create a <code className="text-violet-300 bg-slate-800 px-1.5 py-0.5 rounded">.env</code> file in the project root:</p>
              <CodeBlock code={`ANTHROPIC_API_KEY=sk-ant-...`} lang=".env" />
              <p className="text-slate-500 text-xs mt-2">Get your key at <span className="text-violet-400">console.anthropic.com</span></p>
            </Step>
            <Step n={3} title="Start OpsBrain">
              <CodeBlock code={`docker compose up -d`} />
              <p className="text-slate-400 text-sm mt-3">First run takes 3–5 minutes to build images. Subsequent starts are instant.</p>
            </Step>
            <Step n={4} title="Open the dashboard">
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-400">Frontend</span>
                  <span className="font-mono text-violet-300">http://localhost:3010</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Backend API</span>
                  <span className="font-mono text-violet-300">http://localhost:8011</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">API Docs (Swagger)</span>
                  <span className="font-mono text-violet-300">http://localhost:8011/docs</span>
                </div>
              </div>
            </Step>
            <Step n={5} title="Connect your first cloud account">
              <p className="text-slate-400 text-sm mb-3">In the OpsBrain dashboard, go to <strong className="text-white">Connectors</strong> and add your AWS, GCP, or Azure credentials. OpsBrain reads your cloud state and starts correlating it with alerts.</p>
              <div className="bg-emerald-900/20 border border-emerald-800/40 rounded-lg p-4 text-sm text-emerald-300">
                ✅ That's it — OpsBrain is live and ready to analyze incidents.
              </div>
            </Step>
          </div>
        )}

        {/* Local tab */}
        {tab === "local" && (
          <div className="space-y-2">
            <Step n={1} title="Clone and enter the repo">
              <CodeBlock code={`git clone https://github.com/babathakur855/aiops.git
cd aiops`} />
            </Step>
            <Step n={2} title="Set your API key">
              <CodeBlock code={`echo "ANTHROPIC_API_KEY=sk-ant-..." > .env`} lang=".env" />
            </Step>
            <Step n={3} title="Install backend dependencies">
              <CodeBlock code={`cd backend
pip install -r requirements.txt`} />
            </Step>
            <Step n={4} title="Install frontend dependencies">
              <CodeBlock code={`cd frontend
npm install`} />
            </Step>
            <Step n={5} title="Start both services">
              <p className="text-slate-400 text-sm mb-3">Open two terminals:</p>
              <CodeBlock code={`# Terminal 1 — backend
cd backend
uvicorn main:app --port 8011 --reload`} />
              <div className="mt-3">
                <CodeBlock code={`# Terminal 2 — frontend
cd frontend
npm run dev`} />
              </div>
            </Step>
            <Step n={6} title="Open the dashboard">
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 text-sm font-mono text-violet-300">
                http://localhost:3010
              </div>
            </Step>
          </div>
        )}

        {/* VPS tab */}
        {tab === "vps" && (
          <div className="space-y-2">
            <Step n={1} title="Fork the repo and add GitHub Secrets">
              <p className="text-slate-400 text-sm mb-3">Go to your GitHub repo → <strong className="text-white">Settings → Secrets → Actions</strong> and add:</p>
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-2 text-sm font-mono">
                {[
                  ["VPS_HOST",         "Your VPS IP address"],
                  ["VPS_USER",         "root (or your SSH user)"],
                  ["VPS_SSH_KEY",      "Your private SSH key (cat ~/.ssh/id_rsa)"],
                  ["VPS_DOMAIN",       "opsbrain.yourdomain.com"],
                  ["ANTHROPIC_API_KEY","sk-ant-..."],
                ].map(([k, v]) => (
                  <div key={k} className="flex gap-3">
                    <span className="text-violet-300 w-44 flex-shrink-0">{k}</span>
                    <span className="text-slate-500">{v}</span>
                  </div>
                ))}
              </div>
            </Step>
            <Step n={2} title="Add a DNS A record">
              <p className="text-slate-400 text-sm mb-3">In your DNS provider, point your subdomain to the VPS IP:</p>
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 text-sm">
                <div className="grid grid-cols-3 gap-4 text-slate-400 mb-2 text-xs uppercase tracking-wide">
                  <span>Type</span><span>Host</span><span>Value</span>
                </div>
                <div className="grid grid-cols-3 gap-4 font-mono text-slate-200">
                  <span>A</span><span>opsbrain</span><span>{"<your-vps-ip>"}</span>
                </div>
              </div>
            </Step>
            <Step n={3} title="Push to main — auto-deploys via GitHub Actions">
              <CodeBlock code={`git push origin main`} />
              <p className="text-slate-400 text-sm mt-3">
                The included <code className="text-violet-300 bg-slate-800 px-1.5 py-0.5 rounded">.github/workflows/deploy.yml</code> SSHes into your VPS, builds the Docker images, starts the containers, and wires them to <strong className="text-white">Traefik</strong> for automatic SSL via Let's Encrypt.
              </p>
            </Step>
            <Step n={4} title="Your site is live">
              <div className="bg-emerald-900/20 border border-emerald-800/40 rounded-lg p-4 text-sm text-emerald-300 font-mono">
                https://opsbrain.yourdomain.com
              </div>
              <p className="text-slate-400 text-sm mt-3">SSL certificate is provisioned automatically. No Nginx config, no certbot commands — Traefik handles everything.</p>
            </Step>
          </div>
        )}

        {/* Troubleshooting */}
        <div className="mt-12 bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h2 className="font-semibold text-white mb-4">Common issues</h2>
          <div className="space-y-4 text-sm">
            {[
              { q: "LLM not configured error", a: 'Check that ANTHROPIC_API_KEY is set in .env and restart: docker compose restart backend' },
              { q: "Frontend shows blank page", a: 'Make sure the backend is healthy: docker compose ps — the backend must be healthy before frontend starts.' },
              { q: "Port 3010 already in use", a: 'Change the port mapping in docker-compose.yml: "3011:3010" to use 3011 instead.' },
              { q: "Traefik 404 on domain", a: 'Confirm VPS_DOMAIN is set in .env on the VPS and the containers are on the traefik-public network.' },
            ].map(item => (
              <div key={item.q} className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-violet-400 mt-0.5 flex-shrink-0" />
                <div>
                  <div className="text-white font-medium">{item.q}</div>
                  <div className="text-slate-400 mt-0.5">{item.a}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <footer className="border-t border-slate-800 px-6 py-8 text-center text-slate-500 text-sm">
        © 2026 OpsBrain · <Link href="/why" className="hover:text-slate-300">Why OpsBrain</Link> · <Link href="/install" className="hover:text-slate-300">Install</Link> · <Link href="/pricing" className="hover:text-slate-300">Pricing</Link>
      </footer>
    </div>
  );
}

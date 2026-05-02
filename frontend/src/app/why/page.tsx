"use client";
import Link from "next/link";
import {
  Brain, Zap, DollarSign, Shield, Eye, CheckCircle2, X,
  ArrowRight, Layers, MessageSquare, TrendingDown, Server,
} from "lucide-react";

const FEATURES = [
  {
    icon: Brain,
    title: "Claude-Powered Reasoning",
    desc: "OpsBrain uses Anthropic's Claude to reason through incidents — not just pattern-match. It reads your actual logs, traces, and runbooks before generating a response.",
  },
  {
    icon: Eye,
    title: "Full Transparency",
    desc: "Every AI recommendation shows its reasoning chain. You see exactly why OpsBrain flagged something, not a black-box score.",
  },
  {
    icon: DollarSign,
    title: "10× Cheaper Than Alternatives",
    desc: "You pay only for Anthropic API usage — typically $5–$40/month vs $2,000–$8,000/month for SaaS AIOps tools.",
  },
  {
    icon: Shield,
    title: "Self-Hosted, Your Data Stays Yours",
    desc: "Deploy on your own VPS or Kubernetes cluster. Your logs, metrics, and alerts never leave your infrastructure.",
  },
  {
    icon: Layers,
    title: "Multi-Cloud & Kubernetes Native",
    desc: "AWS, GCP, Azure — OpsBrain connects to all of them. First-class support for Kubernetes pod health, HPA events, and namespace-level diagnostics.",
  },
  {
    icon: MessageSquare,
    title: "Custom Knowledge Base",
    desc: "Upload your runbooks, SOPs, and post-mortems. OpsBrain references them when diagnosing incidents, so recommendations match your team's actual playbooks.",
  },
];

const COMPARISON = [
  { feature: "AI Model",               opsbrain: "Claude (Anthropic)",         nudgebee: "Proprietary ML",    pagerduty: "Basic ML",          datadog: "Watchdog (ML)",       dynatrace: "Davis AI" },
  { feature: "Transparent Reasoning",  opsbrain: true,                          nudgebee: false,               pagerduty: false,               datadog: false,                 dynatrace: false },
  { feature: "Self-Hosted Option",     opsbrain: true,                          nudgebee: false,               pagerduty: false,               datadog: false,                 dynatrace: false },
  { feature: "Custom Knowledge Base",  opsbrain: true,                          nudgebee: false,               pagerduty: false,               datadog: false,                 dynatrace: false },
  { feature: "Kubernetes Native",      opsbrain: true,                          nudgebee: true,                pagerduty: "Partial",           datadog: true,                  dynatrace: true },
  { feature: "Multi-Cloud",            opsbrain: true,                          nudgebee: true,                pagerduty: "Partial",           datadog: true,                  dynatrace: true },
  { feature: "Runbook Integration",    opsbrain: true,                          nudgebee: "Limited",           pagerduty: true,                datadog: "Limited",             dynatrace: "Limited" },
  { feature: "Open Source",            opsbrain: true,                          nudgebee: false,               pagerduty: false,               datadog: false,                 dynatrace: false },
  { feature: "Typical Monthly Cost",   opsbrain: "$5–$40 (API only)",           nudgebee: "$2K–$8K",           pagerduty: "$20–$30/user",      datadog: "$15–$30/host",        dynatrace: "$25–$80/host" },
];

function Cell({ value }: { value: string | boolean }) {
  if (value === true)  return <CheckCircle2 className="w-5 h-5 text-emerald-400 mx-auto" />;
  if (value === false) return <X className="w-5 h-5 text-slate-600 mx-auto" />;
  return <span className="text-sm text-slate-300">{value}</span>;
}

export default function WhyPage() {
  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-200">
      {/* Nav */}
      <nav className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-lg font-bold text-white">
          <Brain className="w-6 h-6 text-violet-400" /> OpsBrain
        </Link>
        <div className="flex items-center gap-6 text-sm text-slate-400">
          <Link href="/why"     className="text-white font-medium">Why OpsBrain</Link>
          <Link href="/install" className="hover:text-white transition-colors">Install</Link>
          <Link href="/pricing" className="hover:text-white transition-colors">Pricing</Link>
          <Link href="/" className="flex items-center gap-1 bg-violet-600 hover:bg-violet-500 text-white px-4 py-1.5 rounded-lg transition-colors">
            Open App <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-5xl mx-auto px-6 py-20 text-center">
        <div className="inline-flex items-center gap-2 bg-violet-900/30 border border-violet-700/40 text-violet-300 text-sm px-4 py-1.5 rounded-full mb-6">
          <Zap className="w-4 h-4" /> Claude-Powered AIOps
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight mb-6">
          Stop paying $8K/month for<br />
          <span className="text-violet-400">AIOps that can't explain itself</span>
        </h1>
        <p className="text-xl text-slate-400 max-w-2xl mx-auto mb-10">
          OpsBrain uses Claude to reason through your incidents like a senior SRE — transparent,
          self-hosted, and a fraction of the cost of legacy AIOps platforms.
        </p>
        <div className="flex items-center justify-center gap-4">
          <Link href="/install" className="bg-violet-600 hover:bg-violet-500 text-white px-6 py-3 rounded-lg font-medium transition-colors flex items-center gap-2">
            Get Started Free <ArrowRight className="w-4 h-4" />
          </Link>
          <Link href="/pricing" className="border border-slate-700 hover:border-slate-500 text-slate-300 px-6 py-3 rounded-lg font-medium transition-colors">
            See Pricing
          </Link>
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-slate-800 bg-slate-900/30">
        <div className="max-w-5xl mx-auto px-6 py-10 grid grid-cols-2 sm:grid-cols-4 gap-8 text-center">
          {[
            { value: "10×", label: "cheaper than NudgeBee" },
            { value: "<2min", label: "mean time to insight" },
            { value: "100%", label: "reasoning transparency" },
            { value: "0", label: "data leaves your infra" },
          ].map(s => (
            <div key={s.label}>
              <div className="text-3xl font-bold text-violet-400 mb-1">{s.value}</div>
              <div className="text-sm text-slate-400">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="max-w-5xl mx-auto px-6 py-20">
        <h2 className="text-3xl font-bold text-white text-center mb-4">What makes OpsBrain different</h2>
        <p className="text-slate-400 text-center mb-12 max-w-xl mx-auto">
          Every other AIOps tool gives you a score or an alert. OpsBrain gives you an explanation.
        </p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map(f => (
            <div key={f.title} className="bg-slate-900 border border-slate-800 rounded-xl p-6 hover:border-violet-700/50 transition-colors">
              <f.icon className="w-8 h-8 text-violet-400 mb-4" />
              <h3 className="font-semibold text-white mb-2">{f.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Comparison table */}
      <section className="max-w-6xl mx-auto px-6 py-16">
        <h2 className="text-3xl font-bold text-white text-center mb-4">How we compare</h2>
        <p className="text-slate-400 text-center mb-10">OpsBrain vs the tools your team is probably already evaluating</p>
        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-900/60">
                <th className="text-left px-5 py-4 text-slate-400 font-medium w-48">Feature</th>
                <th className="px-5 py-4 text-violet-400 font-bold">OpsBrain</th>
                <th className="px-5 py-4 text-slate-400 font-medium">NudgeBee</th>
                <th className="px-5 py-4 text-slate-400 font-medium">PagerDuty</th>
                <th className="px-5 py-4 text-slate-400 font-medium">Datadog</th>
                <th className="px-5 py-4 text-slate-400 font-medium">Dynatrace</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON.map((row, i) => (
                <tr key={row.feature} className={`border-b border-slate-800/60 ${i % 2 === 0 ? "bg-slate-900/20" : ""}`}>
                  <td className="px-5 py-3.5 text-slate-300 font-medium">{row.feature}</td>
                  <td className="px-5 py-3.5 text-center bg-violet-900/10">
                    <Cell value={row.opsbrain} />
                  </td>
                  <td className="px-5 py-3.5 text-center"><Cell value={row.nudgebee} /></td>
                  <td className="px-5 py-3.5 text-center"><Cell value={row.pagerduty} /></td>
                  <td className="px-5 py-3.5 text-center"><Cell value={row.datadog} /></td>
                  <td className="px-5 py-3.5 text-center"><Cell value={row.dynatrace} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Cost comparison */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <h2 className="text-3xl font-bold text-white text-center mb-12">Real cost comparison</h2>
        <div className="grid sm:grid-cols-3 gap-6">
          {[
            { name: "Dynatrace",  cost: "$4,800/mo", detail: "~20 hosts × $240/host/mo", color: "slate" },
            { name: "NudgeBee",   cost: "$5,000/mo", detail: "Mid-tier enterprise plan",  color: "slate" },
            { name: "OpsBrain",   cost: "$20/mo",    detail: "Anthropic API usage only",  color: "violet", highlight: true },
          ].map(p => (
            <div key={p.name} className={`rounded-xl border p-6 text-center ${p.highlight ? "border-violet-500 bg-violet-900/20" : "border-slate-800 bg-slate-900"}`}>
              <div className="text-slate-400 text-sm mb-2">{p.name}</div>
              <div className={`text-3xl font-bold mb-2 ${p.highlight ? "text-violet-400" : "text-white"}`}>{p.cost}</div>
              <div className="text-xs text-slate-500">{p.detail}</div>
              {p.highlight && <div className="mt-3 text-xs text-emerald-400 font-medium">240× cheaper</div>}
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-2xl mx-auto px-6 py-20 text-center">
        <TrendingDown className="w-12 h-12 text-violet-400 mx-auto mb-6" />
        <h2 className="text-3xl font-bold text-white mb-4">Ready to cut your AIOps bill by 90%?</h2>
        <p className="text-slate-400 mb-8">Deploy in 10 minutes. Bring your own Anthropic API key. No vendor lock-in.</p>
        <Link href="/install" className="bg-violet-600 hover:bg-violet-500 text-white px-8 py-3 rounded-lg font-medium transition-colors inline-flex items-center gap-2">
          <Server className="w-5 h-5" /> Get Started Free
        </Link>
      </section>

      <footer className="border-t border-slate-800 px-6 py-8 text-center text-slate-500 text-sm">
        © 2026 OpsBrain · <Link href="/why" className="hover:text-slate-300">Why OpsBrain</Link> · <Link href="/install" className="hover:text-slate-300">Install</Link> · <Link href="/pricing" className="hover:text-slate-300">Pricing</Link>
      </footer>
    </div>
  );
}

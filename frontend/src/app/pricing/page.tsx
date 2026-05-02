"use client";
import Link from "next/link";
import {
  Brain, ArrowRight, CheckCircle2, X, Zap, Server,
  Users, Building2, HelpCircle, ChevronDown, ChevronUp,
} from "lucide-react";
import { useState } from "react";

const PLANS = [
  {
    name: "Starter",
    price: "Free",
    period: "",
    desc: "Self-hosted. Bring your own Anthropic API key. No limits.",
    cta: "Deploy Now",
    ctaHref: "/install",
    highlight: false,
    icon: Server,
    features: [
      "Unlimited environments",
      "AI incident analysis (Claude)",
      "AWS / GCP / Azure connectors",
      "Kubernetes pod monitoring",
      "Custom knowledge base",
      "API + Swagger UI",
      "Community support",
      "Pay only Anthropic API costs (~$5–$40/mo)",
    ],
    missing: [
      "Managed cloud hosting",
      "SSO / SAML",
      "SLA guarantee",
      "Dedicated support",
    ],
  },
  {
    name: "Team",
    price: "$99",
    period: "/month",
    desc: "Fully managed. We host it, patch it, and back it up. Up to 15 users.",
    cta: "Start Free Trial",
    ctaHref: "mailto:hello@opsbrain.io?subject=Team Plan Trial",
    highlight: true,
    icon: Users,
    badge: "Most Popular",
    features: [
      "Everything in Starter",
      "Managed cloud hosting (EU / US)",
      "Automatic updates & backups",
      "Up to 15 team members",
      "Slack + PagerDuty integrations",
      "14-day data retention",
      "Email support (48h SLA)",
      "99.9% uptime SLA",
    ],
    missing: [
      "SSO / SAML",
      "Custom data retention",
      "Dedicated instance",
    ],
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    desc: "Dedicated VPC deployment, SSO, compliance exports, and a named support engineer.",
    cta: "Talk to Sales",
    ctaHref: "mailto:sales@opsbrain.io?subject=Enterprise Inquiry",
    highlight: false,
    icon: Building2,
    features: [
      "Everything in Team",
      "Dedicated VPC / on-prem deploy",
      "SSO / SAML / OIDC",
      "Unlimited users",
      "Custom data retention",
      "SOC 2 compliance exports",
      "99.99% uptime SLA",
      "Named support engineer",
      "Custom integrations",
      "Quarterly roadmap input",
    ],
    missing: [],
  },
];

const FAQS = [
  {
    q: "What does the Starter plan actually cost?",
    a: "The OpsBrain software itself is free and open source. You self-host it and pay only for Anthropic API usage. For a typical team running 50–200 AI analyses per day, that's roughly $5–$40/month in API costs — compared to $2,000–$8,000/month for competing SaaS AIOps tools.",
  },
  {
    q: "What Anthropic model does OpsBrain use?",
    a: "OpsBrain uses Claude claude-sonnet-4-6 by default — the best balance of intelligence and cost. You can switch to Claude Haiku for lower cost or Claude Opus for deeper analysis by changing the model config in your .env file.",
  },
  {
    q: "Can I migrate from Starter to Team later?",
    a: "Yes. Your environments, knowledge base, and connectors are all portable. Contact us and we'll handle the migration — usually takes under an hour.",
  },
  {
    q: "Is my data safe on the Starter (self-hosted) plan?",
    a: "Yes. On Starter, everything runs inside your own infrastructure. Logs, metrics, and alerts never leave your VPS or Kubernetes cluster. The only external call is to the Anthropic API for AI analysis.",
  },
  {
    q: "Do you offer a free trial for Team?",
    a: "Yes — 14 days free, no credit card required. Email us at hello@opsbrain.io to get started.",
  },
  {
    q: "What's included in Enterprise support?",
    a: "A named engineer who knows your deployment. 4-hour response SLA, dedicated Slack channel, onboarding sessions, and quarterly reviews of your alert tuning and cost optimization.",
  },
];

function FAQ({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-slate-800">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between py-5 text-left text-white hover:text-violet-300 transition-colors"
      >
        <span className="font-medium pr-8">{q}</span>
        {open ? <ChevronUp className="w-5 h-5 flex-shrink-0 text-violet-400" /> : <ChevronDown className="w-5 h-5 flex-shrink-0 text-slate-400" />}
      </button>
      {open && <p className="pb-5 text-slate-400 text-sm leading-relaxed">{a}</p>}
    </div>
  );
}

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-200">
      {/* Nav */}
      <nav className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-lg font-bold text-white">
          <Brain className="w-6 h-6 text-violet-400" /> OpsBrain
        </Link>
        <div className="flex items-center gap-6 text-sm text-slate-400">
          <Link href="/why"     className="hover:text-white transition-colors">Why OpsBrain</Link>
          <Link href="/install" className="hover:text-white transition-colors">Install</Link>
          <Link href="/pricing" className="text-white font-medium">Pricing</Link>
          <Link href="/" className="flex items-center gap-1 bg-violet-600 hover:bg-violet-500 text-white px-4 py-1.5 rounded-lg transition-colors">
            Open App <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-3xl mx-auto px-6 py-16 text-center">
        <div className="inline-flex items-center gap-2 bg-violet-900/30 border border-violet-700/40 text-violet-300 text-sm px-4 py-1.5 rounded-full mb-5">
          <Zap className="w-4 h-4" /> Simple, transparent pricing
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold text-white mb-4">
          Start free.<br />Scale when you need to.
        </h1>
        <p className="text-slate-400 text-lg max-w-xl mx-auto">
          OpsBrain is open source. Self-host for free forever, or let us run it for you.
          No per-seat fees. No surprise overage charges.
        </p>
      </section>

      {/* Plans */}
      <section className="max-w-6xl mx-auto px-6 pb-16">
        <div className="grid md:grid-cols-3 gap-6">
          {PLANS.map(plan => (
            <div
              key={plan.name}
              className={`rounded-xl border p-7 flex flex-col relative ${
                plan.highlight
                  ? "border-violet-500 bg-violet-900/15 shadow-lg shadow-violet-900/20"
                  : "border-slate-800 bg-slate-900/40"
              }`}
            >
              {plan.badge && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-violet-600 text-white text-xs font-bold px-4 py-1 rounded-full">
                  {plan.badge}
                </div>
              )}
              <plan.icon className={`w-8 h-8 mb-4 ${plan.highlight ? "text-violet-400" : "text-slate-400"}`} />
              <div className="text-sm text-slate-400 mb-1">{plan.name}</div>
              <div className="flex items-baseline gap-1 mb-2">
                <span className="text-4xl font-bold text-white">{plan.price}</span>
                <span className="text-slate-400 text-sm">{plan.period}</span>
              </div>
              <p className="text-slate-400 text-sm mb-6 leading-relaxed">{plan.desc}</p>

              <Link
                href={plan.ctaHref}
                className={`block text-center py-2.5 rounded-lg font-medium text-sm mb-7 transition-colors ${
                  plan.highlight
                    ? "bg-violet-600 hover:bg-violet-500 text-white"
                    : "border border-slate-700 hover:border-slate-500 text-slate-300"
                }`}
              >
                {plan.cta}
              </Link>

              <div className="space-y-2.5 flex-1">
                {plan.features.map(f => (
                  <div key={f} className="flex items-start gap-2.5 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
                    <span className="text-slate-300">{f}</span>
                  </div>
                ))}
                {plan.missing.map(f => (
                  <div key={f} className="flex items-start gap-2.5 text-sm">
                    <X className="w-4 h-4 text-slate-700 mt-0.5 flex-shrink-0" />
                    <span className="text-slate-600">{f}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Cost calculator context */}
      <section className="max-w-3xl mx-auto px-6 py-12">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8">
          <h2 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-violet-400" /> What will my Anthropic API bill be?
          </h2>
          <div className="space-y-4 text-sm">
            {[
              { label: "Light use", detail: "~20 AI analyses/day", cost: "~$3–$8/mo", color: "emerald" },
              { label: "Medium use", detail: "~100 AI analyses/day", cost: "~$15–$25/mo", color: "violet" },
              { label: "Heavy use", detail: "~500 AI analyses/day (large team, high alert volume)", cost: "~$50–$80/mo", color: "amber" },
            ].map(row => (
              <div key={row.label} className="flex items-center justify-between py-3 border-b border-slate-800 last:border-0">
                <div>
                  <span className="text-white font-medium">{row.label}</span>
                  <span className="text-slate-500 ml-3">{row.detail}</span>
                </div>
                <span className={`font-mono font-bold ${
                  row.color === "emerald" ? "text-emerald-400" :
                  row.color === "amber" ? "text-amber-400" : "text-violet-400"
                }`}>{row.cost}</span>
              </div>
            ))}
          </div>
          <p className="text-slate-500 text-xs mt-5">
            Based on Claude claude-sonnet-4-6 pricing. Each AI analysis uses ~2K–8K tokens depending on log volume and context.
            Anthropic pricing may change — check <span className="text-violet-400">anthropic.com/pricing</span> for current rates.
          </p>
        </div>
      </section>

      {/* FAQs */}
      <section className="max-w-3xl mx-auto px-6 py-12">
        <h2 className="text-2xl font-bold text-white mb-8">Frequently asked questions</h2>
        <div>
          {FAQS.map(f => <FAQ key={f.q} {...f} />)}
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-2xl mx-auto px-6 py-16 text-center">
        <h2 className="text-3xl font-bold text-white mb-4">Start for free today</h2>
        <p className="text-slate-400 mb-8">
          Deploy in 10 minutes. No credit card. No sales call.
          Switch to Team or Enterprise when your team is ready.
        </p>
        <div className="flex items-center justify-center gap-4">
          <Link href="/install" className="bg-violet-600 hover:bg-violet-500 text-white px-7 py-3 rounded-lg font-medium transition-colors flex items-center gap-2">
            <Server className="w-4 h-4" /> Self-Host Free
          </Link>
          <Link href="mailto:hello@opsbrain.io" className="border border-slate-700 hover:border-slate-500 text-slate-300 px-7 py-3 rounded-lg font-medium transition-colors">
            Talk to Us
          </Link>
        </div>
      </section>

      <footer className="border-t border-slate-800 px-6 py-8 text-center text-slate-500 text-sm">
        © 2026 OpsBrain · <Link href="/why" className="hover:text-slate-300">Why OpsBrain</Link> · <Link href="/install" className="hover:text-slate-300">Install</Link> · <Link href="/pricing" className="hover:text-slate-300">Pricing</Link>
      </footer>
    </div>
  );
}

"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import {
  BookOpen, Upload, Edit3, X, Plus, Trash2, FileText, CheckCircle2,
  Link, Package, ChevronRight, Layers,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

// ── Types ─────────────────────────────────────────────────────────────────────
interface KnowledgeDoc {
  id: string; name: string; doc_type: string; checkout_types: string[];
  description: string; content: string; file_size: number;
  updated_at: string; is_default: boolean;
}
interface KnowledgeSet {
  id: string; name: string; description: string; checkout_types: string[];
  sop_doc_id: string | null; sop_doc_name: string | null;
  template_doc_id: string | null; template_doc_name: string | null;
  context_doc_ids: string[]; context_doc_names: string[];
  created_at: string; updated_at: string; is_default: boolean;
}

// ── Constants ─────────────────────────────────────────────────────────────────
const DOC_COLORS: Record<string, string> = {
  sop:             "text-indigo-400 bg-indigo-950/40 border-indigo-800/40",
  report_template: "text-green-400 bg-green-950/40 border-green-800/40",
  context:         "text-amber-400 bg-amber-950/40 border-amber-800/40",
};
const DOC_LABELS: Record<string, string> = {
  sop: "SOP", report_template: "Template", context: "Context",
};
const CO_COLORS: Record<string, string> = {
  infra_health: "text-indigo-300", cost_review: "text-green-300",
  capacity_review: "text-amber-300", slo_review: "text-blue-300",
  incident_review: "text-red-300", custom: "text-purple-300", "*": "text-slate-400",
};
const CHECKOUT_TYPES = ["infra_health","cost_review","capacity_review","slo_review","incident_review","custom"];

// ── Small helpers ─────────────────────────────────────────────────────────────
function Spinner() {
  return <div className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin inline-block" />;
}
function Card({ children, className = "", onClick }: { children: React.ReactNode; className?: string; onClick?: () => void }) {
  return <div onClick={onClick} className={`bg-[#161b27] border border-[#1e2535] rounded-xl ${className}`}>{children}</div>;
}
function DocBadge({ type }: { type: string }) {
  return <span className={`text-xs px-1.5 py-0.5 rounded border ${DOC_COLORS[type] || "text-slate-400 bg-slate-800 border-slate-600"}`}>{DOC_LABELS[type] || type}</span>;
}

// ── Upload modal ──────────────────────────────────────────────────────────────
function UploadModal({ docType, onSave, onClose, post }: {
  docType: "sop" | "report_template" | "context";
  onSave: (doc: KnowledgeDoc) => void;
  onClose: () => void;
  post: any;
}) {
  const [tab, setTab]           = useState<"file"|"paste">("file");
  const [name, setName]         = useState("");
  const [desc, setDesc]         = useState("");
  const [cts, setCts]           = useState<string[]>([]);
  const [content, setContent]   = useState("");
  const [file, setFile]         = useState<File|null>(null);
  const [saving, setSaving]     = useState(false);
  const fileRef                 = useRef<HTMLInputElement>(null);

  const titles = { sop: "📋 Upload SOP", report_template: "📄 Upload Report Template", context: "🗂️ Upload Context" };
  const btns   = { sop: "bg-indigo-600 hover:bg-indigo-500", report_template: "bg-green-700 hover:bg-green-600", context: "bg-amber-600 hover:bg-amber-500" };
  const placeholders = {
    sop: "# Infrastructure Health SOP\n\n## Step 1 — Pod Health\nTool: get_pod_status\nCheck for: CrashLoopBackOff, OOMKilled, restarts > 10\nThreshold: Critical if restarts > 50\n\n## Step 2 — Node Resources\n...",
    report_template: "# Infra Health Report\n**Date:** {date} | **Status:** {STATUS}\n\n## Component Health\n| Component | Status | Metric | Action |\n|-----------|--------|--------|--------|\n| Pods | ... | ... | ... |\n\n## Recommendations\n...",
    context: "# AWS Architecture Context\n\nAccount: 123456789\nRegion: us-east-1\n\n## SLO Targets\n- order-service: < 1% errors\n- payment-service: < 500ms p99\n...",
  };

  async function save() {
    setSaving(true);
    const resolvedCts = cts.length ? cts : ["*"];
    try {
      let r: KnowledgeDoc | null = null;
      if (tab === "file" && file) {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("name", name || file.name.replace(/\.[^.]+$/, ""));
        fd.append("doc_type", docType);
        fd.append("checkout_types", JSON.stringify(resolvedCts));
        fd.append("description", desc);
        const token = JSON.parse(localStorage.getItem("opsbrain_auth") || "{}").token || "";
        r = await fetch(`${API}/api/v1/knowledge/upload`, {
          method: "POST", headers: { Authorization: `Bearer ${token}` }, body: fd,
        }).then(res => res.json());
      } else {
        r = await post("/api/v1/knowledge", { name, doc_type: docType, checkout_types: resolvedCts, description: desc, content });
      }
      if (r?.id) { onSave(r); onClose(); }
    } finally { setSaving(false); }
  }

  const canSave = tab === "file" ? !!file : !!content.trim();

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-[#0f1117] border border-[#1e2535] rounded-2xl w-full max-w-2xl shadow-2xl">
        <div className={`px-6 py-4 border-b border-[#1e2535] flex items-center justify-between rounded-t-2xl
          ${docType==="sop"?"bg-indigo-950/30":docType==="report_template"?"bg-green-950/30":"bg-amber-950/30"}`}>
          <div>
            <h2 className="text-base font-semibold text-white">{titles[docType]}</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {docType==="sop" ? "Step-by-step instructions Claude follows — what tools to call, thresholds, status rules"
               : docType==="report_template" ? "Sample completed report — Claude formats every output to match this exactly"
               : "Background knowledge — AWS accounts, SLO definitions, architecture, team contacts"}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white p-1"><X size={18}/></button>
        </div>

        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Name <span className="text-slate-600">(auto from filename)</span></label>
              <input value={name} onChange={e=>setName(e.target.value)} placeholder={`My ${DOC_LABELS[docType]}`}
                className="w-full bg-[#161b27] border border-[#1e2535] text-slate-200 text-sm rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50" />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Description <span className="text-slate-600">(optional)</span></label>
              <input value={desc} onChange={e=>setDesc(e.target.value)} placeholder="What does this cover?"
                className="w-full bg-[#161b27] border border-[#1e2535] text-slate-200 text-sm rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50" />
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1.5">Applies to checkout types <span className="text-slate-600">(which checkouts can use this doc?)</span></label>
            <div className="flex gap-2 flex-wrap">
              {[{v:"*",l:"All types"},{v:"infra_health",l:"Infra Health"},{v:"cost_review",l:"Cost Review"},
                {v:"capacity_review",l:"Capacity"},{v:"slo_review",l:"SLO Review"},{v:"incident_review",l:"Incidents"},{v:"custom",l:"Custom"}].map(({v,l})=>(
                <button key={v} onClick={()=>setCts(p=>p.includes(v)?p.filter(c=>c!==v):v==="*"?["*"]:[...p.filter(c=>c!=="*"),v])}
                  className={`px-2.5 py-1 text-xs rounded-lg border transition-colors ${cts.includes(v)?"bg-indigo-600/25 border-indigo-600/50 text-indigo-300":"border-[#1e2535] text-slate-500 hover:text-slate-300"}`}>
                  {l}
                </button>
              ))}
            </div>
            {cts.length===0&&<p className="text-xs text-amber-500 mt-1">Select at least one type — or "All types" to make this available everywhere</p>}
          </div>

          <div className="border border-[#1e2535] rounded-xl overflow-hidden">
            <div className="flex border-b border-[#1e2535]">
              {(["file","paste"] as const).map(t=>(
                <button key={t} onClick={()=>setTab(t)}
                  className={`flex-1 py-2.5 text-sm font-medium flex items-center justify-center gap-2 transition-colors ${tab===t?"bg-[#161b27] text-white":"text-slate-500 hover:text-slate-300"}`}>
                  {t==="file"?<><Upload size={14}/> Upload File <span className="text-xs font-normal text-slate-500">(.md / .txt)</span></>:<><Edit3 size={14}/> Paste / Type</>}
                </button>
              ))}
            </div>
            {tab==="file"?(
              <div className="p-4">
                {file?(
                  <div className="flex items-center gap-3 p-3 bg-[#161b27] rounded-lg border border-green-800/30">
                    <CheckCircle2 size={20} className="text-green-400 flex-shrink-0"/>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white font-medium">{file.name}</div>
                      <div className="text-xs text-slate-500">{(file.size/1024).toFixed(1)} KB</div>
                    </div>
                    <button onClick={()=>setFile(null)} className="text-slate-500 hover:text-red-400"><X size={16}/></button>
                  </div>
                ):(
                  <div onClick={()=>fileRef.current?.click()}
                    className="border-2 border-dashed border-[#1e2535] hover:border-indigo-600/50 rounded-xl p-10 text-center cursor-pointer transition-colors group">
                    <Upload size={32} className="mx-auto mb-3 text-slate-600 group-hover:text-indigo-400 transition-colors"/>
                    <p className="text-sm text-slate-400 group-hover:text-slate-200">Click to browse or drag &amp; drop</p>
                    <p className="text-xs text-slate-600 mt-1">Supported: <code>.md</code> · <code>.txt</code> · up to 500 KB</p>
                  </div>
                )}
                <input ref={fileRef} type="file" accept=".md,.txt,.markdown" className="hidden"
                  onChange={e=>{const f=e.target.files?.[0];if(f){setFile(f);if(!name)setName(f.name.replace(/\.[^.]+$/,""))}}}/>
              </div>
            ):(
              <textarea value={content} onChange={e=>setContent(e.target.value)} rows={14}
                placeholder={placeholders[docType]}
                className="w-full bg-[#0b0e16] text-slate-300 text-xs font-mono p-4 outline-none resize-none"/>
            )}
          </div>

          <div className="flex gap-3">
            <button onClick={save} disabled={saving||!canSave||!cts.length}
              className={`flex-1 py-2.5 text-sm font-medium text-white rounded-xl flex items-center justify-center gap-2 transition-colors disabled:opacity-40 ${btns[docType]}`}>
              {saving?<><Spinner/> Saving…</>:<><Upload size={14}/> Save {DOC_LABELS[docType]}</>}
            </button>
            <button onClick={onClose} className="px-5 py-2.5 bg-[#1e2535] hover:bg-[#2a3548] text-slate-300 text-sm rounded-xl">Cancel</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Set Builder modal ─────────────────────────────────────────────────────────
function SetBuilderModal({ docs, editSet, onSave, onClose, post }: {
  docs: KnowledgeDoc[];
  editSet: KnowledgeSet | null;
  onSave: (s: KnowledgeSet) => void;
  onClose: () => void;
  post: any;
}) {
  const [name, setName]       = useState(editSet?.name || "");
  const [desc, setDesc]       = useState(editSet?.description || "");
  const [cts, setCts]         = useState<string[]>(editSet?.checkout_types || []);
  const [sopId, setSopId]     = useState<string|null>(editSet?.sop_doc_id || null);
  const [tplId, setTplId]     = useState<string|null>(editSet?.template_doc_id || null);
  const [ctxIds, setCtxIds]   = useState<string[]>(editSet?.context_doc_ids || []);
  const [isDefault, setDef]   = useState(editSet?.is_default || false);
  const [saving, setSaving]   = useState(false);

  const sops = docs.filter(d=>d.doc_type==="sop");
  const tpls = docs.filter(d=>d.doc_type==="report_template");
  const ctxs = docs.filter(d=>d.doc_type==="context");

  async function save() {
    setSaving(true);
    try {
      const body = { name, description: desc, checkout_types: cts, sop_doc_id: sopId,
                     template_doc_id: tplId, context_doc_ids: ctxIds, is_default: isDefault };
      let r: KnowledgeSet;
      if (editSet) {
        r = await post(`/api/v1/knowledge/sets/${editSet.id}`, body);
      } else {
        r = await post("/api/v1/knowledge/sets", body);
      }
      if (r?.id) { onSave(r); onClose(); }
    } finally { setSaving(false); }
  }

  function DocPicker({ label, icon, selected, setSelected, pool, type }: {
    label: string; icon: string; selected: string | null;
    setSelected: (id: string|null)=>void; pool: KnowledgeDoc[]; type: string;
  }) {
    const sel = pool.find(d=>d.id===selected);
    return (
      <div className={`rounded-xl border p-4 ${selected?"border-indigo-600/40 bg-indigo-950/10":"border-dashed border-[#1e2535]"}`}>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-lg">{icon}</span>
          <span className="text-sm font-medium text-white">{label}</span>
          {selected&&<span className="text-xs text-green-400 ml-auto flex items-center gap-1"><CheckCircle2 size={11}/> Set</span>}
          {selected&&<button onClick={()=>setSelected(null)} className="text-slate-500 hover:text-red-400 ml-1"><X size={12}/></button>}
        </div>
        {sel?(
          <div className="p-2 bg-[#0f1117] rounded-lg border border-[#1e2535]">
            <DocBadge type={type}/>
            <div className="text-xs font-medium text-white mt-1">{sel.name}</div>
            {sel.description&&<div className="text-xs text-slate-500 mt-0.5">{sel.description}</div>}
          </div>
        ):(
          <div className="text-xs text-slate-600 mb-2">No {label.toLowerCase()} selected — pick one below</div>
        )}
        {pool.length===0?(
          <div className="text-xs text-slate-600 mt-2">No {DOC_LABELS[type]}s uploaded yet</div>
        ):(
          <div className="mt-2 space-y-1 max-h-36 overflow-y-auto">
            {pool.map(d=>(
              <button key={d.id} onClick={()=>setSelected(d.id===selected?null:d.id)}
                className={`w-full text-left flex items-center gap-2 p-2 rounded-lg border text-xs transition-colors ${d.id===selected?"bg-indigo-600/20 border-indigo-600/40 text-indigo-200":"border-[#1e2535] text-slate-400 hover:text-white hover:bg-[#1a2236]"}`}>
                <span className="flex-1 truncate">{d.name}</span>
                {d.is_default&&<span className="text-slate-600 flex-shrink-0">built-in</span>}
                {d.id===selected&&<CheckCircle2 size={11} className="text-indigo-400 flex-shrink-0"/>}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={e=>{if(e.target===e.currentTarget)onClose();}}>
      <div className="bg-[#0f1117] border border-[#1e2535] rounded-2xl w-full max-w-3xl shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-[#1e2535] flex items-center justify-between sticky top-0 bg-[#0f1117] z-10">
          <div>
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <Package size={16} className="text-indigo-400"/>
              {editSet?"Edit Knowledge Set":"Create Knowledge Set"}
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Bundle one SOP + one template + context docs into a named set · assign to a checkout
            </p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white p-1"><X size={18}/></button>
        </div>

        <div className="p-6 space-y-5">
          {/* Name + description */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Set Name *</label>
              <input value={name} onChange={e=>setName(e.target.value)}
                placeholder="Weekly Infra Health - Production"
                className="w-full bg-[#161b27] border border-[#1e2535] text-slate-200 text-sm rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50"/>
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Description</label>
              <input value={desc} onChange={e=>setDesc(e.target.value)}
                placeholder="Used for weekly prod infra checks"
                className="w-full bg-[#161b27] border border-[#1e2535] text-slate-200 text-sm rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50"/>
            </div>
          </div>

          {/* Checkout type tags */}
          <div>
            <label className="text-xs text-slate-400 block mb-1.5">Designed for checkout types</label>
            <div className="flex gap-2 flex-wrap">
              {[{v:"*",l:"All"},{v:"infra_health",l:"Infra Health"},{v:"cost_review",l:"Cost Review"},
                {v:"capacity_review",l:"Capacity"},{v:"slo_review",l:"SLO Review"},{v:"incident_review",l:"Incidents"},{v:"custom",l:"Custom"}].map(({v,l})=>(
                <button key={v} onClick={()=>setCts(p=>p.includes(v)?p.filter(c=>c!==v):v==="*"?["*"]:[...p.filter(c=>c!=="*"),v])}
                  className={`px-2.5 py-1 text-xs rounded-lg border transition-colors ${cts.includes(v)?"bg-indigo-600/25 border-indigo-600/50 text-indigo-300":"border-[#1e2535] text-slate-500 hover:text-slate-300"}`}>
                  {l}
                </button>
              ))}
            </div>
          </div>

          {/* Doc pickers */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Documents in this set</h3>
            <DocPicker label="SOP (required)" icon="📋" type="sop" pool={sops} selected={sopId} setSelected={setSopId}/>
            <DocPicker label="Report Template (required)" icon="📄" type="report_template" pool={tpls} selected={tplId} setSelected={setTplId}/>

            {/* Context — multi-select */}
            <div className="rounded-xl border border-dashed border-[#1e2535] p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-lg">🗂️</span>
                <span className="text-sm font-medium text-white">Context Documents</span>
                <span className="text-xs text-slate-500 ml-auto">{ctxIds.length} selected</span>
              </div>
              {ctxs.length===0?(
                <div className="text-xs text-slate-600">No context docs uploaded yet — upload them in the Documents tab</div>
              ):(
                <div className="space-y-1 max-h-36 overflow-y-auto">
                  {ctxs.map(d=>(
                    <button key={d.id} onClick={()=>setCtxIds(p=>p.includes(d.id)?p.filter(c=>c!==d.id):[...p,d.id])}
                      className={`w-full text-left flex items-center gap-2 p-2 rounded-lg border text-xs transition-colors ${ctxIds.includes(d.id)?"bg-amber-950/30 border-amber-700/40 text-amber-200":"border-[#1e2535] text-slate-400 hover:text-white hover:bg-[#1a2236]"}`}>
                      <span className="flex-1 truncate">{d.name}</span>
                      {d.is_default&&<span className="text-slate-600 flex-shrink-0">built-in</span>}
                      {ctxIds.includes(d.id)&&<CheckCircle2 size={11} className="text-amber-400 flex-shrink-0"/>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Default toggle */}
          <label className="flex items-center gap-3 cursor-pointer">
            <div onClick={()=>setDef(p=>!p)}
              className={`w-10 h-5 rounded-full transition-colors relative ${isDefault?"bg-indigo-600":"bg-[#1e2535]"}`}>
              <div className={`w-4 h-4 bg-white rounded-full absolute top-0.5 transition-transform ${isDefault?"translate-x-5":"translate-x-0.5"}`}/>
            </div>
            <div>
              <div className="text-sm text-white">Make default set for this checkout type</div>
              <div className="text-xs text-slate-500">Auto-selected when a checkout of this type has no explicit set assigned</div>
            </div>
          </label>

          <div className="flex gap-3 pt-1 border-t border-[#1e2535]">
            <button onClick={save} disabled={saving||!name||!cts.length}
              className="flex-1 py-2.5 text-sm font-medium text-white rounded-xl flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 transition-colors">
              {saving?<><Spinner/> Saving…</>:<><Package size={14}/> {editSet?"Update Set":"Create Set"}</>}
            </button>
            <button onClick={onClose} className="px-5 py-2.5 bg-[#1e2535] hover:bg-[#2a3548] text-slate-300 text-sm rounded-xl">Cancel</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main KnowledgeTab ─────────────────────────────────────────────────────────
export function KnowledgeTab({ get, post, del, isAdmin }: { get: any; post: any; del: any; isAdmin: boolean }) {
  const [view, setView]           = useState<"sets"|"docs">("sets");
  const [docs, setDocs]           = useState<KnowledgeDoc[]>([]);
  const [sets, setSets]           = useState<KnowledgeSet[]>([]);
  const [loading, setLoading]     = useState(true);
  const [filterType, setFilter]   = useState("all");
  const [previewDoc, setPreview]  = useState<KnowledgeDoc|null>(null);
  const [editDocState, setEditDoc]= useState<KnowledgeDoc|null>(null);
  const [uploadModal, setUpload]  = useState<null|"sop"|"report_template"|"context">(null);
  const [setModal, setSetModal]   = useState<null|"create"|KnowledgeSet>(null);
  const [saving, setSaving]       = useState(false);

  const load = useCallback(async () => {
    const [d, s] = await Promise.all([get("/api/v1/knowledge"), get("/api/v1/knowledge/sets/all")]);
    if (d) setDocs(d);
    if (s) setSets(s);
    setLoading(false);
  }, [get]);

  useEffect(()=>{load();},[load]);

  async function saveEdit() {
    if (!editDocState) return;
    setSaving(true);
    const r = await post(`/api/v1/knowledge/${editDocState.id}`, {
      name: editDocState.name, description: editDocState.description,
      content: editDocState.content, checkout_types: editDocState.checkout_types,
    });
    if (r?.id) { setDocs(p=>p.map(d=>d.id===r.id?r:d)); setPreview(r); setEditDoc(null); }
    setSaving(false);
  }

  async function removeDoc(id: string) {
    if (!confirm("Delete this document?")) return;
    await del(`/api/v1/knowledge/${id}`);
    setDocs(p=>p.filter(d=>d.id!==id));
    if (previewDoc?.id===id) setPreview(null);
  }

  async function removeSet(id: string) {
    if (!confirm("Delete this set?")) return;
    await del(`/api/v1/knowledge/sets/${id}`);
    setSets(p=>p.filter(s=>s.id!==id));
  }

  const filtered = docs.filter(d=>filterType==="all"||d.doc_type===filterType);

  return (
    <div className="p-6 space-y-5 overflow-y-auto h-full">

      {/* ── Header ────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <BookOpen size={18} className="text-indigo-400"/> Knowledge Base
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Group SOPs, templates &amp; context into <strong className="text-slate-300">Knowledge Sets</strong> — one set per checkout, unambiguous
          </p>
        </div>
        <div className="text-xs text-slate-600">
          {sets.length} sets · {docs.filter(d=>d.doc_type==="sop").length} SOPs · {docs.filter(d=>d.doc_type==="report_template").length} templates · {docs.filter(d=>d.doc_type==="context").length} context docs
        </div>
      </div>

      {/* ── View toggle ───────────────────────────────────────── */}
      <div className="flex gap-1 bg-[#161b27] rounded-xl p-1 w-fit border border-[#1e2535]">
        <button onClick={()=>setView("sets")}
          className={`px-4 py-2 text-sm rounded-lg transition-colors flex items-center gap-2 ${view==="sets"?"bg-indigo-600 text-white":"text-slate-400 hover:text-white"}`}>
          <Package size={14}/> Knowledge Sets
        </button>
        <button onClick={()=>setView("docs")}
          className={`px-4 py-2 text-sm rounded-lg transition-colors flex items-center gap-2 ${view==="docs"?"bg-indigo-600 text-white":"text-slate-400 hover:text-white"}`}>
          <FileText size={14}/> Documents Library
        </button>
      </div>

      {/* ══════════════════ SETS VIEW ══════════════════════════ */}
      {view==="sets"&&(
        <div className="space-y-4">
          {/* Create set button */}
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-500">
              Each checkout uses exactly one set — no ambiguity about which SOP or template applies
            </p>
            <button onClick={()=>setSetModal("create")}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-xl transition-colors">
              <Plus size={14}/> New Knowledge Set
            </button>
          </div>

          {loading ? <div className="flex items-center justify-center py-12"><Spinner/></div>
          : sets.length===0?(
            <Card className="flex flex-col items-center justify-center py-16">
              <Package size={36} className="text-slate-700 mb-3"/>
              <p className="text-slate-400 text-sm font-medium">No knowledge sets yet</p>
              <p className="text-slate-600 text-xs mt-1 mb-4">Create a set to bundle a SOP + template + context for each checkout type</p>
              <button onClick={()=>setSetModal("create")}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-xl flex items-center gap-2">
                <Plus size={14}/> Create First Set
              </button>
            </Card>
          ):(
            <div className="space-y-3">
              {sets.map(s=>(
                <Card key={s.id} className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <h3 className="text-sm font-semibold text-white">{s.name}</h3>
                        {s.is_default&&<span className="text-xs px-2 py-0.5 rounded-full bg-indigo-950/50 border border-indigo-700/40 text-indigo-300">default</span>}
                        {s.checkout_types.map(ct=>(
                          <span key={ct} className={`text-xs font-mono ${CO_COLORS[ct]||"text-slate-500"}`}>
                            {ct==="*"?"all types":ct.replace(/_/g," ")}
                          </span>
                        ))}
                      </div>
                      {s.description&&<p className="text-xs text-slate-500 mb-3">{s.description}</p>}

                      {/* Document slots */}
                      <div className="grid grid-cols-3 gap-3">
                        {/* SOP */}
                        <div className={`p-3 rounded-lg border ${s.sop_doc_id?"border-indigo-800/40 bg-indigo-950/20":"border-dashed border-[#1e2535]"}`}>
                          <div className="text-xs text-slate-500 mb-1 flex items-center gap-1">📋 SOP</div>
                          {s.sop_doc_name?(
                            <div className="text-xs font-medium text-white leading-tight">{s.sop_doc_name}</div>
                          ):(
                            <div className="text-xs text-slate-600 italic">Not set</div>
                          )}
                        </div>
                        {/* Template */}
                        <div className={`p-3 rounded-lg border ${s.template_doc_id?"border-green-800/40 bg-green-950/20":"border-dashed border-[#1e2535]"}`}>
                          <div className="text-xs text-slate-500 mb-1 flex items-center gap-1">📄 Report Template</div>
                          {s.template_doc_name?(
                            <div className="text-xs font-medium text-white leading-tight">{s.template_doc_name}</div>
                          ):(
                            <div className="text-xs text-slate-600 italic">Not set</div>
                          )}
                        </div>
                        {/* Context */}
                        <div className={`p-3 rounded-lg border ${s.context_doc_ids.length?"border-amber-800/40 bg-amber-950/20":"border-dashed border-[#1e2535]"}`}>
                          <div className="text-xs text-slate-500 mb-1 flex items-center gap-1">🗂️ Context</div>
                          {s.context_doc_names.length?(
                            <div className="space-y-0.5">
                              {s.context_doc_names.map((n,i)=><div key={i} className="text-xs text-white leading-tight">{n}</div>)}
                            </div>
                          ):(
                            <div className="text-xs text-slate-600 italic">None</div>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <button onClick={()=>setSetModal(s)}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-[#1e2535] hover:bg-[#2a3548] text-slate-300 rounded-lg">
                        <Edit3 size={11}/> Edit
                      </button>
                      <button onClick={()=>removeSet(s.id)}
                        className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-950/20 rounded-lg">
                        <Trash2 size={13}/>
                      </button>
                    </div>
                  </div>
                  <div className="text-xs text-slate-600 mt-3 pt-3 border-t border-[#1e2535]">
                    <span className="flex items-center gap-1 text-slate-500">
                      <Link size={10}/> Assign to a checkout in the <strong className="text-slate-400">Checkouts</strong> tab → checkout card → "Set"
                    </span>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ══════════════════ DOCS VIEW ══════════════════════════ */}
      {view==="docs"&&(
        <div className="space-y-4">
          {/* Upload buttons */}
          <div className="grid grid-cols-3 gap-3">
            {([
              {t:"sop"          as const,emoji:"📋",title:"Upload SOP",              btn:"bg-indigo-600 hover:bg-indigo-500"},
              {t:"report_template" as const,emoji:"📄",title:"Upload Report Template",btn:"bg-green-700 hover:bg-green-600"},
              {t:"context"      as const,emoji:"🗂️",title:"Upload Context",          btn:"bg-amber-600 hover:bg-amber-500"},
            ]).map(({t,emoji,title,btn})=>(
              <button key={t} onClick={()=>setUpload(t)}
                className={`flex items-center justify-center gap-2 py-3 text-sm font-medium text-white rounded-xl ${btn} transition-colors`}>
                <Upload size={14}/> {emoji} {title}
              </button>
            ))}
          </div>

          {/* Filter */}
          <div className="flex gap-1">
            {[{v:"all",l:`All (${docs.length})`},{v:"sop",l:`SOPs (${docs.filter(d=>d.doc_type==="sop").length})`},
              {v:"report_template",l:`Templates (${docs.filter(d=>d.doc_type==="report_template").length})`},
              {v:"context",l:`Context (${docs.filter(d=>d.doc_type==="context").length})`}].map(({v,l})=>(
              <button key={v} onClick={()=>setFilter(v)}
                className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${filterType===v?"bg-indigo-600/20 text-indigo-300 border border-indigo-600/30":"text-slate-500 hover:text-slate-200 hover:bg-[#161b27]"}`}>
                {l}
              </button>
            ))}
          </div>

          {/* Grid */}
          {loading?<div className="flex items-center justify-center py-12"><Spinner/></div>
          :filtered.length===0?(
            <Card className="flex flex-col items-center justify-center py-12">
              <FileText size={28} className="text-slate-700 mb-3"/>
              <p className="text-slate-500 text-sm">No documents yet — use the upload buttons above</p>
            </Card>
          ):(
            <div className="grid grid-cols-3 gap-3">
              {filtered.map(doc=>(
                <Card key={doc.id} onClick={()=>{setPreview(doc);setEditDoc(null);}}
                  className={`p-4 cursor-pointer hover:border-[#2a3548] transition-all ${previewDoc?.id===doc.id?"border-indigo-600/40":""}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <DocBadge type={doc.doc_type}/>
                    {doc.is_default&&<span className="text-xs text-slate-600 bg-slate-800/60 border border-slate-700 px-1.5 py-0.5 rounded">built-in</span>}
                  </div>
                  <div className="text-sm font-medium text-white leading-tight mb-1">{doc.name}</div>
                  {doc.description&&<div className="text-xs text-slate-500 line-clamp-2 mb-2">{doc.description}</div>}
                  <div className="flex flex-wrap gap-1 mb-2">
                    {doc.checkout_types?.map((ct:string)=>(
                      <span key={ct} className={`text-xs font-mono ${CO_COLORS[ct]||"text-slate-500"}`}>
                        {ct==="*"?"all types":ct.replace(/_/g," ")}
                      </span>
                    ))}
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-600">{(doc.file_size/1024).toFixed(1)} KB</span>
                    <div className="flex gap-1" onClick={e=>e.stopPropagation()}>
                      <button onClick={()=>setEditDoc({...doc})} className="p-1 text-slate-500 hover:text-indigo-400 rounded"><Edit3 size={12}/></button>
                      {!doc.is_default&&<button onClick={()=>removeDoc(doc.id)} className="p-1 text-slate-500 hover:text-red-400 rounded"><Trash2 size={12}/></button>}
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}

          {/* Preview */}
          {previewDoc&&!editDocState&&(
            <Card className="p-5">
              <div className="flex items-start justify-between gap-3 mb-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <DocBadge type={previewDoc.doc_type}/>
                    {previewDoc.is_default&&<span className="text-xs text-slate-600 bg-slate-800 border border-slate-700 px-1.5 py-0.5 rounded">built-in</span>}
                    {previewDoc.checkout_types?.map((ct:string)=>(
                      <span key={ct} className={`text-xs font-mono ${CO_COLORS[ct]||"text-slate-500"}`}>
                        {ct==="*"?"all checkout types":ct.replace(/_/g," ")}
                      </span>
                    ))}
                  </div>
                  <h2 className="text-base font-semibold text-white">{previewDoc.name}</h2>
                  {previewDoc.description&&<p className="text-xs text-slate-500 mt-0.5">{previewDoc.description}</p>}
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  <button onClick={()=>setEditDoc({...previewDoc})} className="flex items-center gap-1 px-3 py-1.5 text-xs bg-[#1e2535] hover:bg-[#2a3548] text-slate-300 rounded-lg">
                    <Edit3 size={11}/> Edit
                  </button>
                  <button onClick={()=>setPreview(null)} className="p-1.5 text-slate-500 hover:text-white"><X size={16}/></button>
                </div>
              </div>
              <div className="bg-[#0b0e16] border border-[#1e2535] rounded-xl p-4 max-h-[55vh] overflow-y-auto">
                <div className="prose-ops text-sm"><ReactMarkdown>{previewDoc.content}</ReactMarkdown></div>
              </div>
            </Card>
          )}

          {/* Edit */}
          {editDocState&&(
            <Card className="p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Edit3 size={14} className="text-indigo-400"/> Editing: {editDocState.name}</h2>
                <button onClick={()=>setEditDoc(null)} className="text-slate-500 hover:text-white"><X size={16}/></button>
              </div>
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <label className="text-xs text-slate-400 block mb-1">Name</label>
                  <input value={editDocState.name} onChange={e=>setEditDoc(p=>({...p!,name:e.target.value}))}
                    className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50"/>
                </div>
                <div>
                  <label className="text-xs text-slate-400 block mb-1">Description</label>
                  <input value={editDocState.description} onChange={e=>setEditDoc(p=>({...p!,description:e.target.value}))}
                    className="w-full bg-[#0f1117] border border-[#1e2535] text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-600/50"/>
                </div>
              </div>
              <textarea value={editDocState.content} onChange={e=>setEditDoc(p=>({...p!,content:e.target.value}))}
                rows={22} className="w-full bg-[#0b0e16] border border-[#1e2535] text-slate-300 text-xs font-mono p-3 rounded-xl outline-none resize-none focus:border-indigo-600/50"/>
              <div className="flex gap-2 mt-3">
                <button onClick={saveEdit} disabled={saving}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-lg flex items-center gap-2">
                  {saving?<><Spinner/> Saving…</>:"Save Changes"}
                </button>
                <button onClick={()=>setEditDoc(null)} className="px-4 py-2 bg-[#1e2535] hover:bg-[#2a3548] text-slate-300 text-sm rounded-lg">Cancel</button>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ── Modals ────────────────────────────────────────────── */}
      {uploadModal&&(
        <UploadModal
          docType={uploadModal}
          post={post}
          onClose={()=>setUpload(null)}
          onSave={d=>{setDocs(p=>[d,...p]);}}
        />
      )}
      {setModal&&(
        <SetBuilderModal
          docs={docs}
          editSet={setModal==="create"?null:setModal}
          post={post}
          onClose={()=>setSetModal(null)}
          onSave={s=>{
            setSets(p=>setModal==="create"?[s,...p]:p.map(x=>x.id===s.id?s:x));
          }}
        />
      )}
    </div>
  );
}

"use client";

/** Home — one interaction. A person arrives with work: they type one
 * sentence, choose how intelligent the run should be, and press Run.
 * Everything else — approvals waiting, work in motion, the recent
 * record, pinned roles, suggestions the workforce derived from its own
 * history — reveals itself below, and only when it actually exists.
 * The architecture stays behind the curtain until Run is pressed. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, ArrowUpRight, ChevronDown, CornerDownLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  ApiApproval,
  ApiAttentionItem,
  ApiIntelligenceFinding,
  ApiModelProvider,
  ApiWorkflow,
  DashboardStats,
  ackAttention,
  decideApproval,
  getApprovals,
  getAttention,
  getDashboardStats,
  getIntelligenceBriefing,
  getModels,
  getWorkflows,
} from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [approvals, setApprovals] = useState<ApiApproval[]>([]);
  const [attention, setAttention] = useState<ApiAttentionItem[]>([]);
  const [workflows, setWorkflows] = useState<ApiWorkflow[]>([]);
  const [suggestions, setSuggestions] = useState<ApiIntelligenceFinding[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (signal?: AbortSignal) => {
    const [s, ap, at, wf, br] = await Promise.allSettled([
      getDashboardStats(signal),
      getApprovals("pending", signal),
      getAttention("open", signal),
      getWorkflows(signal),
      getIntelligenceBriefing(signal),
    ]);
    if (s.status === "rejected" && String(s.reason).includes("Unauthorized")) {
      router.replace("/signin");
      return;
    }
    if (s.status === "fulfilled") setStats(s.value);
    if (ap.status === "fulfilled") setApprovals(ap.value);
    if (at.status === "fulfilled") setAttention(at.value);
    if (wf.status === "fulfilled") setWorkflows(wf.value);
    if (br.status === "fulfilled") {
      setSuggestions(br.value.findings.filter(
        (f) => f.kind === "automation_opportunity" || f.kind === "approval_friction").slice(0, 3));
    }
  }, [router]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).finally(() => setLoading(false));
    const id = setInterval(() => load(), 25_000);
    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, [load]);

  const recent = stats?.recent_sessions ?? [];
  const running = recent.filter((s) => s.status === "running");
  const pinned = workflows.filter((w) => w.status === "published").slice(0, 4);

  return (
    <div className="mx-auto max-w-2xl">
      <header className="pt-14 pb-8 text-center">
        <h1 className="text-[26px] font-semibold tracking-tight text-white leading-tight">
          {greeting()}<Name />
        </h1>
        <p className="mt-2 text-[14px] text-white/40">
          What would you like your workforce to accomplish?
        </p>
      </header>

      <CommandBox onRun={(payload) => {
        try {
          window.localStorage.setItem("perceptai_pending_run", JSON.stringify(payload));
        } catch { /* run page falls back to manual */ }
        router.push("/dashboard/run");
      }} />

      <div className="space-y-10 pt-12 pb-16">
        {(approvals.length > 0 || attention.length > 0) && (
          <NeedsYou attention={attention} approvals={approvals} onChanged={() => load()} />
        )}

        {running.length > 0 && (
          <section>
            <SectionLabel>In motion</SectionLabel>
            <div className="mt-3 space-y-1">
              {running.map((s) => (
                <Link key={s.id} href={`/dashboard/sessions/${s.id}`}
                      className="group flex items-center gap-3 rounded-lg px-3 -mx-3 py-2.5 hover:bg-white/[0.02] transition-colors">
                  <span className="h-1.5 w-1.5 rounded-full bg-sky-300 animate-pulse shrink-0" />
                  <span className="flex-1 min-w-0 truncate text-[13.5px] text-white/80">{s.instruction}</span>
                  <span className="font-mono text-[10.5px] text-sky-300/70 shrink-0">watch</span>
                </Link>
              ))}
            </div>
          </section>
        )}

        {recent.filter((s) => s.status !== "running").length > 0 && (
          <section>
            <div className="flex items-baseline justify-between">
              <SectionLabel>Recent operations</SectionLabel>
              <Link href="/dashboard/operations"
                    className="text-[12px] text-white/30 hover:text-accent transition-colors">
                All <ArrowRight size={11} className="inline" />
              </Link>
            </div>
            <div className="mt-3 space-y-0.5">
              {recent.filter((s) => s.status !== "running").slice(0, 5).map((s) => (
                <Link key={s.id} href={`/dashboard/sessions/${s.id}`}
                      className="group flex items-center gap-3 rounded-lg px-3 -mx-3 py-2 hover:bg-white/[0.02] transition-colors">
                  <OutcomeWord status={s.status} />
                  <span className="flex-1 min-w-0 truncate text-[13.5px] text-white/65 group-hover:text-white/90">
                    {s.instruction}
                  </span>
                  <span className="font-mono text-[10.5px] text-white/25 shrink-0">{timeAgo(s.created_at)}</span>
                </Link>
              ))}
            </div>
          </section>
        )}

        {pinned.length > 0 && (
          <section>
            <SectionLabel>Standing roles</SectionLabel>
            <div className="mt-3 space-y-0.5">
              {pinned.map((w) => (
                <Link key={w.id} href={`/dashboard/studio/${w.id}`}
                      className="group flex items-center gap-3 rounded-lg px-3 -mx-3 py-2 hover:bg-white/[0.02] transition-colors">
                  <span className="h-1.5 w-1.5 rounded-full bg-accent/60 shrink-0" />
                  <span className="flex-1 min-w-0 truncate text-[13.5px] text-white/65 group-hover:text-white/90">
                    {w.name}
                  </span>
                  <span className="font-mono text-[10px] text-white/25 shrink-0">run <ArrowUpRight size={10} className="inline" /></span>
                </Link>
              ))}
            </div>
          </section>
        )}

        {suggestions.length > 0 && (
          <section>
            <SectionLabel>Suggested by your workforce</SectionLabel>
            <div className="mt-3 space-y-3">
              {suggestions.map((f, i) => (
                <div key={i} className="flex gap-3">
                  <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-amber-300/80 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-[13px] text-white/75">{f.headline}</p>
                    <p className="mt-0.5 text-[12px] leading-relaxed text-white/40">{f.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {!loading && recent.length === 0 && pinned.length === 0 && (
          <p className="text-center text-[12.5px] text-white/30">
            First time? Try a proven brief from the{" "}
            <Link href="/dashboard/templates" className="text-accent/80 hover:text-accent">
              business templates
            </Link>{" "}
            — or just describe the work above.
          </p>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------- command box */

const EXEC_MODES = [
  { value: "balanced", label: "Balanced", hint: "the default" },
  { value: "fast", label: "Fast", hint: "fewer retries, quickest" },
  { value: "max_reliability", label: "Maximum reliability", hint: "deepest verification effort" },
  { value: "private", label: "Private", hint: "screenshots never leave this machine" },
];
const TARGETS = [
  { value: "local", label: "This machine", hint: "runs on this desktop" },
  { value: "runner", label: "A runner", hint: "runs on your fleet" },
];

interface RunPayload {
  instruction: string; mode: "task"; target: string;
  model: string; exec_mode: string; autostart: boolean;
}

function CommandBox({ onRun }: { onRun: (payload: RunPayload) => void }) {
  const [brief, setBrief] = useState("");
  const [model, setModel] = useState("auto");
  const [execMode, setExecMode] = useState("balanced");
  const [target, setTarget] = useState("local");
  const [providers, setProviders] = useState<ApiModelProvider[]>([]);
  const [activeProvider, setActiveProvider] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // The picker is real: only providers actually configured are offered,
  // each with its capability metadata. Auto shows what it routes to.
  useEffect(() => {
    getModels().then((r) => {
      setProviders(r.providers);
      setActiveProvider(r.active_provider);
    }).catch(() => { /* picker falls back to Auto only */ });
  }, []);

  const modelOptions = useMemo(() => {
    const auto = {
      value: "auto", label: "Auto",
      hint: activeProvider ? `routes to ${activeProvider}` : "best available",
    };
    const configured = providers
      .filter((p) => p.available)
      .map((p) => {
        const top = p.models[0];
        return {
          value: p.picker_value,
          label: p.label,
          hint: top ? `reasoning ${top.reasoning}/5 · ${top.latency_tier} · ${top.cost_tier}` : "",
        };
      });
    return [auto, ...configured];
  }, [providers, activeProvider]);

  useEffect(() => {
    if (!ref.current) return;
    ref.current.style.height = "auto";
    ref.current.style.height = `${Math.min(ref.current.scrollHeight, 200)}px`;
  }, [brief]);

  const run = () => {
    const instruction = brief.trim();
    if (!instruction) return;
    onRun({ instruction, mode: "task", target, model,
            exec_mode: execMode, autostart: target === "local" });
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35 }}
                className="rounded-2xl border border-white/[0.09] bg-white/[0.025] focus-within:border-accent/30 transition-colors shadow-[0_8px_40px_-16px_rgba(0,0,0,0.8)]">
      <textarea
        ref={ref}
        value={brief}
        onChange={(e) => setBrief(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); run(); }
        }}
        placeholder="Post today's pending invoices in the ERP and report the document numbers…"
        rows={2}
        autoFocus
        data-testid="home-brief"
        className="w-full resize-none bg-transparent px-5 pt-5 pb-2 text-[15.5px] leading-relaxed text-white placeholder:text-white/25 focus:outline-none"
      />
      <div className="flex flex-wrap items-center gap-2 px-3.5 pb-3.5 pt-1">
        <Picker value={model} onChange={setModel} options={modelOptions} />
        <Picker value={execMode} onChange={setExecMode} options={EXEC_MODES} />
        <Picker value={target} onChange={setTarget} options={TARGETS} />
        <button
          onClick={run}
          disabled={!brief.trim()}
          data-testid="home-run"
          className="ml-auto inline-flex items-center gap-2 rounded-lg bg-accent px-4 h-9 text-[13.5px] font-medium text-black transition-all hover:bg-accent/90 disabled:opacity-35 disabled:cursor-not-allowed"
        >
          Run <CornerDownLeft size={13} className="opacity-60" />
        </button>
      </div>
    </motion.div>
  );
}

/** A quiet select: native accessibility, custom skin. */
function Picker({ value, onChange, options }: {
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string; hint: string }>;
}) {
  const current = options.find((o) => o.value === value) ?? options[0];
  return (
    <label className="relative inline-flex items-center gap-1.5 rounded-lg border border-white/[0.07] bg-white/[0.02] h-9 pl-3 pr-8 text-[12.5px] text-white/65 hover:text-white hover:border-white/[0.15] transition-colors cursor-pointer"
           title={current.hint}>
      {current.label}
      <ChevronDown size={12} className="absolute right-2.5 text-white/30 pointer-events-none" />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="absolute inset-0 opacity-0 cursor-pointer"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} className="bg-[#111] text-white">
            {o.label} — {o.hint}
          </option>
        ))}
      </select>
    </label>
  );
}

/* ---------------------------------------------------------- needs you */

function NeedsYou({ attention, approvals, onChanged }: {
  attention: ApiAttentionItem[]; approvals: ApiApproval[]; onChanged: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const decide = async (id: string, decision: "approved" | "denied") => {
    setBusy(id);
    try { await decideApproval(id, decision); onChanged(); } catch { /* refresh keeps it honest */ }
    finally { setBusy(null); }
  };
  const ack = async (id: string) => {
    setBusy(id);
    try { await ackAttention(id); onChanged(); } catch { /* stays open */ }
    finally { setBusy(null); }
  };

  return (
    <section>
      <SectionLabel>Needs your judgment</SectionLabel>
      <div className="mt-3 space-y-2.5">
        {approvals.slice(0, 3).map((a) => (
          <div key={a.id} className="rounded-xl border border-amber-300/15 bg-amber-300/[0.03] px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-amber-300/90">
                approval · {a.capability}
              </span>
              <span className="font-mono text-[10px] text-white/30">{timeAgo(a.created_at)}</span>
            </div>
            <p className="mt-1.5 text-[13px] text-white/80 leading-snug">{a.objective}</p>
            <div className="mt-2.5 flex gap-2">
              <button onClick={() => decide(a.id, "approved")} disabled={busy === a.id}
                      className="rounded-md bg-accent/15 px-3 h-7 text-[12px] font-medium text-accent hover:bg-accent/25 transition-colors disabled:opacity-50">
                Approve
              </button>
              <button onClick={() => decide(a.id, "denied")} disabled={busy === a.id}
                      className="rounded-md bg-white/[0.04] px-3 h-7 text-[12px] text-white/55 hover:text-red-300 hover:bg-red-400/10 transition-colors disabled:opacity-50">
                Reject
              </button>
              <Link href="/dashboard/approvals"
                    className="ml-auto self-center text-[12px] text-white/35 hover:text-white transition-colors">
                Review <ArrowUpRight size={11} className="inline" />
              </Link>
            </div>
          </div>
        ))}
        {attention.slice(0, 3).map((item) => {
          const href = item.session_id ? `/dashboard/sessions/${item.session_id}` : null;
          const grave = item.kind === "run_failed" || item.kind === "dead_letter";
          return (
            <div key={item.id}
                 className={cn("rounded-xl border px-4 py-3",
                   grave ? "border-red-400/15 bg-red-400/[0.03]" : "border-amber-300/15 bg-amber-300/[0.03]")}>
              <div className="flex items-center justify-between gap-3">
                <span className={cn("font-mono text-[10px] uppercase tracking-[0.14em]",
                                    grave ? "text-red-300/90" : "text-amber-300/90")}>
                  {item.kind.replace(/_/g, " ")}
                </span>
                <span className="font-mono text-[10px] text-white/30">{timeAgo(item.created_at)}</span>
              </div>
              <p className="mt-1.5 text-[13px] text-white/80 leading-snug">{item.title}</p>
              <div className="mt-2 flex items-center gap-3">
                {href && (
                  <Link href={href} className="text-[12px] text-white/50 hover:text-accent transition-colors">
                    Inspect <ArrowUpRight size={11} className="inline" />
                  </Link>
                )}
                <button onClick={() => ack(item.id)} disabled={busy === item.id}
                        className="ml-auto text-[12px] text-white/35 hover:text-white transition-colors disabled:opacity-50">
                  Dismiss
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- shared */

function OutcomeWord({ status }: { status: string }) {
  const map: Record<string, { word: string; cls: string }> = {
    completed: { word: "Verified", cls: "text-accent" },
    unverified: { word: "Review", cls: "text-amber-300" },
    partial: { word: "Partial", cls: "text-amber-300" },
    failed: { word: "Failed", cls: "text-red-300" },
    running: { word: "Working", cls: "text-sky-300" },
  };
  const m = map[status] ?? { word: status, cls: "text-white/40" };
  return (
    <span className={cn("w-14 shrink-0 font-mono text-[9.5px] uppercase tracking-[0.12em]", m.cls)}>
      {m.word}
    </span>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/30">{children}</h2>;
}

function Name() {
  const [name, setName] = useState<string | null>(null);
  useEffect(() => {
    try {
      const token = window.localStorage.getItem("perceptai_token");
      if (!token) return;
      const payload = JSON.parse(atob(token.split(".")[1]
        .replace(/-/g, "+").replace(/_/g, "/")
        .padEnd(Math.ceil(token.split(".")[1].length / 4) * 4, "=")));
      const email = String(payload?.email ?? "");
      const first = email.split("@")[0]?.split(/[._-]/)[0];
      if (first) setName(first[0].toUpperCase() + first.slice(1));
    } catch { /* greeting stays generic */ }
  }, []);
  return name ? <>, {name}.</> : <>.</>;
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Working late";
  if (h < 12) return "Morning";
  if (h < 18) return "Afternoon";
  return "Evening";
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, (Date.now() - then) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

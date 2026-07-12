"use client";

/** Today — the Morning Brief. The page doesn't ask what you want to do;
 * it already knows what your workforce did, what it's doing, and what
 * needs your judgment. Every number is computed from real rows — when
 * there is no history yet, the page says so and shows the first hire. */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  AnalyticsSummary,
  ApiApproval,
  ApiAttentionItem,
  ApiFleetAutonomy,
  DashboardStats,
  PlatformHealth,
  ackAttention,
  decideApproval,
  getAnalyticsSummary,
  getApprovals,
  getAttention,
  getDashboardStats,
  getFleetAutonomy,
  getPlatformHealth,
} from "@/lib/api";

interface BriefData {
  summary: AnalyticsSummary | null;
  stats: DashboardStats | null;
  approvals: ApiApproval[];
  attention: ApiAttentionItem[];
  autonomy: ApiFleetAutonomy | null;
  health: PlatformHealth | null;
}

export default function TodayPage() {
  const router = useRouter();
  const [data, setData] = useState<BriefData | null>(null);
  const [loading, setLoading] = useState(true);
  const [unauthorized, setUnauthorized] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    const [summary, stats, approvals, attention, autonomy, health] =
      await Promise.allSettled([
        getAnalyticsSummary("7d", "all", signal),
        getDashboardStats(signal),
        getApprovals("pending", signal),
        getAttention("open", signal),
        getFleetAutonomy(signal),
        getPlatformHealth(signal),
      ]);
    if (stats.status === "rejected" && String(stats.reason).includes("Unauthorized")) {
      setUnauthorized(true);
      return;
    }
    setData({
      summary: settled(summary, null),
      stats: settled(stats, null),
      approvals: settled(approvals, [] as ApiApproval[]),
      attention: settled(attention, [] as ApiAttentionItem[]),
      autonomy: settled(autonomy, null),
      health: settled(health, null),
    });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).finally(() => setLoading(false));
    const id = setInterval(() => load(), 20_000);
    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, [load]);

  useEffect(() => {
    if (unauthorized) router.replace("/signin");
  }, [unauthorized, router]);

  if (loading || !data) return <BriefSkeleton />;

  const { summary, stats, approvals, attention, autonomy, health } = data;
  const totals = summary?.totals;
  const recent = stats?.recent_sessions ?? [];
  const running = recent.filter((s) => s.status === "running");
  const hasHistory = (totals?.runs ?? 0) > 0 || recent.length > 0;

  return (
    <div className="mx-auto max-w-3xl">
      {/* Greeting — typography does the work */}
      <header className="pt-6 pb-10">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[28px] font-semibold tracking-tight text-white leading-tight">
              {greeting()}<Name />
            </h1>
            <p className="mt-1.5 text-[13px] text-white/40">
              {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
            </p>
          </div>
          <HealthQuiet health={health} />
        </div>
      </header>

      {!hasHistory ? (
        <FirstHire />
      ) : (
        <div className="space-y-12 pb-16">
          <TheBrief totals={totals} autonomy={autonomy}
                    needsYou={attention.length + approvals.length} summary={summary} />
          <NeedsYou attention={attention} approvals={approvals} onChanged={() => load()} />
          {running.length > 0 && <InMotion running={running} />}
          <TheRecord recent={recent.filter((s) => s.status !== "running").slice(0, 6)} />
          <Standing autonomy={autonomy} />
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- the brief */

function TheBrief({ totals, autonomy, needsYou, summary }: {
  totals: AnalyticsSummary["totals"] | undefined;
  autonomy: ApiFleetAutonomy | null;
  needsYou: number;
  summary: AnalyticsSummary | null;
}) {
  const lines: Array<{ text: React.ReactNode; key: string }> = [];
  if (totals && totals.runs > 0) {
    lines.push({
      key: "ops",
      text: (
        <>completed <Strong>{totals.succeeded}</Strong> verified operation{totals.succeeded === 1 ? "" : "s"}
          {totals.needs_attention > 0 && <> and flagged <Strong tone="amber">{totals.needs_attention}</Strong> for review</>}
          {totals.failed > 0 && <>, with <Strong tone="red">{totals.failed}</Strong> failed</>}</>
      ),
    });
  }
  const earned = autonomy?.earned_autonomy ?? 0;
  if ((autonomy?.graded_workflows ?? 0) > 0) {
    lines.push({
      key: "autonomy",
      text: earned > 0
        ? <>has <Strong>{earned}</Strong> workflow{earned === 1 ? "" : "s"} that earned the right to run unattended</>
        : <>is still earning autonomy — every run adds verified evidence</>,
    });
  }
  const topFailure = summary?.failures?.[0];
  if (topFailure && topFailure.count > 0) {
    lines.push({
      key: "failure",
      text: <>most common obstacle: <Strong tone="amber">{topFailure.label.toLowerCase()}</Strong> ({topFailure.count}×)</>,
    });
  }
  lines.push({
    key: "needs",
    text: needsYou > 0
      ? <>needs your judgment on <Strong tone="amber">{needsYou}</Strong> item{needsYou === 1 ? "" : "s"} below</>
      : <>needs nothing from you right now</>,
  });

  return (
    <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <SectionLabel>This week, your workforce</SectionLabel>
      <ul className="mt-4 space-y-3">
        {lines.map((l) => (
          <li key={l.key} className="flex gap-3 text-[15px] leading-relaxed text-white/75">
            <span className="mt-[11px] h-1 w-1 rounded-full bg-white/25 shrink-0" />
            <span>{l.text}</span>
          </li>
        ))}
      </ul>
    </motion.section>
  );
}

function Strong({ children, tone }: { children: React.ReactNode; tone?: "amber" | "red" }) {
  return (
    <span className={cn("font-semibold tabular-nums",
      tone === "amber" ? "text-amber-300" : tone === "red" ? "text-red-300" : "text-white")}>
      {children}
    </span>
  );
}

/* --------------------------------------------------------- needs you */

function NeedsYou({ attention, approvals, onChanged }: {
  attention: ApiAttentionItem[]; approvals: ApiApproval[]; onChanged: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  if (attention.length === 0 && approvals.length === 0) return null;

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
      <div className="mt-4 space-y-2.5">
        {approvals.slice(0, 4).map((a) => (
          <div key={a.id} className="rounded-xl border border-amber-300/15 bg-amber-300/[0.03] px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-amber-300/90">
                approval · {a.capability}
              </span>
              <span className="font-mono text-[10px] text-white/30">{timeAgo(a.created_at)}</span>
            </div>
            <p className="mt-1.5 text-[13.5px] text-white/80 leading-snug">{a.objective}</p>
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
                Context <ArrowUpRight size={11} className="inline" />
              </Link>
            </div>
          </div>
        ))}
        {attention.slice(0, 4).map((item) => {
          const href = item.session_id
            ? `/dashboard/sessions/${item.session_id}`
            : item.workflow_id ? `/dashboard/studio/${item.workflow_id}` : null;
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
              <p className="mt-1.5 text-[13.5px] text-white/80 leading-snug">{item.title}</p>
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

/* --------------------------------------------------------- in motion */

function InMotion({ running }: { running: DashboardStats["recent_sessions"] }) {
  return (
    <section>
      <SectionLabel>In motion</SectionLabel>
      <div className="mt-4 space-y-1">
        {running.map((s) => (
          <Link key={s.id} href={`/dashboard/sessions/${s.id}`}
                className="group flex items-center gap-3 rounded-lg px-3 -mx-3 py-2.5 hover:bg-white/[0.02] transition-colors">
            <span className="h-1.5 w-1.5 rounded-full bg-sky-300 animate-pulse shrink-0" />
            <span className="flex-1 min-w-0 truncate text-[14px] text-white/80 group-hover:text-white">
              {s.instruction}
            </span>
            <span className="font-mono text-[11px] text-sky-300/70 shrink-0">watch</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

/* --------------------------------------------------------- the record */

function TheRecord({ recent }: { recent: DashboardStats["recent_sessions"] }) {
  if (recent.length === 0) return null;
  return (
    <section>
      <div className="flex items-baseline justify-between">
        <SectionLabel>The record</SectionLabel>
        <Link href="/dashboard/operations"
              className="text-[12px] text-white/35 hover:text-accent transition-colors">
          All operations <ArrowRight size={11} className="inline" />
        </Link>
      </div>
      <div className="mt-4 space-y-1">
        {recent.map((s) => (
          <Link key={s.id} href={`/dashboard/sessions/${s.id}`}
                className="group flex items-center gap-3 rounded-lg px-3 -mx-3 py-2.5 hover:bg-white/[0.02] transition-colors">
            <OutcomeWord status={s.status} />
            <span className="flex-1 min-w-0 truncate text-[14px] text-white/70 group-hover:text-white">
              {s.instruction}
            </span>
            <span className="font-mono text-[11px] text-white/25 shrink-0">{timeAgo(s.created_at)}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

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
    <span className={cn("w-16 shrink-0 font-mono text-[10px] uppercase tracking-[0.12em]", m.cls)}>
      {m.word}
    </span>
  );
}

/* ------------------------------------------------------------ standing */

function Standing({ autonomy }: { autonomy: ApiFleetAutonomy | null }) {
  if (!autonomy || autonomy.graded_workflows === 0) return null;
  const pct = autonomy.fleet_verified_success_rate != null
    ? Math.round(autonomy.fleet_verified_success_rate * 100) : null;
  return (
    <section className="border-t border-white/[0.05] pt-8">
      <p className="text-[13.5px] leading-relaxed text-white/50 max-w-xl">
        Across <span className="text-white/80">{autonomy.total_runs}</span> operations,{" "}
        {pct != null && <><span className="text-white/80">{pct}%</span> finished with verified evidence. </>}
        <span className="text-white/80">{autonomy.earned_autonomy}</span> of{" "}
        <span className="text-white/80">{autonomy.graded_workflows}</span> graded workflows
        have earned unattended autonomy.{" "}
        <Link href="/dashboard/answers" className="text-accent/80 hover:text-accent">
          See what&apos;s improving <ArrowRight size={11} className="inline" />
        </Link>
      </p>
    </section>
  );
}

/* ------------------------------------------------------------ first hire */

function FirstHire() {
  return (
    <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4 }} className="pb-16">
      <p className="text-[15px] leading-relaxed text-white/60 max-w-xl">
        Your workforce hasn&apos;t taken on any work yet. Hire it for its first role —
        pick the business process you already do by hand, and PerceptAI will do it,
        verify the outcome, and show you the evidence.
      </p>
      <div className="mt-8 flex flex-wrap items-center gap-4">
        <Link href="/dashboard/templates"
              className="inline-flex items-center gap-2 rounded-lg bg-accent text-black px-5 h-11 text-[14px] font-medium hover:shadow-[0_0_40px_-8px_rgba(0,255,133,0.6)] transition-shadow">
          Browse business templates <ArrowRight size={15} />
        </Link>
        <Link href="/dashboard/run" className="text-[13px] text-white/45 hover:text-white transition-colors">
          or brief it in your own words
        </Link>
      </div>
      <div className="mt-12 grid grid-cols-1 sm:grid-cols-3 gap-8 max-w-2xl">
        {[
          { t: "Describe the outcome", b: "Plain English. No scripts, no node editors." },
          { t: "It works, you watch", b: "Every action grounded on the live screen, with reasons." },
          { t: "Proof, not promises", b: "Outcomes verified with evidence you can audit." },
        ].map((s) => (
          <div key={s.t}>
            <div className="text-[13px] text-white/80">{s.t}</div>
            <p className="mt-1 text-[12px] leading-relaxed text-white/40">{s.b}</p>
          </div>
        ))}
      </div>
    </motion.section>
  );
}

/* ------------------------------------------------------------ chrome */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">{children}</h2>
  );
}

function HealthQuiet({ health }: { health: PlatformHealth | null }) {
  const ok = health != null && health.database && health.engine;
  return (
    <div className="flex items-center gap-1.5 pt-2" title={health?.engine_reason || undefined}>
      <span className={cn("h-1.5 w-1.5 rounded-full", ok ? "bg-accent" : "bg-red-400")} />
      <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-white/30">
        {ok ? "workforce online" : "degraded"}
      </span>
    </div>
  );
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
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function settled<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

function BriefSkeleton() {
  return (
    <div className="mx-auto max-w-3xl animate-pulse">
      <div className="pt-6 pb-10">
        <div className="h-8 w-72 rounded-lg bg-white/[0.04]" />
        <div className="mt-2 h-4 w-40 rounded bg-white/[0.03]" />
      </div>
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-5 w-full max-w-lg rounded bg-white/[0.03]" />
        ))}
      </div>
      <div className="mt-12 h-40 rounded-xl bg-white/[0.03]" />
    </div>
  );
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, (Date.now() - then) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

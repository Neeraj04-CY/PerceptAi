"use client";

/** Mission Control: the operational command center. One screen answers
 * what is running, what finished, what failed, what needs approval, what
 * was produced, and whether this host can execute at all. */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  BadgeCheck,
  BellRing,
  CalendarClock,
  CheckCircle2,
  FileText,
  Gauge,
  PlayCircle,
  Server,
  ShieldAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/dashboard/page-header";
import {
  ApiApproval,
  ApiAttentionItem,
  ApiFleetAutonomy,
  ApiMission,
  ApiRunner,
  ApiTemplate,
  ApiWorkflow,
  AutonomyTier,
  DashboardStats,
  PlatformHealth,
  ackAttention,
  decideApproval,
  getApprovals,
  getAttention,
  getDashboardStats,
  getFleetAutonomy,
  getMissions,
  getPlatformHealth,
  getRunners,
  getTemplates,
  getWorkflows,
} from "@/lib/api";

interface ControlData {
  stats: DashboardStats | null;
  missions: ApiMission[];
  approvals: ApiApproval[];
  attention: ApiAttentionItem[];
  health: PlatformHealth | null;
  runners: ApiRunner[];
  autonomy: ApiFleetAutonomy | null;
  workflows: ApiWorkflow[];
  templates: ApiTemplate[];
}

export default function MissionControlPage() {
  const router = useRouter();
  const [data, setData] = useState<ControlData | null>(null);
  const [loading, setLoading] = useState(true);
  const [unauthorized, setUnauthorized] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    const [stats, missions, approvals, attention, health,
           runners, autonomy, workflows, templates] =
      await Promise.allSettled([
        getDashboardStats(signal),
        getMissions(10, signal),
        getApprovals("pending", signal),
        getAttention("open", signal),
        getPlatformHealth(signal),
        getRunners(signal),
        getFleetAutonomy(signal),
        getWorkflows(signal),
        getTemplates(signal),
      ]);
    if (stats.status === "rejected" && String(stats.reason).includes("Unauthorized")) {
      setUnauthorized(true);
      return;
    }
    setData({
      stats: settled(stats, null),
      missions: settled(missions, [] as ApiMission[]),
      approvals: settled(approvals, [] as ApiApproval[]),
      attention: settled(attention, [] as ApiAttentionItem[]),
      health: settled(health, null),
      runners: settled(runners, [] as ApiRunner[]),
      autonomy: settled(autonomy, null),
      workflows: settled(workflows, [] as ApiWorkflow[]),
      templates: settled(templates, [] as ApiTemplate[]),
    });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).finally(() => setLoading(false));
    const id = setInterval(() => load(), 15_000);
    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, [load]);

  useEffect(() => {
    if (unauthorized) router.replace("/signin");
  }, [unauthorized, router]);

  if (loading || !data) return <ControlSkeleton />;

  const { stats, missions, approvals, attention, health,
          runners, autonomy, workflows, templates } = data;
  const recentSessions = stats?.recent_sessions ?? [];
  const runningMissions = missions.filter((m) => m.status === "running");
  const runningSessions = recentSessions.filter((s) => s.status === "running");
  const available = runners.filter((r) => r.status === "online" || r.status === "busy").length;
  const scheduled = workflows.filter((w) => w.schedule?.enabled).length;
  const firstRun = recentSessions.length === 0 && missions.length === 0 && runners.length === 0;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Operations"
        subtitle="Your autonomous workforce, at a glance — what's running, what needs you, and what you can trust."
        actions={<HealthStrip health={health} />}
      />

      {/* THE PULSE — the vitals line you read from across the room */}
      <PulseBar
        running={runningMissions.length + runningSessions.length}
        needsYou={attention.length + approvals.length}
        runnersAvailable={available}
        runnersTotal={runners.length}
        autonomy={autonomy}
        verifiedToday={stats?.successful_sessions ?? 0}
        failedToday={stats?.failed_sessions ?? 0}
      />

      {firstRun ? (
        <FirstRun templates={templates} />
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[1.55fr_1fr] gap-4 items-start">
          {/* ACT + WATCH */}
          <div className="space-y-4">
            <AttentionPanel items={attention} onAcked={() => load()} />
            <ApprovalsPanel approvals={approvals} onDecided={() => load()} />
            <InFlight missions={runningMissions} sessions={runningSessions}
                      recentSessions={recentSessions} recentMissions={missions} />
          </div>

          {/* TRUST + PLAN */}
          <div className="space-y-4">
            <AutonomyPosture autonomy={autonomy} />
            <FleetCapacity runners={runners} health={health} scheduled={scheduled} />
            <ComingUp workflows={workflows} autonomy={autonomy} />
          </div>
        </div>
      )}
    </div>
  );
}

/* ======================================================= the pulse ======= */

function PulseBar({ running, needsYou, runnersAvailable, runnersTotal, autonomy,
                    verifiedToday, failedToday }: {
  running: number; needsYou: number; runnersAvailable: number; runnersTotal: number;
  autonomy: ApiFleetAutonomy | null; verifiedToday: number; failedToday: number;
}) {
  const earned = autonomy?.earned_autonomy ?? 0;
  const graded = autonomy?.graded_workflows ?? 0;
  const liars = autonomy?.confident_liars.length ?? 0;
  const cells: Array<{ icon: React.ReactNode; value: string; label: string; tone: string }> = [
    { icon: <Activity size={14} />, value: String(running), tone: running ? "text-sky-300" : "text-white/70",
      label: running === 1 ? "running now" : "running now" },
    { icon: <BellRing size={14} />, value: String(needsYou), tone: needsYou ? "text-amber-300" : "text-accent",
      label: needsYou ? "need you" : "all handled" },
    { icon: <Server size={14} />, value: `${runnersAvailable}/${runnersTotal}`,
      tone: runnersTotal === 0 ? "text-white/40" : runnersAvailable < runnersTotal ? "text-amber-300" : "text-accent",
      label: "fleet ready" },
    { icon: <CheckCircle2 size={14} />, value: String(verifiedToday), tone: "text-accent",
      label: failedToday ? `verified · ${failedToday} failed` : "verified recently" },
    { icon: <BadgeCheck size={14} />, value: graded ? `${earned}/${graded}` : "—", tone: earned ? "text-accent" : "text-white/60",
      label: liars ? `earned autonomy · ${liars} to watch` : "workflows earned autonomy" },
  ];
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
                className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {cells.map((c, i) => (
        <div key={i} className="glass rounded-xl px-4 py-3">
          <div className={cn("flex items-center gap-2", c.tone)}>{c.icon}
            <span className="text-[22px] font-semibold tabular-nums leading-none">{c.value}</span>
          </div>
          <div className="mt-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-white/35">{c.label}</div>
        </div>
      ))}
    </motion.div>
  );
}

/* ============================================= autonomy posture (TRUST) === */

const TIER_META: Record<AutonomyTier, { label: string; fg: string; dot: string }> = {
  ready: { label: "Earned autonomy", fg: "text-accent", dot: "bg-accent" },
  supervised: { label: "Supervised", fg: "text-amber-300", dot: "bg-amber-300" },
  in_the_loop: { label: "In the loop", fg: "text-red-300", dot: "bg-red-400" },
  insufficient: { label: "Building evidence", fg: "text-white/50", dot: "bg-white/40" },
};

function AutonomyPosture({ autonomy }: { autonomy: ApiFleetAutonomy | null }) {
  if (!autonomy || autonomy.total_workflows === 0) {
    return (
      <Panel title="Autonomy posture">
        <p className="py-3 text-[12px] text-white/40">
          Publish a workflow and run it a few times — PerceptAI measures its verified reliability and
          tells you when it has earned the right to run unattended.
        </p>
      </Panel>
    );
  }
  const fleetPct = autonomy.fleet_verified_success_rate != null
    ? Math.round(autonomy.fleet_verified_success_rate * 100) : null;
  const order: AutonomyTier[] = ["ready", "supervised", "in_the_loop", "insufficient"];
  return (
    <section className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden" data-testid="autonomy-posture">
      <div className="flex items-center justify-between px-4 h-11 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <Gauge size={13} className="text-white/45" />
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/45">Autonomy posture</span>
        </div>
        <Link href="/dashboard/studio" className="font-mono text-[10px] uppercase tracking-wider text-white/35 hover:text-accent transition-colors">
          Studio
        </Link>
      </div>

      <div className="grid grid-cols-2 divide-x divide-white/[0.06] border-b border-white/[0.06]">
        <div className="px-4 py-3">
          <div className="font-mono text-[9px] uppercase tracking-wider text-white/35">Earned autonomy</div>
          <div className="mt-0.5 flex items-baseline gap-1.5">
            <span className="text-[24px] font-semibold tabular-nums leading-none text-accent">{autonomy.earned_autonomy}</span>
            <span className="text-[11px] text-white/35">/ {autonomy.graded_workflows} workflows</span>
          </div>
          <div className="mt-1 text-[9.5px] text-white/30">run unattended, safely</div>
        </div>
        <div className="px-4 py-3">
          <div className="font-mono text-[9px] uppercase tracking-wider text-white/35">Fleet verified success</div>
          <div className={cn("mt-0.5 text-[24px] font-semibold tabular-nums leading-none",
                             (fleetPct ?? 0) >= 90 ? "text-accent" : (fleetPct ?? 0) >= 70 ? "text-amber-300" : "text-white/70")}>
            {fleetPct != null ? `${fleetPct}%` : "—"}
          </div>
          <div className="mt-1 text-[9.5px] text-white/30">across {autonomy.total_runs} runs</div>
        </div>
      </div>

      {/* the confident liars — reliable-looking, not trustworthy */}
      {autonomy.confident_liars.length > 0 && (
        <div className="px-4 py-2.5 border-b border-white/[0.06] bg-red-400/[0.03]">
          <div className="flex items-center gap-1.5 text-red-300">
            <ShieldAlert size={12} />
            <span className="font-mono text-[9.5px] uppercase tracking-wider">
              {autonomy.confident_liars.length} look reliable but aren&apos;t calibrated
            </span>
          </div>
          <div className="mt-1.5 space-y-1">
            {autonomy.confident_liars.slice(0, 2).map((w) => (
              <Link key={w.id} href={`/dashboard/studio/${w.id}`}
                    className="flex items-center gap-2 text-[12px] text-white/70 hover:text-white">
                <span className="truncate flex-1">{w.name}</span>
                <span className="font-mono text-[10px] text-accent/80">{Math.round(w.verified_success_rate * 100)}% ok</span>
                <span className="font-mono text-[10px] text-red-300/80">poorly calibrated</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* tier ladder */}
      <div className="px-4 py-3">
        {order.filter((t) => (autonomy.by_tier[t] ?? 0) > 0).map((tier) => (
          <div key={tier} className="flex items-center gap-2.5 py-1">
            <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", TIER_META[tier].dot)} />
            <span className={cn("text-[12px]", TIER_META[tier].fg)}>{TIER_META[tier].label}</span>
            <span className="ml-auto font-mono text-[12px] tabular-nums text-white/60">{autonomy.by_tier[tier]}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ============================================== fleet capacity (TRUST) === */

function FleetCapacity({ runners, health, scheduled }: {
  runners: ApiRunner[]; health: PlatformHealth | null; scheduled: number;
}) {
  const tone = (s: string) =>
    s === "online" || s === "busy" ? "bg-accent"
      : s === "offline" || s === "network_unavailable" ? "bg-white/30" : "bg-amber-300";
  return (
    <Panel title="Fleet capacity" action={{ href: "/dashboard/runners", label: "Runners" }}>
      {runners.length === 0 ? (
        <p className="py-2 text-[12px] text-white/40">
          No runners yet. A runner executes work on a real Windows desktop — connect one to run unattended.
        </p>
      ) : (
        <div className="space-y-1.5">
          {runners.slice(0, 5).map((r) => (
            <div key={r.id} className="flex items-center gap-2.5"
                 title={r.readiness?.detail || undefined}>
              <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", tone(r.status))} />
              <span className="text-[12.5px] text-white/80 truncate">{r.name}</span>
              <span className={cn("ml-auto font-mono text-[10px] uppercase tracking-wider shrink-0",
                                  r.status === "online" || r.status === "busy" ? "text-accent/80"
                                    : r.status === "offline" ? "text-white/35" : "text-amber-300/90")}>
                {r.status.replace(/_/g, " ")}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="mt-2.5 flex items-center gap-3 border-t border-white/[0.05] pt-2 font-mono text-[9.5px] uppercase tracking-wider text-white/35">
        <span className="flex items-center gap-1">
          <span className={cn("h-1.5 w-1.5 rounded-full", health?.scheduler ? "bg-accent" : "bg-white/25")} />
          scheduler {health?.scheduler ? "on" : "off"}
        </span>
        <span>· {scheduled} scheduled</span>
      </div>
    </Panel>
  );
}

/* ================================================== coming up (PLAN) === */

function ComingUp({ workflows, autonomy }: {
  workflows: ApiWorkflow[]; autonomy: ApiFleetAutonomy | null;
}) {
  const tierOf = (id: string): AutonomyTier | null =>
    autonomy?.workflows.find((w) => w.id === id)?.tier ?? null;
  const upcoming = workflows
    .filter((w) => w.schedule?.enabled && w.schedule?.next_run_at)
    .sort((a, b) => (a.schedule!.next_run_at! < b.schedule!.next_run_at! ? -1 : 1))
    .slice(0, 5);
  if (upcoming.length === 0) return null;
  return (
    <Panel title="Coming up" action={{ href: "/dashboard/studio", label: "Studio" }}>
      <div className="space-y-2">
        {upcoming.map((w) => {
          const tier = tierOf(w.id);
          return (
            <Link key={w.id} href={`/dashboard/studio/${w.id}`}
                  className="flex items-center gap-2.5 group">
              <CalendarClock size={13} className="text-white/30 shrink-0" />
              <span className="flex-1 min-w-0 truncate text-[12.5px] text-white/80 group-hover:text-white">{w.name}</span>
              {tier && (
                <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", TIER_META[tier].dot)}
                      title={TIER_META[tier].label} />
              )}
              <span className="font-mono text-[10px] text-white/35 shrink-0">
                {relativeWhen(w.schedule!.next_run_at!)}
              </span>
            </Link>
          );
        })}
      </div>
    </Panel>
  );
}

/* ==================================================== in flight (WATCH) === */

function InFlight({ missions, sessions, recentSessions, recentMissions }: {
  missions: ApiMission[];
  sessions: DashboardStats["recent_sessions"];
  recentSessions: DashboardStats["recent_sessions"];
  recentMissions: ApiMission[];
}) {
  const live = missions.length + sessions.length;
  return (
    <Panel title={live ? "In flight" : "Recent activity"}
           action={{ href: "/dashboard/sessions", label: "All runs" }}>
      {live === 0 && recentSessions.length === 0 && recentMissions.length === 0 ? (
        <Empty text="Nothing has run yet." cta={{ href: "/dashboard/run", label: "Run a task" }} />
      ) : (
        <div className="divide-y divide-white/[0.04]">
          {missions.map((m) => (
            <Link key={m.id} href={`/dashboard/missions/${m.id}`} className="flex items-center gap-3 py-2.5 group">
              <StatusDot status={m.status} />
              <span className="flex-1 min-w-0 truncate text-[13px] text-white/80 group-hover:text-white">{m.instruction}</span>
              <span className="font-mono text-[10px] text-sky-300/80 shrink-0">
                {m.metrics ? `${m.metrics.orders_completed}/${m.metrics.orders_total} orders` : "running"}
              </span>
            </Link>
          ))}
          {sessions.map((s) => (
            <Link key={s.id} href={`/dashboard/sessions/${s.id}`} className="flex items-center gap-3 py-2.5 group">
              <StatusDot status={s.status} />
              <span className="flex-1 min-w-0 truncate text-[13px] text-white/80 group-hover:text-white">{s.instruction}</span>
              <span className="font-mono text-[10px] text-sky-300/80 shrink-0">running</span>
            </Link>
          ))}
          {/* fall back to recent finished runs when nothing is live */}
          {live === 0 && recentSessions.slice(0, 6).map((s) => (
            <Link key={s.id} href={`/dashboard/sessions/${s.id}`} className="flex items-center gap-3 py-2.5 group">
              <StatusDot status={s.status} />
              <span className="flex-1 min-w-0 truncate text-[13px] text-white/80 group-hover:text-white">{s.instruction}</span>
              <span className="font-mono text-[10px] text-white/30 shrink-0">
                {s.steps_count} steps{s.execution_time ? ` · ${s.execution_time.toFixed(1)}s` : ""}
              </span>
              <span className="font-mono text-[10px] text-white/25 shrink-0 w-16 text-right">{timeAgo(s.created_at)}</span>
            </Link>
          ))}
        </div>
      )}
    </Panel>
  );
}

function relativeWhen(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = (then - Date.now()) / 1000;
  if (s <= 0) return "due";
  if (s < 3600) return `in ${Math.round(s / 60)}m`;
  if (s < 86400) return `in ${Math.round(s / 3600)}h`;
  return `in ${Math.round(s / 86400)}d`;
}

/* ------------------------------------------------------------------ */

function settled<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

function Panel({ title, action, children }: {
  title: string;
  action?: { href: string; label: string };
  children: React.ReactNode;
}) {
  return (
    <section className="glass rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">{title}</h2>
        {action && (
          <Link href={action.href}
                className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider text-white/35 hover:text-accent transition-colors">
            {action.label} <ArrowRight size={11} />
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "completed" ? "bg-accent" :
    status === "partial" || status === "unverified" ? "bg-amber-300" :
    status === "failed" ? "bg-red-400" :
    status === "running" ? "bg-sky-300 animate-pulse" : "bg-white/25";
  return <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", color)} title={status} />;
}

function Empty({ text, cta }: { text: string; cta?: { href: string; label: string } }) {
  return (
    <div className="py-6 text-center">
      <p className="text-[12px] text-white/35">{text}</p>
      {cta && (
        <Link href={cta.href}
              className="mt-2 inline-flex items-center gap-1 text-[12px] text-accent hover:underline">
          {cta.label} <ArrowRight size={12} />
        </Link>
      )}
    </div>
  );
}

function HealthStrip({ health }: { health: PlatformHealth | null }) {
  const items = [
    { label: "api", ok: health != null },
    { label: "database", ok: health?.database ?? false },
    { label: "engine", ok: health?.engine ?? false },
    { label: "scheduler", ok: health?.scheduler ?? false, neutralOff: true },
  ];
  return (
    <div className="glass flex items-center gap-4 rounded-lg px-3 py-2"
         title={health?.engine_reason || undefined}>
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5">
          <span className={cn(
            "h-1.5 w-1.5 rounded-full",
            item.ok ? "bg-accent" : item.neutralOff ? "bg-white/20" : "bg-red-400",
          )} />
          <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-white/40">
            {item.label}
          </span>
        </span>
      ))}
    </div>
  );
}

/** The unattended-operations inbox: everything that reached a human because
 * nobody was watching — final failures, dead-letters, waiting approvals,
 * schedules that cannot run. Ack removes it; an empty inbox renders nothing
 * (silence means healthy, and the panel never nags). */
function AttentionPanel({ items, onAcked }: {
  items: ApiAttentionItem[]; onAcked: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  if (items.length === 0) return null;

  const tone = (kind: ApiAttentionItem["kind"]) =>
    kind === "run_failed" || kind === "dead_letter" ? "red" : "amber";
  const ack = async (id: string) => {
    setBusy(id);
    try {
      await ackAttention(id);
      onAcked();
    } catch {
      // stays open; the refresh keeps it honest
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="rounded-xl border border-amber-300/20 bg-amber-300/[0.03] p-4"
             data-testid="attention-inbox">
      <div className="mb-2 flex items-center gap-2">
        <BellRing size={13} className="text-amber-300" />
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-amber-300/90">
          Needs attention
        </h2>
        <span className="ml-auto font-mono text-[10px] text-white/35 tabular-nums">
          {items.length} open
        </span>
      </div>
      <div className="space-y-2">
        {items.slice(0, 5).map((item) => {
          const detailText = String(
            item.detail?.error ?? item.detail?.reason ?? item.detail?.warning ??
            item.detail?.summary ?? "");
          const href = item.session_id
            ? `/dashboard/sessions/${item.session_id}`
            : item.workflow_id ? `/dashboard/studio/${item.workflow_id}` : null;
          return (
            <div key={item.id}
                 className={cn("rounded-lg border px-3 py-2",
                               tone(item.kind) === "red"
                                 ? "border-red-400/15 bg-red-400/[0.04]"
                                 : "border-amber-300/15 bg-amber-300/[0.04]")}>
              <div className="flex items-center justify-between gap-2">
                <span className={cn("font-mono text-[9px] uppercase tracking-wider",
                                    tone(item.kind) === "red" ? "text-red-300" : "text-amber-300")}>
                  {item.kind.replace(/_/g, " ")}
                </span>
                <span className="font-mono text-[9px] text-white/30 shrink-0">
                  {timeAgo(item.created_at)}
                </span>
              </div>
              <p className="mt-1 text-[12px] text-white/75 leading-snug">{item.title}</p>
              {detailText && (
                <p className="mt-0.5 text-[11px] text-white/40 line-clamp-2">{detailText}</p>
              )}
              <div className="mt-1.5 flex items-center gap-2">
                {href && (
                  <Link href={href}
                        className="font-mono text-[10px] uppercase tracking-wider text-white/50 hover:text-accent transition-colors">
                    Inspect
                  </Link>
                )}
                <button onClick={() => ack(item.id)} disabled={busy === item.id}
                        className="ml-auto rounded-md bg-white/[0.04] px-2.5 h-6 font-mono text-[10px] uppercase tracking-wider text-white/50 hover:text-white hover:bg-white/[0.08] transition-colors disabled:opacity-50">
                  Ack
                </button>
              </div>
            </div>
          );
        })}
        {items.length > 5 && (
          <p className="font-mono text-[10px] text-white/30">
            +{items.length - 5} more open item{items.length - 5 === 1 ? "" : "s"}
          </p>
        )}
      </div>
    </section>
  );
}

function ApprovalsPanel({ approvals, onDecided }: {
  approvals: ApiApproval[]; onDecided: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const decide = async (id: string, decision: "approved" | "denied") => {
    setBusy(id);
    try {
      await decideApproval(id, decision);
      onDecided();
    } catch {
      // surfaced by refresh: the row stays pending
    } finally {
      setBusy(null);
    }
  };
  return (
    <Panel title="Pending approvals"
           action={{ href: "/dashboard/approvals", label: "History" }}>
      {approvals.length === 0 ? (
        <p className="py-3 text-[12px] text-white/35">
          Nothing waiting. Capabilities that require approval are configured
          per workspace in{" "}
          <Link href="/dashboard/org" className="text-white/55 hover:text-accent">Organization → Policies</Link>.
        </p>
      ) : (
        <div className="space-y-2">
          {approvals.slice(0, 4).map((approval) => (
            <div key={approval.id}
                 className="rounded-lg border border-amber-300/15 bg-amber-300/[0.04] px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider text-amber-300">
                  {approval.capability}
                </span>
                <span className="font-mono text-[9px] text-white/30">{timeAgo(approval.created_at)}</span>
              </div>
              <p className="mt-1 text-[12px] text-white/70 line-clamp-2">{approval.objective}</p>
              <div className="mt-2 flex gap-2">
                <button
                  onClick={() => decide(approval.id, "approved")}
                  disabled={busy === approval.id}
                  className="rounded-md bg-accent/15 px-2.5 h-6 font-mono text-[10px] uppercase tracking-wider text-accent hover:bg-accent/25 transition-colors disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  onClick={() => decide(approval.id, "denied")}
                  disabled={busy === approval.id}
                  className="rounded-md bg-white/[0.04] px-2.5 h-6 font-mono text-[10px] uppercase tracking-wider text-white/50 hover:text-red-300 hover:bg-red-400/10 transition-colors disabled:opacity-50"
                >
                  Deny
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------ first run */

// The one benign, self-verifying task that proves the whole loop safely.
const STARTER_TASK = "Open Notepad and type 'Hello from PerceptAI'";

function FirstRun({ templates }: { templates: ApiTemplate[] }) {
  const router = useRouter();

  const runStarter = (target: "local" | "runner") => {
    try {
      window.localStorage.setItem("perceptai_pending_run",
        JSON.stringify({ instruction: STARTER_TASK, mode: "task", target }));
    } catch {
      /* ignore */
    }
    router.push("/dashboard/run");
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }} className="space-y-4">
      <div className="glass-strong rounded-xl p-6">
        <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-accent/80">get started</span>
        <h2 className="mt-2 text-[19px] font-semibold tracking-tight text-white">
          Reach your first successful run
        </h2>
        <p className="mt-1.5 text-[13px] text-white/55 max-w-xl leading-relaxed">
          Describe a goal in plain English — PerceptAI perceives the screen, plans, acts, and
          <span className="text-white/75"> verifies the outcome</span>. Start with one safe task and watch the
          whole loop in the live cockpit.
        </p>

        {/* The one-click path to first success */}
        <div className="mt-5 rounded-lg border border-accent/20 bg-accent/[0.04] p-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-[13px] text-white/85">
                <PlayCircle size={15} className="text-accent shrink-0" />
                Run a safe starter task
              </div>
              <p className="mt-1 text-[12px] text-white/50 leading-relaxed">
                Opens Notepad, types one line, and verifies it — harmless, about 15 seconds. Runs on
                this machine and takes the screen briefly; you approve the run on the next screen.
              </p>
            </div>
            <button
              onClick={() => runStarter("local")}
              data-testid="run-starter-task"
              className="shrink-0 inline-flex items-center gap-2 rounded-lg bg-accent text-black px-4 h-10 text-[13px] font-medium hover:shadow-[0_0_40px_-8px_rgba(0,255,133,0.6)] transition-shadow"
            >
              Run starter task <ArrowRight size={14} />
            </button>
          </div>
        </div>

        {/* Alternative: run it on a runner instead of this machine */}
        <div className="mt-3 flex flex-col sm:flex-row sm:items-center gap-2 text-[12px] text-white/45">
          <span>Prefer to run it elsewhere?</span>
          <Link href="/dashboard/runners" className="inline-flex items-center gap-1 text-accent/80 hover:text-accent">
            <Server size={12} /> Connect a runner
          </Link>
          <span className="hidden sm:inline text-white/25">·</span>
          <button onClick={() => runStarter("runner")} className="text-white/55 hover:text-white text-left">
            then run the starter on it <ArrowRight size={11} className="inline" />
          </button>
        </div>

        {/* What to expect — sets the trust frame without being a wall of steps */}
        <div className="mt-5 grid grid-cols-3 gap-3 border-t border-white/[0.06] pt-4">
          {[
            { n: "1", t: "Describe", b: "Plain English goal" },
            { n: "2", t: "Watch it work", b: "Live cockpit: now, why, next" },
            { n: "3", t: "Verified result", b: "Outcome checked, not assumed" },
          ].map((s) => (
            <div key={s.n} className="min-w-0">
              <div className="flex items-center gap-1.5 text-white/40">
                <span className="font-mono text-[9px] uppercase tracking-[0.16em]">{s.n}</span>
                <span className="text-[12px] text-white/80 truncate">{s.t}</span>
              </div>
              <p className="mt-0.5 text-[11px] leading-snug text-white/40">{s.b}</p>
            </div>
          ))}
        </div>
      </div>

      {templates.length > 0 && (
        <Panel title="Start from a template" action={{ href: "/dashboard/studio", label: "All templates" }}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {templates.slice(0, 3).map((template) => (
              <Link key={template.id}
                    href={`/dashboard/studio?template=${template.id}`}
                    className="group rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 hover:border-accent/30 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-white/30">
                    {template.category}
                  </span>
                  <span className={cn("rounded border px-1.5 py-[1px] font-mono text-[9px] uppercase",
                                      template.mode === "mission"
                                        ? "border-accent/25 text-accent/80"
                                        : "border-white/15 text-white/40")}>
                    {template.mode}
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-2 text-[13px] text-white/85">
                  <FileText size={13} className="text-white/30" /> {template.name}
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-white/40 line-clamp-2">
                  {template.description}
                </p>
              </Link>
            ))}
          </div>
        </Panel>
      )}
    </motion.div>
  );
}

function ControlSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      <div className="h-10 w-64 rounded-lg bg-white/[0.04]" />
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-[84px] rounded-xl bg-white/[0.04]" />
        ))}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[1.6fr_1fr] gap-4">
        <div className="h-72 rounded-xl bg-white/[0.04]" />
        <div className="h-72 rounded-xl bg-white/[0.04]" />
      </div>
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

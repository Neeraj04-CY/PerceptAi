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
  CheckCircle2,
  FileText,
  Network,
  PenTool,
  PlayCircle,
  ShieldCheck,
  Users,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  ApiApproval,
  ApiCapabilities,
  ApiMission,
  ApiTemplate,
  DashboardStats,
  OrgUsage,
  PlatformHealth,
  decideApproval,
  getApprovals,
  getCapabilities,
  getDashboardStats,
  getMissions,
  getOrgs,
  getOrgUsage,
  getPlatformHealth,
  getTemplates,
} from "@/lib/api";

interface ControlData {
  stats: DashboardStats | null;
  missions: ApiMission[];
  approvals: ApiApproval[];
  capabilities: ApiCapabilities | null;
  health: PlatformHealth | null;
  usage: OrgUsage | null;
  templates: ApiTemplate[];
}

export default function MissionControlPage() {
  const router = useRouter();
  const [data, setData] = useState<ControlData | null>(null);
  const [loading, setLoading] = useState(true);
  const [unauthorized, setUnauthorized] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    const [stats, missions, approvals, capabilities, health, usage, templates] =
      await Promise.allSettled([
        getDashboardStats(signal),
        getMissions(10, signal),
        getApprovals("pending", signal),
        getCapabilities(signal),
        getPlatformHealth(signal),
        getOrgs(signal).then((orgs) => (orgs[0] ? getOrgUsage(orgs[0].id, signal) : null)),
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
      capabilities: settled(capabilities, null),
      health: settled(health, null),
      usage: settled(usage, null),
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

  const { stats, missions, approvals, capabilities, health, usage, templates } = data;
  const runningMissions = missions.filter((m) => m.status === "running");
  const recentSessions = stats?.recent_sessions ?? [];
  const firstRun = recentSessions.length === 0 && missions.length === 0;

  return (
    <div className="space-y-5">
      {/* header + host truth */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[17px] font-medium text-white">Mission Control</h1>
          <p className="text-[12px] text-white/40 mt-0.5">
            Live operations across tasks, missions and the workforce.
          </p>
        </div>
        <HealthStrip health={health} />
      </div>

      {/* stat strip */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="grid grid-cols-2 md:grid-cols-5 gap-3"
      >
        <Stat icon={Activity} label="Running now"
              value={String(runningMissions.length)}
              hint={runningMissions.length ? "missions in flight" : "all quiet"} />
        <Stat icon={CheckCircle2} label="Succeeded"
              value={String(stats?.successful_sessions ?? 0)}
              hint="recent sessions" accent />
        <Stat icon={XCircle} label="Failed"
              value={String(stats?.failed_sessions ?? 0)}
              hint="recent sessions"
              alert={(stats?.failed_sessions ?? 0) > 0} />
        <Stat icon={ShieldCheck} label="Needs approval"
              value={String(approvals.length)}
              hint={approvals.length ? "waiting on you" : "none pending"}
              alert={approvals.length > 0} />
        <Stat icon={Users} label="Specialists"
              value={String(capabilities?.specialists.length ?? 0)}
              hint={capabilities?.available
                ? `${capabilities.capabilities.length} capabilities`
                : "engine offline"} />
      </motion.div>

      {firstRun ? (
        <FirstRun templates={templates} />
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[1.6fr_1fr] gap-4 items-start">
          {/* left: activity */}
          <div className="space-y-4">
            <Panel title="Missions" action={{ href: "/dashboard/missions", label: "All missions" }}>
              {missions.length === 0 ? (
                <Empty text="No missions yet — run one from the Run page or Studio."
                       cta={{ href: "/dashboard/run", label: "Run a mission" }} />
              ) : (
                <div className="divide-y divide-white/[0.04]">
                  {missions.slice(0, 6).map((mission) => (
                    <Link key={mission.id} href={`/dashboard/missions/${mission.id}`}
                          className="flex items-center gap-3 py-2.5 group">
                      <StatusDot status={mission.status} />
                      <span className="flex-1 min-w-0 truncate text-[13px] text-white/80 group-hover:text-white">
                        {mission.instruction}
                      </span>
                      <span className="font-mono text-[10px] text-white/30 shrink-0">
                        {mission.metrics
                          ? `${mission.metrics.orders_completed}/${mission.metrics.orders_total} orders`
                          : mission.status}
                        {mission.duration_s ? ` · ${Math.round(mission.duration_s)}s` : ""}
                      </span>
                      <span className="font-mono text-[10px] text-white/25 shrink-0 w-16 text-right">
                        {timeAgo(mission.created_at)}
                      </span>
                    </Link>
                  ))}
                </div>
              )}
            </Panel>

            <Panel title="Sessions" action={{ href: "/dashboard/sessions", label: "All sessions" }}>
              {recentSessions.length === 0 ? (
                <Empty text="No task sessions yet." cta={{ href: "/dashboard/run", label: "Run a task" }} />
              ) : (
                <div className="divide-y divide-white/[0.04]">
                  {recentSessions.slice(0, 6).map((session) => (
                    <Link key={session.id} href={`/dashboard/sessions/${session.id}`}
                          className="flex items-center gap-3 py-2.5 group">
                      <StatusDot status={session.status} />
                      <span className="flex-1 min-w-0 truncate text-[13px] text-white/80 group-hover:text-white">
                        {session.instruction}
                      </span>
                      <span className="font-mono text-[10px] text-white/30 shrink-0">
                        {session.steps_count} steps
                        {session.execution_time ? ` · ${session.execution_time.toFixed(1)}s` : ""}
                      </span>
                      <span className="font-mono text-[10px] text-white/25 shrink-0 w-16 text-right">
                        {timeAgo(session.created_at)}
                      </span>
                    </Link>
                  ))}
                </div>
              )}
            </Panel>
          </div>

          {/* right: control rail */}
          <div className="space-y-4">
            <ApprovalsPanel approvals={approvals} onDecided={() => load()} />
            <UsagePanel usage={usage} stats={stats} />
            <SpecialistPanel capabilities={capabilities} />
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function settled<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

function Stat({ icon: Icon, label, value, hint, accent, alert }: {
  icon: typeof Activity; label: string; value: string; hint: string;
  accent?: boolean; alert?: boolean;
}) {
  return (
    <div className="glass rounded-xl px-4 py-3">
      <div className="flex items-center gap-2 text-white/40">
        <Icon size={13} strokeWidth={1.6} />
        <span className="font-mono text-[9px] uppercase tracking-[0.18em]">{label}</span>
      </div>
      <div className={cn(
        "mt-1.5 text-[22px] font-medium tabular-nums leading-none",
        accent ? "text-accent" : alert ? "text-amber-300" : "text-white",
      )}>
        {value}
      </div>
      <div className="mt-1 text-[10px] text-white/30 truncate">{hint}</div>
    </div>
  );
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

function UsagePanel({ usage, stats }: { usage: OrgUsage | null; stats: DashboardStats | null }) {
  const used = usage?.executions_used ?? stats?.total_executions_this_month ?? 0;
  const limit = usage?.executions_limit ?? stats?.executions_limit ?? 0;
  const pct = limit ? Math.min(100, (used / limit) * 100) : 0;
  return (
    <Panel title="Usage & budget" action={{ href: "/dashboard/org", label: "Details" }}>
      <div className="flex items-baseline justify-between">
        <span className="text-[18px] font-medium tabular-nums text-white">{used.toLocaleString()}</span>
        <span className="font-mono text-[10px] text-white/35">
          of {limit.toLocaleString()} runs · {(usage?.plan ?? stats?.plan ?? "free").toUpperCase()}
        </span>
      </div>
      <div className="mt-2 h-1 rounded-full bg-white/[0.06] overflow-hidden">
        <div className={cn("h-full rounded-full transition-[width] duration-500",
                           pct > 90 ? "bg-red-400" : pct > 70 ? "bg-amber-300" : "bg-accent")}
             style={{ width: `${pct}%` }} />
      </div>
      {usage?.workforce_limits && (
        <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1">
          <Meta k="parallel specialists" v={String(usage.workforce_limits.max_parallel ?? "—")} />
          <Meta k="orders / mission" v={String(usage.workforce_limits.max_work_orders ?? "—")} />
          <Meta k="mission budget" v={`${usage.workforce_limits.max_total_cost ?? "—"} cr`} />
          <Meta k="mission wall clock" v={`${Math.round((usage.workforce_limits.max_mission_duration_s ?? 0) / 60)}m`} />
        </div>
      )}
    </Panel>
  );
}

function Meta({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-2 min-w-0">
      <span className="font-mono text-[9px] uppercase tracking-wider text-white/30 truncate">{k}</span>
      <span className="font-mono text-[10px] text-white/60 tabular-nums">{v}</span>
    </div>
  );
}

function SpecialistPanel({ capabilities }: { capabilities: ApiCapabilities | null }) {
  return (
    <Panel title="Workforce roster">
      {!capabilities?.available ? (
        <p className="py-3 text-[12px] text-white/35">
          Engine offline on this host — the roster appears when the API runs
          on a desktop machine.
        </p>
      ) : (
        <div className="space-y-1.5">
          {capabilities.specialists.map((s) => (
            <div key={s.name} className="flex items-center gap-2.5">
              <span className={cn("h-1.5 w-1.5 rounded-full shrink-0",
                                  s.healthy ? "bg-accent" : "bg-red-400")} />
              <span className="text-[12px] text-white/75 w-28 truncate">{s.name}</span>
              <span className="font-mono text-[10px] text-white/30 flex-1 truncate">
                {s.capabilities.join(", ")}
              </span>
              <span className="font-mono text-[9px] text-white/25 shrink-0">
                {s.resources.includes("desktop") ? "desktop" : "compute"}
              </span>
            </div>
          ))}
          {typeof capabilities.plugin_count === "number" && (
            <p className="pt-1.5 font-mono text-[9px] uppercase tracking-wider text-white/25">
              {capabilities.plugin_count} plugin specialist(s) discovered
            </p>
          )}
        </div>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------ first run */

function FirstRun({ templates }: { templates: ApiTemplate[] }) {
  const steps = [
    { icon: PlayCircle, title: "Run your first task",
      body: "Plain English in — the agent perceives the screen, plans, acts and verifies.",
      href: "/dashboard/run", cta: "Open Run" },
    { icon: Network, title: "Launch a mission",
      body: "An executive decomposes the goal across specialists and returns one grounded report.",
      href: "/dashboard/run", cta: "Run as mission" },
    { icon: PenTool, title: "Save it as a workflow",
      body: "Parametrize with variables, publish a version, schedule it.",
      href: "/dashboard/studio", cta: "Open Studio" },
  ];
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }} className="space-y-4">
      <div className="glass-strong rounded-xl p-6">
        <h2 className="text-[15px] font-medium text-white">Welcome to PerceptAI</h2>
        <p className="mt-1 text-[13px] text-white/50 max-w-xl">
          An AI workforce that works your real screen: perception in, verified
          business outcomes out. Three steps to your first report:
        </p>
        <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-3">
          {steps.map((step, i) => (
            <Link key={step.title} href={step.href}
                  className="group rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 hover:border-accent/30 transition-colors">
              <div className="flex items-center gap-2 text-white/40">
                <step.icon size={15} strokeWidth={1.6} />
                <span className="font-mono text-[9px] uppercase tracking-[0.18em]">Step {i + 1}</span>
              </div>
              <div className="mt-2 text-[13px] text-white/85">{step.title}</div>
              <p className="mt-1 text-[11px] leading-relaxed text-white/40">{step.body}</p>
              <span className="mt-3 inline-flex items-center gap-1 text-[11px] text-accent opacity-70 group-hover:opacity-100">
                {step.cta} <ArrowRight size={11} />
              </span>
            </Link>
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

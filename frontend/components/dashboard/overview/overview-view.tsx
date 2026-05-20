"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowRight,
  ArrowUpRight,
  Activity,
  Clock,
  Layers,
  Gauge,
  CheckCircle2,
  PlayCircle,
  KeyRound,
  ChevronRight,
  History,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { GlassCard } from "@/components/ui/glass-card";
import { MetricCard } from "@/components/ui/metric-card";
import { SectionLabel } from "@/components/ui/section-label";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/loading-skeleton";
import {
  getSessions,
  getStats,
  type ApiSession,
  type ApiStats,
} from "@/lib/api";
import { staggerContainer, fadeUp } from "@/lib/motion";
import { formatRelativeTime, truncate } from "@/components/dashboard/sessions/format";
import { cn } from "@/lib/utils";

export function OverviewView() {
  const router = useRouter();
  const [sessions, setSessions] = useState<ApiSession[] | null>(null);
  const [stats, setStats] = useState<ApiStats | null>(null);
  const [loading, setLoading] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    Promise.allSettled([
      getSessions(controller.signal),
      getStats(controller.signal),
    ]).then(([sRes, stRes]) => {
      if (controller.signal.aborted) return;
      if (sRes.status === "fulfilled") setSessions(sRes.value);
      else setSessions([]);
      if (stRes.status === "fulfilled") setStats(stRes.value);
      setLoading(false);
    });

    return () => controller.abort();
  }, []);

  const derived = useMemo(() => {
    const list = sessions ?? [];
    const total = stats?.total_sessions ?? list.length;
    const completed = list.filter((s) => s.status === "completed").length;
    const successRate =
      stats?.success_rate != null
        ? Number(stats.success_rate)
        : list.length
        ? (completed / list.length) * 100
        : null;
    const durations = list
      .map((s) => s.execution_time)
      .filter((x): x is number => typeof x === "number" && !Number.isNaN(x));
    const avg =
      stats?.avg_duration != null
        ? Number(stats.avg_duration)
        : durations.length
        ? durations.reduce((a, b) => a + b, 0) / durations.length
        : null;
    const usage = stats?.monthly_usage ?? list.length;
    const limit = stats?.monthly_limit ?? 1_000_000;
    return {
      total,
      successRate,
      avg,
      usage,
      limit,
      latest: list.slice(0, 5),
    };
  }, [sessions, stats]);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Dashboard"
        title="Overview"
        description="Monitor executions, runtime health, and platform activity."
        action={
          <Link href="/dashboard">
            <Button variant="primary" size="md" data-testid="overview-run-task" className="gap-2">
              Run Task
              <ArrowRight size={14} />
            </Button>
          </Link>
        }
      />

      {/* Metrics row */}
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        <MetricCard
          testId="metric-total-sessions"
          label="Total Sessions"
          icon={<Layers size={14} />}
          value={loading ? <Skeleton className="h-8 w-20" /> : formatNumber(derived.total)}
          sub="all-time agent runs"
        />
        <MetricCard
          testId="metric-success-rate"
          label="Success Rate"
          icon={<CheckCircle2 size={14} />}
          value={
            loading ? (
              <Skeleton className="h-8 w-20" />
            ) : derived.successRate != null ? (
              `${derived.successRate.toFixed(1)}%`
            ) : (
              "—"
            )
          }
          sub="last 30 days"
        />
        <MetricCard
          testId="metric-avg-duration"
          label="Avg Duration"
          icon={<Clock size={14} />}
          value={
            loading ? (
              <Skeleton className="h-8 w-20" />
            ) : derived.avg != null ? (
              `${derived.avg.toFixed(2)}s`
            ) : (
              "—"
            )
          }
          sub="median across runs"
        />
        <MetricCard
          testId="metric-monthly-usage"
          label="Monthly Usage"
          icon={<Gauge size={14} />}
          value={loading ? <Skeleton className="h-8 w-20" /> : formatNumber(derived.usage)}
          sub={`of ${formatNumber(derived.limit)} included`}
        />
      </motion.div>

      {/* Recent + Runtime status */}
      <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-4">
        {/* Recent sessions */}
        <motion.div variants={fadeUp} initial="hidden" animate="show">
          <GlassCard padding="none" data-testid="recent-sessions">
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06]">
              <SectionLabel>Recent sessions</SectionLabel>
              <Link
                href="/dashboard/sessions"
                className="inline-flex items-center gap-1 text-[12px] text-white/55 hover:text-white transition-colors"
                data-testid="recent-view-all"
              >
                View all
                <ArrowUpRight size={12} />
              </Link>
            </div>

            <div>
              {loading ? (
                <RecentLoading />
              ) : derived.latest.length === 0 ? (
                <EmptyState
                  icon={<History size={22} strokeWidth={1.5} />}
                  title="No sessions yet"
                  description="Your most recent agent runs will appear here."
                  minHeight={220}
                  action={
                    <Link href="/dashboard">
                      <Button variant="primary" size="sm" className="gap-1.5">
                        Run your first task
                        <ArrowRight size={12} />
                      </Button>
                    </Link>
                  }
                />
              ) : (
                derived.latest.map((s, i) => (
                  <RecentRow
                    key={s.id}
                    session={s}
                    index={i}
                    onClick={() => router.push(`/dashboard/sessions/${s.id}`)}
                  />
                ))
              )}
            </div>
          </GlassCard>
        </motion.div>

        {/* Runtime status */}
        <motion.div variants={fadeUp} initial="hidden" animate="show">
          <RuntimeStatusCard usage={derived.usage} limit={derived.limit} loading={loading} />
        </motion.div>
      </div>

      {/* Quick actions */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="space-y-3">
        <SectionLabel>Quick actions</SectionLabel>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <QuickAction
            href="/dashboard"
            icon={<PlayCircle size={16} />}
            title="Run New Task"
            description="Spin up a perception-driven agent run."
            testId="quick-run"
          />
          <QuickAction
            href="/dashboard/sessions"
            icon={<Layers size={16} />}
            title="View Sessions"
            description="Replay traces and triage failed runs."
            testId="quick-sessions"
          />
          <QuickAction
            href="/dashboard/keys"
            icon={<KeyRound size={16} />}
            title="Manage API Keys"
            description="Rotate credentials and scope access."
            testId="quick-keys"
          />
        </div>
      </motion.div>
    </div>
  );
}

function RecentLoading() {
  return (
    <div>
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-4 px-5 py-4 border-b border-white/[0.04] last:border-0"
        >
          <Skeleton className="h-3 flex-1" />
          <Skeleton className="h-5 w-20" rounded="full" />
          <Skeleton className="h-3 w-12" />
        </div>
      ))}
    </div>
  );
}

function RecentRow({
  session,
  index,
  onClick,
}: {
  session: ApiSession;
  index: number;
  onClick: () => void;
}) {
  const duration =
    session.execution_time != null
      ? `${Number(session.execution_time).toFixed(2)}s`
      : "—";
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05 }}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className="group flex items-center gap-4 px-5 py-3.5 border-b border-white/[0.04] last:border-0 cursor-pointer hover:bg-white/[0.02] transition-colors"
      data-testid={`overview-session-${session.id}`}
    >
      <div className="min-w-0 flex-1">
        <div className="text-[13px] text-white truncate" title={session.instruction}>
          {truncate(session.instruction, 60)}
        </div>
        <div className="mt-0.5 font-mono text-[10.5px] text-white/35 truncate">
          {session.id}
        </div>
      </div>
      <StatusBadge status={session.status} />
      <div className="font-mono text-[11.5px] text-white/55 w-14 text-right tabular-nums">
        {duration}
      </div>
      <div className="font-mono text-[11px] text-white/45 w-20 text-right hidden sm:block">
        {formatRelativeTime(session.created_at)}
      </div>
      <ChevronRight
        size={13}
        className="text-white/30 opacity-0 group-hover:opacity-100 transition-opacity"
      />
    </motion.div>
  );
}

function RuntimeStatusCard({
  usage,
  limit,
  loading,
}: {
  usage: number;
  limit: number;
  loading: boolean;
}) {
  const pct = Math.min(100, Math.max(0, limit ? (usage / limit) * 100 : 0));

  return (
    <GlassCard padding="md" data-testid="runtime-status-card">
      <div className="flex items-center justify-between">
        <SectionLabel>Runtime status</SectionLabel>
        <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
          <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
          Operational
        </span>
      </div>

      <div className="mt-5 space-y-4">
        <Row
          label="API host"
          value={
            <code className="font-mono text-[12px] text-white/80 truncate">
              perceptai-production.up.railway.app
            </code>
          }
        />
        <Row
          label="Region"
          value={<span className="font-mono text-[12px] text-white/80">us-west-2 · edge</span>}
        />
        <Row
          label="Status"
          value={<StatusBadge status="running" label="Online" />}
        />

        <div className="pt-4 border-t border-white/[0.06]">
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/40">
              Execution usage
            </span>
            <span
              className={cn(
                "font-mono text-[11px] tabular-nums",
                pct > 90 ? "text-[#FF3B3B]" : "text-white/70"
              )}
            >
              {loading ? "…" : `${formatNumber(usage)} / ${formatNumber(limit)}`}
            </span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-white/[0.05] overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
              className={cn(
                "h-full rounded-full",
                pct > 90 ? "bg-[#FF3B3B]" : "bg-accent"
              )}
            />
          </div>
          <div className="mt-2 font-mono text-[10px] uppercase tracking-wider text-white/35">
            {pct.toFixed(1)}% of monthly quota
          </div>
        </div>
      </div>
    </GlassCard>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/40">
        {label}
      </span>
      <div className="min-w-0">{value}</div>
    </div>
  );
}

function QuickAction({
  href,
  icon,
  title,
  description,
  testId,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
  testId: string;
}) {
  return (
    <Link href={href} data-testid={testId}>
      <motion.div
        whileHover={{ y: -2 }}
        transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
        className="group flex items-center justify-between gap-4 rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl p-4 hover:border-accent/30 hover:bg-white/[0.04] transition-colors duration-300"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="h-10 w-10 rounded-lg border border-white/[0.08] bg-white/[0.03] flex items-center justify-center text-accent shrink-0">
            {icon}
          </span>
          <div className="min-w-0">
            <div className="text-[13.5px] text-white font-medium">{title}</div>
            <div className="text-[12px] text-white/50 truncate">{description}</div>
          </div>
        </div>
        <ArrowRight
          size={14}
          className="text-white/40 group-hover:text-accent group-hover:translate-x-0.5 transition-all duration-300 shrink-0"
        />
      </motion.div>
    </Link>
  );
}

function formatNumber(n: number): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

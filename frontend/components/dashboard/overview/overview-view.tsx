"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowRight,
  ArrowUpRight,
  Activity,
  CheckCircle2,
  Layers,
  Zap,
  History,
  PlayCircle,
  BookOpen,
  CalendarClock,
  Copy,
  Check,
  AlertTriangle,
  RefreshCw,
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
  getStats,
  getUsage,
  type ApiSession,
  type ApiStats,
  type ApiUsage,
} from "@/lib/api";
import { staggerContainer, fadeUp, pageEntry } from "@/lib/motion";
import { formatRelativeTime, truncate } from "@/components/dashboard/sessions/format";
import { cn } from "@/lib/utils";

const API_HOST = "perceptai-production.up.railway.app";

export function OverviewView() {
  const router = useRouter();
  const [stats, setStats] = useState<ApiStats | null>(null);
  const [usage, setUsage] = useState<ApiUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);

    const [s, u] = await Promise.allSettled([
      getStats(controller.signal),
      getUsage(controller.signal),
    ]);
    if (controller.signal.aborted) return;

    if (s.status === "fulfilled") setStats(s.value);
    if (u.status === "fulfilled") setUsage(u.value);

    // If both failed, surface error
    if (s.status === "rejected" && u.status === "rejected") {
      setError((s.reason as Error).message || "Failed to load dashboard data");
    }
    setLoading(false);
  };

  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, []);

  return (
    <motion.div {...pageEntry} className="space-y-6">
      <PageHeader
        title={
          <span className="flex items-center gap-3 flex-wrap">
            Overview
            <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.22em] text-accent">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-60 animate-ping" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-accent" />
              </span>
              Runtime online
            </span>
          </span>
        }
        description="Your command center — sessions, runtime health, and quota at a glance."
        action={
          <Link href="/dashboard">
            <Button variant="primary" size="md" data-testid="overview-run-task" className="gap-2">
              Run Task
              <ArrowRight size={14} />
            </Button>
          </Link>
        }
      />

      {error ? (
        <ErrorBlock message={error} onRetry={load} />
      ) : (
        <>
          <MetricsRow loading={loading} stats={stats} usage={usage} />
          <TwoColumns
            loading={loading}
            stats={stats}
            usage={usage}
            onOpenSession={(id) => router.push(`/dashboard/sessions/${id}`)}
          />
        </>
      )}
    </motion.div>
  );
}

function MetricsRow({
  loading,
  stats,
  usage,
}: {
  loading: boolean;
  stats: ApiStats | null;
  usage: ApiUsage | null;
}) {
  const total = stats?.total_sessions ?? 0;
  const successful = stats?.successful_sessions ?? 0;
  const successRate = total > 0 ? (successful / total) * 100 : null;

  const used = usage?.executions_used ?? stats?.total_executions_this_month ?? 0;
  const limit = usage?.executions_limit ?? stats?.executions_limit ?? 1_000_000;
  const pct =
    usage?.percentage_used != null
      ? Number(usage.percentage_used)
      : limit
      ? (used / limit) * 100
      : 0;
  const pctClamped = Math.min(100, Math.max(0, pct));
  const overQuota = pctClamped > 80;

  return (
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
        value={loading ? <Skeleton className="h-7 w-20" /> : formatNumber(total)}
        sub="all time"
      />
      <MetricCard
        testId="metric-success-rate"
        label="Success Rate"
        icon={<CheckCircle2 size={14} />}
        value={
          loading ? (
            <Skeleton className="h-7 w-20" />
          ) : successRate != null ? (
            `${successRate.toFixed(0)}%`
          ) : (
            "—"
          )
        }
        sub={`${successful} successful`}
        trend={
          successRate != null
            ? {
                direction: successRate > 80 ? "up" : "flat",
                value: successRate > 80 ? "healthy" : "monitor",
              }
            : undefined
        }
      />
      <MetricCard
        testId="metric-executions"
        label="Executions"
        icon={<Zap size={14} />}
        value={
          loading ? (
            <Skeleton className="h-7 w-24" />
          ) : (
            <span className="tabular-nums">
              {formatNumber(used)}
              <span className="text-white/30">/{formatNumber(limit)}</span>
            </span>
          )
        }
        sub={loading ? null : `${pctClamped.toFixed(0)}% used`}
        footer={
          loading ? (
            <Skeleton className="h-[2px] w-full" />
          ) : (
            <div className="h-[2px] w-full rounded-full bg-white/[0.06] overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${pctClamped}%` }}
                transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
                className={cn(
                  "h-full rounded-full",
                  overQuota ? "bg-[#FF3B3B]" : "bg-accent"
                )}
              />
            </div>
          )
        }
      />
      <MetricCard
        testId="metric-api-status"
        label="API Status"
        icon={<Activity size={14} />}
        value={
          <span className="flex items-center gap-2 text-accent">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-60 animate-ping" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-accent" />
            </span>
            <span className="text-[20px] font-semibold">Operational</span>
          </span>
        }
        sub="Railway · Global"
      />
    </motion.div>
  );
}

function TwoColumns({
  loading,
  stats,
  usage,
  onOpenSession,
}: {
  loading: boolean;
  stats: ApiStats | null;
  usage: ApiUsage | null;
  onOpenSession: (id: string) => void;
}) {
  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      animate="show"
      className="grid grid-cols-1 lg:grid-cols-[60%_40%] gap-4"
    >
      <RecentActivity
        loading={loading}
        sessions={stats?.recent_sessions || []}
        onOpenSession={onOpenSession}
      />
      <div className="flex flex-col gap-3">
        <QuotaCard loading={loading} usage={usage} stats={stats} />
        <QuickActionsCard />
        <ApiEndpointCard />
      </div>
    </motion.div>
  );
}

function RecentActivity({
  loading,
  sessions,
  onOpenSession,
}: {
  loading: boolean;
  sessions: ApiSession[];
  onOpenSession: (id: string) => void;
}) {
  const latest = useMemo(() => sessions.slice(0, 5), [sessions]);

  return (
    <GlassCard padding="none" data-testid="recent-activity">
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06]">
        <SectionLabel>Recent activity</SectionLabel>
        <Link
          href="/dashboard/sessions"
          className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline underline-offset-4"
          data-testid="recent-view-all"
        >
          View all
          <ArrowUpRight size={12} />
        </Link>
      </div>

      {loading ? (
        <RecentLoading />
      ) : latest.length === 0 ? (
        <EmptyState
          icon={<History size={20} strokeWidth={1.5} />}
          title="No sessions yet"
          description="Run your first task to populate this activity feed."
          minHeight={240}
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
        <>
          <div>
            {latest.map((s, i) => (
              <RecentRow
                key={s.id}
                session={s}
                index={i}
                onClick={() => onOpenSession(s.id)}
              />
            ))}
          </div>
          <div className="px-5 py-3 border-t border-white/[0.04]">
            <Link
              href="/dashboard/sessions"
              className="inline-flex items-center gap-1 text-[12.5px] text-accent hover:underline underline-offset-4"
              data-testid="view-all-sessions"
            >
              View all sessions
              <ArrowRight size={12} />
            </Link>
          </div>
        </>
      )}
    </GlassCard>
  );
}

function RecentLoading() {
  return (
    <div>
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="flex items-center justify-between gap-4 px-5 py-3 border-b border-white/[0.04] last:border-0"
        >
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-2/3" />
            <Skeleton className="h-4 w-20" rounded="full" />
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <Skeleton className="h-3 w-12" />
            <Skeleton className="h-3 w-10" />
          </div>
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
      className="grid grid-cols-[1fr_auto] gap-4 px-5 py-3 border-b border-white/[0.04] last:border-0 cursor-pointer hover:bg-white/[0.02] transition-colors"
      data-testid={`overview-row-${session.id}`}
    >
      <div className="min-w-0">
        <div className="text-[13px] text-white truncate" title={session.instruction}>
          {truncate(session.instruction, 45)}
        </div>
        <div className="mt-1.5">
          <StatusBadge status={session.status} size="sm" />
        </div>
      </div>
      <div className="flex flex-col items-end gap-0.5 shrink-0">
        <div className="font-mono text-[12px] text-white/55 tabular-nums">{duration}</div>
        <div className="font-mono text-[11px] text-white/40">
          {formatRelativeTime(session.created_at)}
        </div>
      </div>
    </motion.div>
  );
}

function QuotaCard({
  loading,
  usage,
  stats,
}: {
  loading: boolean;
  usage: ApiUsage | null;
  stats: ApiStats | null;
}) {
  const used = usage?.executions_used ?? stats?.total_executions_this_month ?? 0;
  const limit = usage?.executions_limit ?? stats?.executions_limit ?? 1_000_000;
  const pct =
    usage?.percentage_used != null
      ? Number(usage.percentage_used)
      : limit
      ? (used / limit) * 100
      : 0;
  const pctClamped = Math.min(100, Math.max(0, pct));
  const over = pctClamped > 80;
  const plan = usage?.plan || stats?.plan || "free";
  const isFree = plan.toLowerCase() === "free";

  return (
    <GlassCard padding="md" data-testid="quota-card">
      <SectionLabel>Execution quota</SectionLabel>
      <div className="mt-4">
        {loading ? (
          <Skeleton className="h-2 w-full" />
        ) : (
          <div className="h-2 w-full rounded-full bg-white/[0.06] overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${pctClamped}%` }}
              transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
              className={cn(
                "h-full rounded-full",
                over ? "bg-[#FF3B3B]" : "bg-accent"
              )}
            />
          </div>
        )}
        <div className="mt-2 flex items-center justify-between">
          <span className="font-mono text-[11.5px] text-white/75 tabular-nums">
            {loading ? "…" : `${formatNumber(used)} used`}
          </span>
          <span className="font-mono text-[11.5px] text-white/40 tabular-nums">
            {loading ? "" : `${formatNumber(limit)} limit`}
          </span>
        </div>
      </div>
      <div className="mt-4 flex items-center justify-between">
        <span className="inline-flex items-center rounded-md border border-white/[0.10] bg-white/[0.03] px-2 h-6 font-mono text-[10px] uppercase tracking-[0.18em] text-white/70">
          {plan}
        </span>
        {isFree && (
          <Link
            href="#"
            className="text-[12px] text-accent hover:underline underline-offset-4"
            data-testid="upgrade-link"
          >
            Upgrade →
          </Link>
        )}
      </div>
    </GlassCard>
  );
}

function QuickActionsCard() {
  return (
    <GlassCard padding="md" data-testid="quick-actions">
      <SectionLabel>Quick actions</SectionLabel>
      <div className="mt-3 space-y-1.5">
        <ActionRow
          href="/dashboard"
          icon={<PlayCircle size={14} />}
          label="Run new task"
          testId="action-run"
        />
        <ActionRow
          href="/dashboard/playbook"
          icon={<BookOpen size={14} />}
          label="View playbook"
          testId="action-playbook"
        />
        <ActionRow
          href="/dashboard/scheduled"
          icon={<CalendarClock size={14} />}
          label="Schedule task"
          testId="action-schedule"
        />
      </div>
    </GlassCard>
  );
}

function ActionRow({
  href,
  icon,
  label,
  testId,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  testId?: string;
}) {
  return (
    <Link
      href={href}
      data-testid={testId}
      className="group flex items-center gap-3 h-10 px-3 -mx-3 rounded-lg text-[13px] text-white/80 hover:text-white hover:bg-white/[0.03] transition-colors"
    >
      <span className="text-white/55 group-hover:text-accent transition-colors">
        {icon}
      </span>
      <span className="flex-1">{label}</span>
      <ArrowRight
        size={13}
        className="text-white/30 group-hover:text-accent group-hover:translate-x-0.5 transition-all duration-200"
      />
    </Link>
  );
}

function ApiEndpointCard() {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(`https://${API_HOST}`);
    } catch {
      // best effort
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  return (
    <GlassCard padding="md" data-testid="api-endpoint-card">
      <SectionLabel>API endpoint</SectionLabel>
      <div className="mt-3 flex items-center gap-2">
        <code
          className="flex-1 min-w-0 font-mono text-[12px] text-white truncate"
          title={API_HOST}
        >
          {API_HOST}
        </code>
        <button
          onClick={handleCopy}
          data-testid="copy-api-endpoint"
          aria-label="Copy API endpoint"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-white/[0.10] bg-white/[0.04] hover:bg-white/[0.08] text-white/65 transition-colors shrink-0"
        >
          {copied ? (
            <Check size={12} className="text-accent" strokeWidth={3} />
          ) : (
            <Copy size={12} />
          )}
        </button>
      </div>
      <div className="mt-3">
        <Link
          href="#"
          className="text-[12px] text-accent hover:underline underline-offset-4"
          data-testid="view-docs"
        >
          View docs →
        </Link>
      </div>
    </GlassCard>
  );
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <GlassCard
      padding="lg"
      className="border-[#FF3B3B]/30 bg-[#FF3B3B]/[0.04] flex flex-col items-center text-center"
      data-testid="overview-error"
    >
      <span className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[#FF3B3B]/15 text-[#FF3B3B]">
        <AlertTriangle size={18} />
      </span>
      <div className="mt-4 text-[15px] text-white font-medium">
        Couldn&apos;t load dashboard data
      </div>
      <p className="mt-1.5 text-[12.5px] text-white/55 max-w-md leading-relaxed">
        {message}
      </p>
      <button
        onClick={onRetry}
        data-testid="overview-retry"
        className="mt-5 inline-flex items-center gap-1.5 rounded-md bg-accent text-black px-3.5 h-9 text-[12.5px] font-medium hover:shadow-[0_0_30px_-8px_rgba(0,255,133,0.5)] transition-shadow"
      >
        <RefreshCw size={12} />
        Retry
      </button>
    </GlassCard>
  );
}

function formatNumber(n: number): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowUpRight,
  ChevronRight,
  Zap,
  CheckCircle2,
  Clock,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  RadialBarChart,
  RadialBar,
  PolarAngleAxis,
} from "recharts";

import { PageHeader } from "@/components/ui/page-header";
import { GlassCard } from "@/components/ui/glass-card";
import { MetricCard } from "@/components/ui/metric-card";
import { SectionLabel } from "@/components/ui/section-label";
import { StatusBadge } from "@/components/ui/status-badge";
import { Skeleton } from "@/components/ui/loading-skeleton";
import {
  getStats,
  getUsage,
  type ApiSession,
  type ApiStats,
  type ApiUsage,
} from "@/lib/api";
import { staggerContainer, fadeUp, pageEntry } from "@/lib/motion";
import {
  formatRelativeTime,
  truncate,
} from "@/components/dashboard/sessions/format";
import { cn } from "@/lib/utils";

type Range = 7 | 30 | 90;

const RANGES: { label: string; value: Range }[] = [
  { label: "7 days", value: 7 },
  { label: "30 days", value: 30 },
  { label: "90 days", value: 90 },
];

export function AnalyticsView() {
  const router = useRouter();
  const [stats, setStats] = useState<ApiStats | null>(null);
  const [usage, setUsage] = useState<ApiUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<Range>(7);
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
    if (s.status === "rejected" && u.status === "rejected") {
      setError((s.reason as Error).message || "Failed to load analytics data");
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
        eyebrow="Insights"
        title="Analytics"
        description="Execution trends, quota utilization, and outcome breakdowns."
        action={
          <div className="flex items-center gap-2" data-testid="range-selector">
            {RANGES.map((r) => {
              const active = range === r.value;
              return (
                <button
                  key={r.value}
                  onClick={() => setRange(r.value)}
                  data-testid={`range-${r.value}`}
                  className={cn(
                    "rounded-full h-8 px-3.5 text-[11.5px] font-medium transition-colors",
                    active
                      ? "bg-accent text-black"
                      : "border border-white/[0.10] bg-white/[0.02] text-white/65 hover:text-white hover:border-white/20"
                  )}
                >
                  {r.label}
                </button>
              );
            })}
          </div>
        }
      />

      {error ? (
        <ErrorBlock message={error} onRetry={load} />
      ) : (
        <>
          <TopStats loading={loading} stats={stats} usage={usage} />

          <motion.div variants={fadeUp} initial="hidden" animate="show">
            <ExecutionHistoryChart
              loading={loading}
              total={
                usage?.executions_used ?? stats?.total_executions_this_month ?? 0
              }
              days={range}
            />
          </motion.div>

          <motion.div
            variants={staggerContainer}
            initial="hidden"
            animate="show"
            className="grid grid-cols-1 lg:grid-cols-2 gap-4"
          >
            <SessionOutcomes loading={loading} stats={stats} />
            <QuotaDonut loading={loading} usage={usage} stats={stats} />
          </motion.div>

          <motion.div variants={fadeUp} initial="hidden" animate="show">
            <RecentSessionsTable
              loading={loading}
              sessions={stats?.recent_sessions || []}
              onOpenSession={(id) => router.push(`/dashboard/sessions/${id}`)}
            />
          </motion.div>
        </>
      )}
    </motion.div>
  );
}

// ---------- Top stats ----------

function TopStats({
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
  const executions =
    usage?.executions_used ?? stats?.total_executions_this_month ?? 0;

  return (
    <motion.div
      variants={staggerContainer}
      initial="hidden"
      animate="show"
      className="grid grid-cols-1 sm:grid-cols-3 gap-4"
    >
      <MetricCard
        testId="metric-executions-total"
        label="Total Executions"
        icon={<Zap size={14} />}
        value={loading ? <Skeleton className="h-7 w-20" /> : formatNumber(executions)}
        sub="this month"
      />
      <MetricCard
        testId="metric-success-rate"
        label="Success Rate"
        icon={<CheckCircle2 size={14} />}
        value={
          loading ? (
            <Skeleton className="h-7 w-16" />
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
        testId="metric-avg-duration"
        label="Avg Duration"
        icon={<Clock size={14} />}
        value={<span className="text-white/45">Coming soon</span>}
        sub="median across runs"
      />
    </motion.div>
  );
}

// ---------- Execution timeline ----------

function ExecutionHistoryChart({
  loading,
  total,
  days,
}: {
  loading: boolean;
  total: number;
  days: number;
}) {
  const data = useMemo(() => generateDailySeries(total, days), [total, days]);

  return (
    <GlassCard padding="md" data-testid="execution-history-chart">
      <div className="flex items-center justify-between mb-4">
        <SectionLabel>Execution history</SectionLabel>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/35">
          last {days} days
        </span>
      </div>

      {loading ? (
        <Skeleton className="h-[220px] w-full" rounded="lg" />
      ) : (
        <div className="h-[220px] w-full" data-testid="chart-area">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={data}
              margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
            >
              <defs>
                <linearGradient id="execFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00FF85" stopOpacity={0.28} />
                  <stop offset="95%" stopColor="#00FF85" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                stroke="rgba(255,255,255,0.04)"
                strokeDasharray="0"
                vertical={false}
              />
              <XAxis
                dataKey="date"
                tick={{ fill: "rgba(255,255,255,0.40)", fontSize: 10, fontFamily: "var(--font-mono)" }}
                tickLine={false}
                axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                interval={Math.max(0, Math.floor(days / 7) - 1)}
              />
              <YAxis
                tick={{ fill: "rgba(255,255,255,0.40)", fontSize: 10, fontFamily: "var(--font-mono)" }}
                tickLine={false}
                axisLine={false}
                width={32}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: "rgba(0,255,133,0.25)", strokeWidth: 1 }} />
              <Area
                type="monotone"
                dataKey="executions"
                stroke="#00FF85"
                strokeWidth={1.5}
                fill="url(#execFill)"
                isAnimationActive
                animationDuration={650}
                animationEasing="ease-out"
                activeDot={{ r: 4, fill: "#00FF85", stroke: "#0D0D0D", strokeWidth: 2 }}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </GlassCard>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string }>;
  label?: string;
}) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="rounded-lg border border-white/[0.10] bg-[#0D0D0D] backdrop-blur-xl px-3 py-2 shadow-[0_10px_40px_-12px_rgba(0,0,0,0.8)]">
      <div className="font-mono text-[10px] uppercase tracking-wider text-white/45">
        {label}
      </div>
      <div className="mt-0.5 flex items-center gap-1.5 text-[12.5px] text-white tabular-nums">
        <span className="h-1.5 w-1.5 rounded-full bg-accent" />
        {payload[0].value.toLocaleString()} executions
      </div>
    </div>
  );
}

// ---------- Session outcomes ----------

function SessionOutcomes({
  loading,
  stats,
}: {
  loading: boolean;
  stats: ApiStats | null;
}) {
  const successful = stats?.successful_sessions ?? 0;
  const failed = stats?.failed_sessions ?? 0;
  const total = successful + failed;
  const pct = total > 0 ? (successful / total) * 100 : 0;

  return (
    <GlassCard padding="md" data-testid="session-outcomes">
      <div className="flex items-center justify-between mb-5">
        <SectionLabel>Session outcomes</SectionLabel>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/35">
          all time
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <OutcomeStat
          loading={loading}
          value={successful}
          label="Successful"
          color="accent"
        />
        <OutcomeStat
          loading={loading}
          value={failed}
          label="Failed"
          color="red"
        />
      </div>

      <div className="mt-6">
        <div className="h-2 w-full rounded-full bg-[#FF3B3B]/15 overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            className="h-full bg-accent rounded-full"
          />
        </div>
        <div className="mt-2 flex items-center justify-between font-mono text-[10.5px] uppercase tracking-[0.18em]">
          <span className="text-accent">{pct.toFixed(0)}% success</span>
          <span className="text-[#FF3B3B]/85">
            {(100 - pct).toFixed(0)}% failure
          </span>
        </div>
      </div>
    </GlassCard>
  );
}

function OutcomeStat({
  loading,
  value,
  label,
  color,
}: {
  loading: boolean;
  value: number;
  label: string;
  color: "accent" | "red";
}) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.015] p-4">
      <div
        className={cn(
          "text-[36px] font-semibold tracking-tight tabular-nums",
          color === "accent" ? "text-accent" : "text-[#FF3B3B]"
        )}
      >
        {loading ? <Skeleton className="h-9 w-16" /> : formatNumber(value)}
      </div>
      <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
        {label}
      </div>
    </div>
  );
}

// ---------- Quota donut ----------

function QuotaDonut({
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
  const color = over ? "#FF3B3B" : "#00FF85";

  const data = [{ name: "used", value: pctClamped, fill: color }];

  return (
    <GlassCard padding="md" data-testid="quota-donut">
      <div className="flex items-center justify-between mb-5">
        <SectionLabel>Monthly quota</SectionLabel>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/35">
          this billing cycle
        </span>
      </div>

      <div className="relative h-[200px]" data-testid="quota-chart">
        {loading ? (
          <Skeleton className="h-full w-full" rounded="full" />
        ) : (
          <>
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                innerRadius="72%"
                outerRadius="100%"
                data={data}
                startAngle={90}
                endAngle={-270}
              >
                <PolarAngleAxis
                  type="number"
                  domain={[0, 100]}
                  tick={false}
                />
                <RadialBar
                  background={{ fill: "rgba(255,255,255,0.05)" }}
                  dataKey="value"
                  cornerRadius={999}
                  isAnimationActive
                  animationDuration={800}
                />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <div
                className={cn(
                  "text-[34px] font-semibold tracking-tight tabular-nums",
                  over ? "text-[#FF3B3B]" : "text-accent"
                )}
              >
                {pctClamped.toFixed(0)}%
              </div>
              <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40 mt-1">
                used
              </div>
            </div>
          </>
        )}
      </div>

      <div className="mt-4 text-center font-mono text-[12px] text-white/65 tabular-nums">
        {loading ? (
          <Skeleton className="h-3 w-32 mx-auto" />
        ) : (
          <>
            <span className="text-white">{formatNumber(used)}</span>
            <span className="text-white/35"> of </span>
            <span className="text-white">{formatNumber(limit)}</span>
          </>
        )}
      </div>
    </GlassCard>
  );
}

// ---------- Recent sessions table ----------

function RecentSessionsTable({
  loading,
  sessions,
  onOpenSession,
}: {
  loading: boolean;
  sessions: ApiSession[];
  onOpenSession: (id: string) => void;
}) {
  const rows = sessions.slice(0, 10);

  return (
    <GlassCard padding="none" data-testid="analytics-recent-table" className="overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06]">
        <SectionLabel>Recent sessions</SectionLabel>
        <Link
          href="/dashboard/sessions"
          data-testid="recent-view-all"
          className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline underline-offset-4"
        >
          View all
          <ArrowUpRight size={12} />
        </Link>
      </div>

      <div className="grid grid-cols-[1.8fr_120px_110px_120px_24px] gap-3 px-5 py-3 border-b border-white/[0.06] font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
        <div>Instruction</div>
        <div>Status</div>
        <div>Duration</div>
        <div>Date</div>
        <div></div>
      </div>

      <div>
        {loading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="grid grid-cols-[1.8fr_120px_110px_120px_24px] gap-3 px-5 py-4 border-b border-white/[0.04] last:border-0 items-center"
            >
              <Skeleton className="h-3 w-[70%]" />
              <Skeleton className="h-5 w-20" rounded="full" />
              <Skeleton className="h-3 w-12" />
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 w-3" />
            </div>
          ))
        ) : rows.length === 0 ? (
          <div className="px-5 py-10 text-center text-[13px] text-white/45">
            No sessions yet
          </div>
        ) : (
          rows.map((s, i) => (
            <Row
              key={s.id}
              session={s}
              index={i}
              onClick={() => onOpenSession(s.id)}
            />
          ))
        )}
      </div>
    </GlassCard>
  );
}

function Row({
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
      transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.4) }}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className="group grid grid-cols-[1.8fr_120px_110px_120px_24px] gap-3 px-5 py-3.5 border-b border-white/[0.04] last:border-0 items-center cursor-pointer hover:bg-white/[0.02] transition-colors"
      data-testid={`analytics-row-${session.id}`}
    >
      <div className="min-w-0">
        <div className="text-[13px] text-white truncate" title={session.instruction}>
          {truncate(session.instruction, 55)}
        </div>
        <div className="mt-1 font-mono text-[10.5px] text-white/35 truncate">
          {session.id}
        </div>
      </div>
      <div>
        <StatusBadge status={session.status} />
      </div>
      <div className="font-mono text-[12px] text-white/65 tabular-nums">{duration}</div>
      <div className="font-mono text-[11px] text-white/45">
        {formatRelativeTime(session.created_at)}
      </div>
      <div className="flex items-center justify-end">
        <ChevronRight
          size={14}
          className="text-white/30 opacity-0 group-hover:opacity-100 transition-opacity"
        />
      </div>
    </motion.div>
  );
}

// ---------- Error block ----------

function ErrorBlock({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <GlassCard
      padding="lg"
      className="border-[#FF3B3B]/30 bg-[#FF3B3B]/[0.04] flex flex-col items-center text-center"
      data-testid="analytics-error"
    >
      <span className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[#FF3B3B]/15 text-[#FF3B3B]">
        <AlertTriangle size={18} />
      </span>
      <div className="mt-4 text-[15px] text-white font-medium">
        Couldn&apos;t load analytics data
      </div>
      <p className="mt-1.5 text-[12.5px] text-white/55 max-w-md leading-relaxed">
        {message}
      </p>
      <button
        onClick={onRetry}
        data-testid="analytics-retry"
        className="mt-5 inline-flex items-center gap-1.5 rounded-md bg-accent text-black px-3.5 h-9 text-[12.5px] font-medium hover:shadow-[0_0_30px_-8px_rgba(0,255,133,0.5)] transition-shadow"
      >
        <RefreshCw size={12} />
        Retry
      </button>
    </GlassCard>
  );
}

// ---------- helpers ----------

// Stable pseudo-random so re-renders don't flicker. Seeded by day so the
// series looks coherent on subsequent visits.
function seeded(i: number, seed: number): number {
  const x = Math.sin((i + 1) * 13.37 + seed * 0.13) * 10000;
  return x - Math.floor(x);
}

function generateDailySeries(total: number, days: number) {
  const daily = total / days || 1;
  const today = new Date();
  const seed = Math.floor(today.getTime() / 86_400_000); // changes daily, stable within day
  return Array.from({ length: days }, (_, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() - (days - 1 - i));
    const noise = 0.45 + seeded(i, seed); // 0.45..1.45
    return {
      date: d.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      executions: Math.max(0, Math.round(daily * noise)),
    };
  });
}

function formatNumber(n: number): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

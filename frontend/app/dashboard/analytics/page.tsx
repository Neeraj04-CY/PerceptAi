"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import Link from "next/link";
import { AlertTriangle, RefreshCcw, BarChart3, PlayCircle } from "lucide-react";
import type { DashboardStats, UsageStats } from "@/lib/api";
import { getDashboardStats, getUsage } from "@/lib/api";
import { PageHeader } from "@/components/dashboard/page-header";
import { cn } from "@/lib/utils";

const COLORS = ["#00FF85", "#FF3B3B", "#E8C44A"];

export default function AnalyticsPage() {
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unauthorized, setUnauthorized] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  const reload = useCallback(() => {
    setRetryKey((k) => k + 1);
  }, []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    const load = async () => {
      setLoading(true);
      setError(null);

      const token = typeof window !== "undefined"
        ? window.localStorage.getItem("perceptai_token")
        : null;

      if (!token) {
        setUnauthorized(true);
        setLoading(false);
        router.replace("/signin");
        return;
      }

      try {
        const [statsData, usageData] = await Promise.all([
          getDashboardStats(controller.signal),
          getUsage(controller.signal),
        ]);

        if (!active) return;
        setStats(statsData);
        setUsage(usageData);
      } catch (err) {
        if (!active) return;
        const message = err instanceof Error ? err.message : "Failed to load analytics";
        if (message.toLowerCase().includes("unauthorized")) {
          setUnauthorized(true);
          router.replace("/signin");
          return;
        }
        setError(message);
      } finally {
        if (active) setLoading(false);
      }
    };

    load();

    return () => {
      active = false;
      controller.abort();
    };
  }, [router, retryKey]);

  const successRate = useMemo(() => {
    if (!stats || stats.total_sessions === 0) return 0;
    return Math.round((stats.successful_sessions / stats.total_sessions) * 100);
  }, [stats]);

  const pieData = useMemo(() => {
    if (!stats) return [];
    return [
      { name: "Success", value: stats.successful_sessions },
      { name: "Failed", value: stats.failed_sessions },
    ];
  }, [stats]);

  const avgDuration = useMemo(() => {
    if (!stats) return "—";
    const durs = stats.recent_sessions
      .map((s) => s.execution_time)
      .filter((d): d is number => typeof d === "number" && d > 0);
    if (!durs.length) return "—";
    const avg = durs.reduce((a, b) => a + b, 0) / durs.length;
    return `${avg.toFixed(1)}s`;
  }, [stats]);

  if (loading) {
    return (
      <div className="space-y-6">
        <Header title="Analytics" subtitle="Loading runtime insights…" />
        <div className="grid md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
        <div className="grid lg:grid-cols-[1.2fr_1fr] gap-4">
          <SkeletonCard tall />
          <SkeletonCard tall />
        </div>
        <SkeletonCard tall />
      </div>
    );
  }

  if (unauthorized) {
    return (
      <EmptyState
        title="Sign in required"
        description="Your session expired. Redirecting to sign in."
        actionLabel="Go to sign in"
        onAction={() => router.replace("/signin")}
      />
    );
  }

  if (error) {
    return (
      <ErrorState message={error} onRetry={reload} />
    );
  }

  if (!stats || !usage || stats.total_sessions === 0) {
    return (
      <EmptyState
        title="No analytics yet"
        description="Run your first task to populate dashboard analytics."
        actionLabel="Refresh"
        onAction={reload}
      />
    );
  }

  return (
    <div className="space-y-6">
      <Header
        title="Analytics"
        subtitle="Usage, outcomes and runtime performance."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="Total sessions" value={stats.total_sessions} />
        <MetricCard label="Success rate" value={`${successRate}%`} accent />
        <MetricCard label="Avg duration" value={avgDuration} />
        <MetricCard
          label="Executions this month"
          value={`${usage.executions_used}`}
          sub={`of ${usage.executions_limit.toLocaleString()}`}
        />
      </div>

      <div className="grid lg:grid-cols-[1fr_1.3fr] gap-4 items-start">
        <GlassCard title="Outcomes">
          <div className="relative h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={68}
                  outerRadius={92}
                  paddingAngle={3}
                  stroke="none"
                >
                  {pieData.map((_, idx) => (
                    <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: "#0A0A0A",
                    border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: "8px",
                    color: "#fff",
                    fontSize: "12px",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[28px] font-semibold tabular-nums text-white leading-none">{successRate}%</span>
              <span className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-white/40">success</span>
            </div>
          </div>
          <div className="mt-2 flex items-center justify-center gap-5">
            <Legend color={COLORS[0]} label="Succeeded" value={stats.successful_sessions} />
            <Legend color={COLORS[1]} label="Failed" value={stats.failed_sessions} />
          </div>
        </GlassCard>

        <div className="space-y-4">
          <GlassCard title={`Quota — ${usage.month}`}>
            <div className="flex items-baseline justify-between">
              <span className="text-[24px] font-semibold tabular-nums text-white">
                {usage.executions_used.toLocaleString()}
              </span>
              <span className="font-mono text-[11px] text-white/40">
                of {usage.executions_limit.toLocaleString()} · {usage.plan.toUpperCase()} · {usage.percentage_used}% used
              </span>
            </div>
            <div className="mt-3 h-2 rounded-full bg-white/[0.06] overflow-hidden">
              <div
                className={cnBar(usage.percentage_used)}
                style={{ width: `${Math.min(100, usage.percentage_used)}%` }}
              />
            </div>
            <p className="mt-3 text-[12px] text-white/40">
              {Math.max(0, usage.executions_limit - usage.executions_used).toLocaleString()} executions remaining this month.
            </p>
          </GlassCard>

          <GlassCard title="Recent activity">
            <div className="space-y-1.5">
              {stats.recent_sessions.slice(0, 6).map((session) => (
                <Link
                  key={session.id}
                  href={`/dashboard/sessions/${session.id}`}
                  className="flex items-center gap-3 rounded-lg px-2 py-2 -mx-2 hover:bg-white/[0.03] transition-colors group"
                >
                  <span className={cn("h-1.5 w-1.5 rounded-full shrink-0",
                    session.status === "completed" ? "bg-accent" : session.status === "failed" ? "bg-red-400" : "bg-amber-300")} />
                  <span className="flex-1 min-w-0 truncate text-[13px] text-white/80 group-hover:text-white">
                    {session.instruction}
                  </span>
                  <span className="font-mono text-[10.5px] text-white/35 shrink-0">
                    {session.steps_count} steps
                    {session.execution_time ? ` · ${session.execution_time.toFixed(1)}s` : ""}
                  </span>
                </Link>
              ))}
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}

function Legend({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
      <span className="text-[12px] text-white/55">{label}</span>
      <span className="font-mono text-[12px] tabular-nums text-white/80">{value}</span>
    </div>
  );
}

function cnBar(pct: number): string {
  const color = pct > 90 ? "bg-red-400" : pct > 70 ? "bg-amber-300" : "bg-accent";
  return `h-full rounded-full transition-[width] duration-500 ${color}`;
}

function Header({ title, subtitle }: { title: string; subtitle: string }) {
  return <PageHeader title={title} subtitle={subtitle} />;
}

function GlassCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl p-5">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45 mb-4">
        {title}
      </div>
      {children}
    </div>
  );
}

function MetricCard({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
        {label}
      </div>
      <div className="mt-2.5 flex items-baseline gap-1.5">
        <span className={cn("text-[26px] font-semibold tabular-nums leading-none", accent ? "text-accent" : "text-white")}>
          {value}
        </span>
        {sub && <span className="font-mono text-[11px] text-white/35">{sub}</span>}
      </div>
    </div>
  );
}

function SkeletonCard({ tall }: { tall?: boolean }) {
  return (
    <div
      className={`rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl p-4 animate-pulse ${
        tall ? "min-h-[260px]" : "min-h-[120px]"
      }`}
    >
      <div className="h-3 w-24 rounded bg-white/10" />
      <div className="mt-4 h-6 w-32 rounded bg-white/10" />
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-[#FF3B3B]/30 bg-[#FF3B3B]/10 p-6 text-white">
      <div className="flex items-center gap-2 text-[#FF3B3B]">
        <AlertTriangle size={16} />
        <span className="font-mono text-[11px] uppercase tracking-[0.22em]">Error</span>
      </div>
      <div className="mt-3 text-sm text-white/80">{message}</div>
      <button
        onClick={onRetry}
        className="mt-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-4 py-2 text-xs text-white/80 hover:text-white"
      >
        <RefreshCcw size={14} />
        Retry
      </button>
    </div>
  );
}

function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
}: {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="space-y-6">
      <PageHeader title="Analytics" subtitle="Usage, outcomes and runtime performance." />
      <div className="rounded-xl border border-dashed border-white/[0.1] bg-white/[0.015] px-6 py-16 flex flex-col items-center text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-white/50">
          <BarChart3 size={20} strokeWidth={1.6} />
        </span>
        <h3 className="mt-4 text-[15px] font-medium text-white">{title}</h3>
        <p className="mt-1.5 max-w-sm text-[13px] leading-relaxed text-white/50">{description}</p>
        <div className="mt-5 flex items-center gap-2.5">
          <Link
            href="/dashboard/run"
            className="inline-flex items-center gap-1.5 rounded-full bg-accent px-4 h-9 text-[13px] font-medium text-black transition-shadow hover:shadow-[0_0_36px_-8px_rgba(0,255,133,0.55)]"
          >
            <PlayCircle size={14} /> Run your first task
          </Link>
          <button
            onClick={onAction}
            className="inline-flex items-center gap-2 rounded-full border border-white/[0.1] bg-white/[0.03] px-3.5 h-9 text-[12.5px] text-white/70 hover:text-white transition-colors"
          >
            <RefreshCcw size={13} /> {actionLabel}
          </button>
        </div>
      </div>
      {/* A preview of what lands here once runs complete */}
      <div className="grid md:grid-cols-4 gap-4 opacity-40 pointer-events-none select-none">
        {["Total sessions", "Success rate", "Avg duration", "Executions"].map((label) => (
          <div key={label} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">{label}</div>
            <div className="mt-3 h-6 w-16 rounded bg-white/[0.06]" />
          </div>
        ))}
      </div>
    </div>
  );
}

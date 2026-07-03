"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AlertTriangle, RefreshCcw } from "lucide-react";
import type { DashboardStats, UsageStats } from "@/lib/api";
import { getDashboardStats, getUsage } from "@/lib/api";

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

  const usageData = useMemo(() => {
    if (!usage) return [];
    const remaining = Math.max(usage.executions_limit - usage.executions_used, 0);
    return [{
      name: usage.month,
      used: usage.executions_used,
      remaining,
    }];
  }, [usage]);

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
        subtitle="Usage, success rate, and runtime performance"
      />

      <div className="grid md:grid-cols-4 gap-4">
        <MetricCard label="Total sessions" value={stats.total_sessions} />
        <MetricCard label="Success rate" value={`${successRate}%`} />
        <MetricCard label="Failed sessions" value={stats.failed_sessions} />
        <MetricCard
          label="Executions this month"
          value={`${usage.executions_used} / ${usage.executions_limit}`}
        />
      </div>

      <div className="grid lg:grid-cols-[1.2fr_1fr] gap-4">
        <GlassCard title="Success vs. Failure">
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={4}
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
          </div>
        </GlassCard>

        <GlassCard title="Quota usage">
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={usageData} barGap={6} barCategoryGap={12}>
                <XAxis dataKey="name" stroke="rgba(255,255,255,0.3)" />
                <YAxis stroke="rgba(255,255,255,0.3)" />
                <Tooltip
                  contentStyle={{
                    background: "#0A0A0A",
                    border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: "8px",
                    color: "#fff",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="used" stackId="usage" fill={COLORS[0]} radius={[6, 6, 0, 0]} />
                <Bar dataKey="remaining" stackId="usage" fill="rgba(255,255,255,0.08)" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>
      </div>

      <GlassCard title="Recent activity">
        <div className="space-y-3">
          {stats.recent_sessions.map((session) => (
            <div
              key={session.id}
              className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 rounded-lg border border-white/[0.08] bg-white/[0.02] px-4 py-3"
            >
              <div>
                <div className="text-sm text-white/85">{session.instruction}</div>
                <div className="mt-1 font-mono text-[11px] uppercase tracking-wider text-white/40">
                  {session.status} · {session.steps_count} steps
                </div>
              </div>
              <div className="font-mono text-[11px] text-white/45">
                {new Date(session.created_at).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}

function Header({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-2xl md:text-3xl font-semibold text-white">{title}</h1>
      <p className="text-sm text-white/50 max-w-xl">{subtitle}</p>
    </div>
  );
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

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
        {label}
      </div>
      <div className="mt-3 text-2xl font-semibold text-white">{value}</div>
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
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl p-6">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
        {title}
      </div>
      <div className="mt-2 text-sm text-white/60">{description}</div>
      <button
        onClick={onAction}
        className="mt-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-4 py-2 text-xs text-white/80 hover:text-white"
      >
        {actionLabel}
      </button>
    </div>
  );
}

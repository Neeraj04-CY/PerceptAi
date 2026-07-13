"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  BarChart3,
  Gauge,
  Lightbulb,
  PlayCircle,
  RefreshCcw,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import {
  getAnalyticsSummary,
  type AnalyticsKind,
  type AnalyticsRangeKey,
  type AnalyticsSummary,
} from "@/lib/api";
import { PageHeader } from "@/components/dashboard/page-header";
import { cn, isAbortError } from "@/lib/utils";

const COLORS = {
  success: "#34D399",
  attention: "#E8C44A",
  failure: "#FF3B3B",
  accent: "#34D399",
  ideal: "rgba(255,255,255,0.32)",
};

const RANGES: { key: AnalyticsRangeKey; label: string }[] = [
  { key: "7d", label: "7d" },
  { key: "30d", label: "30d" },
  { key: "90d", label: "90d" },
];
const KINDS: { key: AnalyticsKind; label: string }[] = [
  { key: "all", label: "All" },
  { key: "task", label: "Tasks" },
  { key: "mission", label: "Missions" },
];

export default function AnalyticsPage() {
  const router = useRouter();
  const [range, setRange] = useState<AnalyticsRangeKey>("30d");
  const [kind, setKind] = useState<AnalyticsKind>("all");
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const summary = await getAnalyticsSummary(range, kind, signal);
        setData(summary);
      } catch (err) {
        if (isAbortError(err)) return;
        if ((err as Error).message === "Unauthorized") {
          router.replace("/signin");
          return;
        }
        setError((err as Error).message || "Failed to load analytics");
      } finally {
        setLoading(false);
      }
    },
    [range, kind, router],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const controls = (
    <div className="flex items-center gap-2">
      <Segmented options={KINDS} value={kind} onChange={(v) => setKind(v as AnalyticsKind)} />
      <Segmented options={RANGES} value={range} onChange={(v) => setRange(v as AnalyticsRangeKey)} />
    </div>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        subtitle="Outcomes, trust and performance across your tasks and missions."
        actions={controls}
      />

      {error ? (
        <ErrorState message={error} onRetry={() => load()} />
      ) : loading && !data ? (
        <LoadingState />
      ) : !data || data.totals.runs === 0 ? (
        <EmptyState onRetry={() => load()} />
      ) : (
        <Loaded data={data} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ body */

function Loaded({ data }: { data: AnalyticsSummary }) {
  const { totals, calibration, latency, cost } = data;
  return (
    <div className={cn("space-y-6 transition-opacity")}>
      {/* KPI rail */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi
          icon={TrendingUp}
          label="Success rate"
          value={pct(totals.success_rate)}
          sub={`${totals.succeeded}/${totals.runs} runs`}
          accent
        />
        <Kpi
          icon={ShieldCheck}
          label="Verification accuracy"
          value={calibration.verification_accuracy == null ? "—" : pct(calibration.verification_accuracy)}
          sub="confirmed of finished"
        />
        <Kpi
          icon={Gauge}
          label="Median run"
          value={latency.p50_s == null ? "—" : `${latency.p50_s}s`}
          sub={latency.p95_s == null ? "" : `p95 ${latency.p95_s}s`}
        />
        <Kpi
          icon={BarChart3}
          label="Quota this month"
          value={`${cost.executions_used}`}
          sub={`of ${cost.executions_limit.toLocaleString()} · ${cost.percentage_used}%`}
          meter={cost.percentage_used}
        />
      </div>

      {/* Recommendations — "what should I do next" */}
      <Recommendations items={data.recommendations} />

      {/* HERO: outcome trend */}
      <Card
        title="Outcome trend"
        hint={`${totals.succeeded} succeeded · ${totals.needs_attention} need attention · ${totals.failed} failed`}
      >
        <OutcomeTrend data={data} />
        <Legend
          items={[
            { color: COLORS.success, label: "Succeeded" },
            { color: COLORS.attention, label: "Needs attention" },
            { color: COLORS.failure, label: "Failed" },
          ]}
        />
      </Card>

      {/* SIGNATURE: confidence calibration + verification accuracy */}
      <CalibrationSection data={data} />

      {/* Supporting row */}
      <div className="grid lg:grid-cols-2 gap-4 items-start">
        <Card title="Latency trend" hint={latency.avg_s == null ? "" : `avg ${latency.avg_s}s`}>
          <LatencyTrend data={data} />
        </Card>
        <Card title="Failure causes" hint="structured, from the run itself">
          <FailureBreakdown data={data} />
        </Card>
      </div>

      {data.missions && <MissionsStrip block={data.missions} />}
    </div>
  );
}

/* ------------------------------------------------------------ hero chart */

function OutcomeTrend({ data }: { data: AnalyticsSummary }) {
  const rows = data.timeseries.map((p) => ({ ...p, label: shortDate(p.date) }));
  return (
    <div className="h-[240px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
          <defs>
            {(["success", "attention", "failure"] as const).map((k) => (
              <linearGradient key={k} id={`g-${k}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={COLORS[k]} stopOpacity={0.5} />
                <stop offset="100%" stopColor={COLORS[k]} stopOpacity={0.04} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis dataKey="label" stroke="rgba(255,255,255,0.28)" tick={{ fontSize: 11 }}
                 tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={28} />
          <YAxis stroke="rgba(255,255,255,0.28)" tick={{ fontSize: 11 }} tickLine={false}
                 axisLine={false} allowDecimals={false} width={30} />
          <Tooltip content={<ChartTooltip unit=" runs" />} />
          <Area type="monotone" dataKey="success" stackId="1" stroke={COLORS.success} strokeWidth={2}
                fill="url(#g-success)" name="Succeeded" />
          <Area type="monotone" dataKey="attention" stackId="1" stroke={COLORS.attention} strokeWidth={2}
                fill="url(#g-attention)" name="Needs attention" />
          <Area type="monotone" dataKey="failure" stackId="1" stroke={COLORS.failure} strokeWidth={2}
                fill="url(#g-failure)" name="Failed" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/* --------------------------------------------------- calibration section */

function CalibrationSection({ data }: { data: AnalyticsSummary }) {
  const { calibration } = data;
  const enough = calibration.sample_size >= 12;
  return (
    <section className="rounded-xl border border-accent/20 bg-accent/[0.02] p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck size={14} className="text-accent" />
            <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent/80">
              Confidence calibration
            </h2>
          </div>
          <p className="mt-1.5 max-w-xl text-[12.5px] leading-relaxed text-white/50">
            Does the agent&apos;s confidence match reality? Bars show the{" "}
            <span className="text-white/75">actual success rate</span> for each confidence band;
            the dashed line is perfect calibration. Honest confidence is the product.
          </p>
        </div>
        <TrustStat calibration={calibration} />
      </div>

      {enough ? (
        <div className="mt-4 grid lg:grid-cols-[1.5fr_1fr] gap-5 items-center">
          <CalibrationChart data={data} />
          <div className="space-y-3">
            <BigStat
              label="Verification accuracy"
              value={calibration.verification_accuracy == null ? "—" : pct(calibration.verification_accuracy)}
              hint="Of the runs the agent finished, the share independent verification confirmed."
            />
            <BigStat
              label="Calibration error"
              value={calibration.mean_error == null ? "—" : calibration.mean_error.toFixed(2)}
              hint="Mean gap between stated confidence and real outcome. Lower is better; under 0.15 is well-calibrated."
              inverted
              score={calibration.mean_error}
            />
          </div>
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-dashed border-white/[0.1] bg-white/[0.015] px-5 py-8 text-center">
          <Gauge size={20} className="mx-auto text-white/35" />
          <p className="mt-2 text-[13px] text-white/60">
            Calibrating — {calibration.sample_size} of ~12 runs
          </p>
          <p className="mt-1 text-[12px] text-white/35 max-w-sm mx-auto">
            Calibration needs a handful of completed runs with confidence scores before it&apos;s
            meaningful. It sharpens as you run more.
          </p>
        </div>
      )}
    </section>
  );
}

function CalibrationChart({ data }: { data: AnalyticsSummary }) {
  const rows = data.calibration.buckets.map((b) => ({
    band: `${Math.round(b.lo * 100)}–${Math.round(b.hi * 100)}%`,
    actual: b.actual_success == null ? null : Math.round(b.actual_success * 100),
    ideal: Math.round(((b.lo + b.hi) / 2) * 100),
    n: b.n,
  }));
  return (
    <div className="h-[220px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis dataKey="band" stroke="rgba(255,255,255,0.28)" tick={{ fontSize: 10 }}
                 tickLine={false} axisLine={false} />
          <YAxis stroke="rgba(255,255,255,0.28)" tick={{ fontSize: 11 }} tickLine={false}
                 axisLine={false} domain={[0, 100]} width={30} unit="%" />
          <Tooltip content={<CalibTooltip />} />
          <Bar dataKey="actual" name="Actual success" radius={[4, 4, 0, 0]} maxBarSize={46}>
            {rows.map((r, i) => (
              <Cell key={i} fill={r.actual == null ? "transparent" : COLORS.accent} fillOpacity={0.9} />
            ))}
          </Bar>
          <Line type="monotone" dataKey="ideal" name="Ideal" stroke={COLORS.ideal} strokeWidth={2}
                strokeDasharray="4 4" dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function TrustStat({ calibration }: { calibration: AnalyticsSummary["calibration"] }) {
  const va = calibration.verification_accuracy;
  const tone = va == null ? "text-white/40" : va >= 0.85 ? "text-accent" : va >= 0.6 ? "text-amber-300" : "text-red-300";
  return (
    <div className="shrink-0 text-right">
      <div className={cn("text-[30px] font-semibold tabular-nums leading-none", tone)}>
        {va == null ? "—" : pct(va)}
      </div>
      <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.16em] text-white/40">
        verification accuracy
      </div>
    </div>
  );
}

/* ------------------------------------------------------- latency & fails */

function LatencyTrend({ data }: { data: AnalyticsSummary }) {
  const rows = data.latency.series.map((p) => ({ label: shortDate(p.date), p50: p.p50 }));
  const hasData = rows.some((r) => r.p50 != null);
  if (!hasData) return <NoData text="No timed runs in this range." />;
  return (
    <div className="h-[200px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis dataKey="label" stroke="rgba(255,255,255,0.28)" tick={{ fontSize: 11 }}
                 tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={28} />
          <YAxis stroke="rgba(255,255,255,0.28)" tick={{ fontSize: 11 }} tickLine={false}
                 axisLine={false} width={34} unit="s" />
          <Tooltip content={<ChartTooltip unit="s" />} />
          <Line type="monotone" dataKey="p50" name="Median (p50)" stroke={COLORS.accent} strokeWidth={2}
                dot={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function FailureBreakdown({ data }: { data: AnalyticsSummary }) {
  if (data.failures.length === 0) return <NoData text="No failures in this range. 🎉" />;
  const max = Math.max(...data.failures.map((f) => f.count));
  return (
    <div className="space-y-2.5 pt-1">
      {data.failures.slice(0, 6).map((f) => (
        <div key={f.type} className="flex items-center gap-3">
          <span className="w-36 shrink-0 truncate text-[12.5px] text-white/70" title={f.label}>
            {f.label}
          </span>
          <div className="h-2 flex-1 rounded-full bg-white/[0.05] overflow-hidden">
            <div className="h-full rounded-full bg-red-400/70"
                 style={{ width: `${Math.max(6, (f.count / max) * 100)}%` }} />
          </div>
          <span className="w-6 text-right font-mono text-[12px] tabular-nums text-white/60">{f.count}</span>
        </div>
      ))}
    </div>
  );
}

/* --------------------------------------------------------- missions strip */

function MissionsStrip({ block }: { block: NonNullable<AnalyticsSummary["missions"]> }) {
  const specialists = Object.entries(block.specialist_utilization);
  return (
    <Card title="Missions" hint={`${block.count} in range`}>
      <div className="grid sm:grid-cols-4 gap-3">
        <MiniStat label="Avg orders" value={String(block.avg_orders)} />
        <MiniStat label="Reassignments" value={String(block.reassignments)} tone={block.reassignments > block.count ? "warn" : "muted"} />
        <MiniStat label="Duplicates avoided" value={String(block.duplicates_cancelled)} tone="good" />
        <MiniStat label="Mission cost" value={`${block.cost_total} cr`} />
      </div>
      {specialists.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-white/35">Specialist utilization</div>
          {specialists.map(([name, rate]) => (
            <div key={name} className="flex items-center gap-3">
              <span className="w-24 shrink-0 truncate text-[12.5px] text-white/70">{name}</span>
              <div className="h-2 flex-1 rounded-full bg-white/[0.05] overflow-hidden">
                <div className="h-full rounded-full bg-accent/70" style={{ width: `${Math.min(100, rate * 100)}%` }} />
              </div>
              <span className="w-10 text-right font-mono text-[11px] tabular-nums text-white/55">
                {Math.round(rate * 100)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

/* ----------------------------------------------------- recommendations */

function Recommendations({ items }: { items: AnalyticsSummary["recommendations"] }) {
  if (!items.length) return null;
  const tone = {
    high: { chip: "bg-red-400/15 text-red-300 border-red-400/25", icon: AlertTriangle, ring: "border-red-400/20" },
    medium: { chip: "bg-amber-300/15 text-amber-200 border-amber-300/25", icon: TrendingUp, ring: "border-amber-300/15" },
    info: { chip: "bg-accent/15 text-accent border-accent/25", icon: ShieldCheck, ring: "border-white/[0.08]" },
  } as const;
  return (
    <section className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-5">
      <div className="mb-3 flex items-center gap-2">
        <Lightbulb size={14} className="text-accent" />
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/45">
          Optimization recommendations
        </h2>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        {items.map((r, i) => {
          const t = tone[r.severity];
          const Icon = t.icon;
          return (
            <div key={i} className={cn("rounded-lg border bg-white/[0.015] p-3.5", t.ring)}>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <Icon size={13} className={cn(r.severity === "high" ? "text-red-300" : r.severity === "medium" ? "text-amber-300" : "text-accent", "shrink-0")} />
                  <span className="truncate text-[13.5px] font-medium text-white/90">{r.title}</span>
                </div>
                <span className={cn("shrink-0 rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider", t.chip)}>
                  {r.severity}
                </span>
              </div>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-white/55">{r.detail}</p>
              {r.metric && (
                <div className="mt-2 font-mono text-[10px] uppercase tracking-wider text-white/30">{r.metric}</div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- primitives */

function Card({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/45">{title}</h2>
        {hint && <span className="font-mono text-[10px] text-white/30 truncate">{hint}</span>}
      </div>
      {children}
    </section>
  );
}

function Kpi({ icon: Icon, label, value, sub, accent, meter }: {
  icon: typeof TrendingUp; label: string; value: string; sub?: string; accent?: boolean; meter?: number;
}) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
      <div className="flex items-center gap-2 text-white/40">
        <Icon size={13} strokeWidth={1.7} />
        <span className="font-mono text-[9px] uppercase tracking-[0.18em]">{label}</span>
      </div>
      <div className={cn("mt-2 text-[26px] font-semibold tabular-nums leading-none", accent ? "text-accent" : "text-white")}>
        {value}
      </div>
      {meter != null ? (
        <div className="mt-2.5 h-1 rounded-full bg-white/[0.06] overflow-hidden">
          <div className={cn("h-full rounded-full", meter > 90 ? "bg-red-400" : meter > 70 ? "bg-amber-300" : "bg-accent")}
               style={{ width: `${Math.min(100, meter)}%` }} />
        </div>
      ) : sub ? (
        <div className="mt-1.5 text-[11px] text-white/35 truncate">{sub}</div>
      ) : null}
    </div>
  );
}

function BigStat({ label, value, hint, inverted, score }: {
  label: string; value: string; hint: string; inverted?: boolean; score?: number | null;
}) {
  const tone = inverted
    ? score == null ? "text-white" : score < 0.15 ? "text-accent" : score < 0.3 ? "text-amber-300" : "text-red-300"
    : "text-white";
  return (
    <div className="rounded-lg border border-white/[0.07] bg-white/[0.02] p-3.5">
      <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-white/40">{label}</div>
      <div className={cn("mt-1.5 text-[24px] font-semibold tabular-nums leading-none", tone)}>{value}</div>
      <p className="mt-1.5 text-[11.5px] leading-relaxed text-white/40">{hint}</p>
    </div>
  );
}

function MiniStat({ label, value, tone = "muted" }: { label: string; value: string; tone?: "muted" | "good" | "warn" }) {
  const color = tone === "good" ? "text-accent" : tone === "warn" ? "text-amber-300" : "text-white";
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
      <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-white/35">{label}</div>
      <div className={cn("mt-1.5 text-[19px] font-semibold tabular-nums", color)}>{value}</div>
    </div>
  );
}

function Segmented<T extends string>({ options, value, onChange }: {
  options: { key: T; label: string }[]; value: T; onChange: (v: T) => void;
}) {
  return (
    <div className="flex items-center gap-1 rounded-lg border border-white/[0.07] bg-white/[0.02] p-1">
      {options.map((o) => (
        <button key={o.key} onClick={() => onChange(o.key)}
                className={cn("rounded-md px-2.5 h-7 font-mono text-[10px] uppercase tracking-wider transition-colors",
                  value === o.key ? "bg-white/[0.08] text-white" : "text-white/40 hover:text-white")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Legend({ items }: { items: { color: string; label: string }[] }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-4">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: i.color }} />
          <span className="text-[11.5px] text-white/55">{i.label}</span>
        </span>
      ))}
    </div>
  );
}

function ChartTooltip({ active, payload, label, unit = "" }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/[0.1] bg-[#0A0A0A] px-3 py-2 shadow-xl">
      <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-white/40">{label}</div>
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center gap-2 text-[12px]">
          <span className="h-2 w-2 rounded-sm" style={{ background: p.color || p.stroke }} />
          <span className="text-white/55">{p.name}</span>
          <span className="ml-auto font-mono tabular-nums text-white/90">{p.value}{unit}</span>
        </div>
      ))}
    </div>
  );
}

function CalibTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  return (
    <div className="rounded-lg border border-white/[0.1] bg-[#0A0A0A] px-3 py-2 shadow-xl text-[12px]">
      <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-white/40">confidence {label}</div>
      <div className="text-white/80">Actual success: <span className="font-mono">{row?.actual == null ? "—" : `${row.actual}%`}</span></div>
      <div className="text-white/50">Ideal: <span className="font-mono">{row?.ideal}%</span></div>
      <div className="text-white/40">n = {row?.n}</div>
    </div>
  );
}

function NoData({ text }: { text: string }) {
  return <div className="flex h-[160px] items-center justify-center text-[12.5px] text-white/35">{text}</div>;
}

/* -------------------------------------------------------- states & utils */

function LoadingState() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-[92px] rounded-xl bg-white/[0.04]" />)}
      </div>
      <div className="h-[120px] rounded-xl bg-white/[0.04]" />
      <div className="h-[300px] rounded-xl bg-white/[0.04]" />
    </div>
  );
}

function EmptyState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-dashed border-white/[0.1] bg-white/[0.015] px-6 py-16 flex flex-col items-center text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-white/50">
        <BarChart3 size={20} strokeWidth={1.6} />
      </span>
      <h3 className="mt-4 text-[15px] font-medium text-white">No runs in this range yet</h3>
      <p className="mt-1.5 max-w-sm text-[13px] leading-relaxed text-white/50">
        Run a task or mission and this page fills with outcome trends, confidence calibration,
        latency, failure causes and tailored recommendations.
      </p>
      <div className="mt-5 flex items-center gap-2.5">
        <Link href="/dashboard/run"
              className="inline-flex items-center gap-1.5 rounded-full bg-accent px-4 h-9 text-[13px] font-medium text-black transition-shadow hover:shadow-[0_0_36px_-8px_rgba(52,211,153,0.35)]">
          <PlayCircle size={14} /> Run your first task
        </Link>
        <button onClick={onRetry}
                className="inline-flex items-center gap-2 rounded-full border border-white/[0.1] bg-white/[0.03] px-3.5 h-9 text-[12.5px] text-white/70 hover:text-white transition-colors">
          <RefreshCcw size={13} /> Refresh
        </button>
      </div>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-red-400/25 bg-red-400/[0.05] p-6">
      <div className="flex items-center gap-2 text-red-300">
        <AlertTriangle size={15} />
        <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Couldn&apos;t load analytics</span>
      </div>
      <p className="mt-2 text-[13px] text-white/70">{message}</p>
      <button onClick={onRetry}
              className="mt-4 inline-flex items-center gap-2 rounded-lg border border-white/[0.1] bg-white/[0.04] px-3.5 h-9 text-[12.5px] text-white/80 hover:text-white transition-colors">
        <RefreshCcw size={13} /> Retry
      </button>
    </div>
  );
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function shortDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

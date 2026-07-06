"use client";

/** Mission detail: the replayable record — final report, work-order
 * graph, evidence with confidence and open conflicts, the executive's
 * decision log, and the persisted canonical event timeline. */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft } from "lucide-react";
import { cn, isAbortError } from "@/lib/utils";
import {
  ApiEventRow,
  ApiMission,
  ApiWorkOrder,
  ApiWorkResult,
  getMission,
  getMissionEvents,
} from "@/lib/api";

export default function MissionDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [mission, setMission] = useState<ApiMission | null>(null);
  const [events, setEvents] = useState<ApiEventRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const id = params.id;
    Promise.allSettled([
      getMission(id, controller.signal),
      getMissionEvents(id, 0, controller.signal),
    ]).then(([m, e]) => {
      if (m.status === "fulfilled") setMission(m.value);
      else if (isAbortError(m.reason)) { /* ignore */ }
      else if (String(m.reason).includes("Unauthorized")) router.replace("/signin");
      else setError(m.reason instanceof Error ? m.reason.message : "Failed to load mission");
      if (e.status === "fulfilled") setEvents(e.value);
    });
    return () => controller.abort();
  }, [params.id, router]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
        {error}
      </div>
    );
  }
  if (!mission) {
    return (
      <div className="space-y-3 animate-pulse">
        <div className="h-20 rounded-xl bg-white/[0.04]" />
        <div className="h-64 rounded-xl bg-white/[0.04]" />
      </div>
    );
  }

  const result = mission.result;
  const orders = result?.orders ?? [];
  const work = new Map((result?.work ?? []).map((w) => [w.order_id, w]));
  const conflicts = result?.metadata?.conflicts ?? [];
  const report = result?.report;
  const metrics = mission.metrics ?? result?.metrics;

  return (
    <div className="space-y-4">
      {/* header */}
      <div className="flex items-start gap-3">
        <Link href="/dashboard/missions"
              className="mt-1 rounded-md p-1.5 text-white/40 hover:text-white hover:bg-white/[0.04] transition-colors">
          <ArrowLeft size={15} />
        </Link>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip status={mission.status} />
            <span className="font-mono text-[10px] text-white/30">
              {mission.id.slice(0, 8)} · {new Date(mission.created_at).toLocaleString()}
              {mission.duration_s ? ` · ${Math.round(mission.duration_s)}s` : ""}
            </span>
          </div>
          <h1 className="mt-1.5 text-[15px] text-white/90 leading-snug">{mission.instruction}</h1>
        </div>
      </div>

      {/* metrics strip */}
      {metrics && (
        <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
          <Metric label="orders" value={`${metrics.orders_completed}/${metrics.orders_total}`} />
          <Metric label="evidence" value={String(metrics.evidence_count)} />
          <Metric label="conflicts" value={String(metrics.conflicts_open)}
                  alert={metrics.conflicts_open > 0} />
          <Metric label="reassignments" value={String(metrics.reassignments)} />
          <Metric label="peak parallel" value={String(metrics.peak_parallelism)} />
          <Metric label="cost" value={`${round2(metrics.cost_total)} cr`} />
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1.5fr_1fr] gap-4 items-start">
        <div className="space-y-4">
          {/* report */}
          {report && (
            <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                            className="glass-strong rounded-xl p-5">
              <SectionTitle accent>
                Mission report · confidence {(report.confidence * 100).toFixed(0)}%
              </SectionTitle>
              <p className="text-[13px] leading-relaxed text-white/85">{report.executive_summary}</p>
              {report.key_findings.length > 0 && (
                <ul className="mt-3 space-y-1.5">
                  {report.key_findings.map((finding, i) => (
                    <li key={i} className="flex gap-2 text-[12px] text-white/65">
                      <span className="text-accent shrink-0">▸</span>{finding}
                    </li>
                  ))}
                </ul>
              )}
              {report.evidence.length > 0 && (
                <div className="mt-4">
                  <SectionTitle>Evidence</SectionTitle>
                  <div className="space-y-1">
                    {report.evidence.slice(0, 12).map((evidence, i) => (
                      <div key={i} className="flex items-center gap-3">
                        <span className="w-36 shrink-0 truncate font-mono text-[10px] text-white/40">
                          {evidence.label}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-[12px] text-white/75">
                          {evidence.value}
                        </span>
                        <ConfidenceBar value={evidence.confidence} />
                        <span className="w-16 shrink-0 truncate font-mono text-[9px] text-white/25">
                          {evidence.source}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {(report.next_actions?.length ?? 0) > 0 && (
                <div className="mt-4">
                  <SectionTitle>Suggested next actions</SectionTitle>
                  <ul className="space-y-1">
                    {report.next_actions.map((action, i) => (
                      <li key={i} className="text-[12px] text-white/55">→ {action}</li>
                    ))}
                  </ul>
                </div>
              )}
            </motion.section>
          )}

          {/* evidence conflicts: left visible, never hidden */}
          {conflicts.length > 0 && (
            <section className="rounded-xl border border-amber-300/20 bg-amber-300/[0.03] p-4">
              <SectionTitle warn>Open evidence conflicts</SectionTitle>
              <div className="space-y-2">
                {conflicts.map((conflict, i) => (
                  <div key={i} className="text-[12px]">
                    <span className="font-mono text-[10px] text-amber-300/90">
                      {conflict.entity}.{conflict.attribute}
                    </span>
                    <div className="mt-0.5 text-white/60">
                      {conflict.values.map((v, j) => (
                        <span key={j}>
                          {j > 0 && <span className="text-white/25"> vs </span>}
                          “{v.value}”
                          <span className="text-white/30"> ({v.sources.join(", ")})</span>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* work orders */}
          <section className="glass rounded-xl p-4">
            <SectionTitle>Work orders</SectionTitle>
            {orders.length === 0 ? (
              <p className="text-[12px] text-white/35">No order breakdown recorded.</p>
            ) : (
              <div className="space-y-2">
                {orders.map((order) => (
                  <OrderRow key={order.id} order={order} result={work.get(order.id)} />
                ))}
              </div>
            )}
          </section>
        </div>

        {/* right rail: decisions + timeline */}
        <div className="space-y-4">
          <section className="glass rounded-xl p-4">
            <SectionTitle>Executive decisions</SectionTitle>
            <DecisionLog events={events} />
          </section>
          <section className="glass rounded-xl p-4">
            <SectionTitle>Timeline</SectionTitle>
            <Timeline events={events} />
          </section>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function SectionTitle({ children, accent, warn }: {
  children: React.ReactNode; accent?: boolean; warn?: boolean;
}) {
  return (
    <h2 className={cn("mb-2 font-mono text-[10px] uppercase tracking-[0.2em]",
                      accent ? "text-accent/80" : warn ? "text-amber-300/90" : "text-white/40")}>
      {children}
    </h2>
  );
}

function StatusChip({ status }: { status: string }) {
  const style =
    status === "completed" ? "text-accent border-accent/30" :
    status === "partial" ? "text-amber-300 border-amber-300/30" :
    status === "failed" ? "text-red-400 border-red-400/30" :
    status === "running" ? "text-sky-300 border-sky-300/30" :
    "text-white/40 border-white/10";
  return (
    <span className={cn("rounded border px-2 py-[2px] font-mono text-[9px] uppercase tracking-[0.14em]", style)}>
      {status}
    </span>
  );
}

function Metric({ label, value, alert }: { label: string; value: string; alert?: boolean }) {
  return (
    <div className="glass rounded-lg px-3 py-2">
      <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-white/30">{label}</div>
      <div className={cn("mt-0.5 text-[15px] font-medium tabular-nums",
                         alert ? "text-amber-300" : "text-white/90")}>{value}</div>
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <span className="flex w-20 shrink-0 items-center gap-1.5" title={`confidence ${pct}%`}>
      <span className="h-1 flex-1 rounded-full bg-white/[0.07] overflow-hidden">
        <span className={cn("block h-full rounded-full",
                            pct >= 75 ? "bg-accent" : pct >= 45 ? "bg-amber-300" : "bg-red-400")}
              style={{ width: `${pct}%` }} />
      </span>
      <span className="font-mono text-[9px] text-white/35 tabular-nums w-7">{pct}%</span>
    </span>
  );
}

const ORDER_STYLE: Record<string, string> = {
  completed: "text-accent border-accent/30",
  failed: "text-red-400 border-red-400/30",
  running: "text-sky-300 border-sky-300/30",
  cancelled: "text-white/30 border-white/10",
  skipped: "text-white/30 border-white/10",
  pending: "text-white/40 border-white/10",
};

function OrderRow({ order, result }: { order: ApiWorkOrder; result?: ApiWorkResult }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-white/[0.05] bg-white/[0.02]">
      <button onClick={() => setOpen((v) => !v)}
              className="flex w-full items-start gap-3 px-3 py-2 text-left">
        <span className={cn("mt-[2px] shrink-0 rounded border px-1.5 py-[1px] font-mono text-[9px] uppercase tracking-wider",
                            ORDER_STYLE[order.status] || ORDER_STYLE.pending)}>
          {order.status}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] text-white/85">{order.objective}</span>
          <span className="mt-0.5 block font-mono text-[10px] text-white/35">
            {order.capability}
            {order.assigned_to && ` · ${order.assigned_to}`}
            {order.attempts > 1 && ` · ${order.attempts} attempts`}
            {order.depends_on.length > 0 && ` · after ${order.depends_on.length} order(s)`}
          </span>
        </span>
        {result && (
          <span className="shrink-0 font-mono text-[10px] text-white/30 tabular-nums">
            {round2(result.duration_s)}s
          </span>
        )}
      </button>
      {open && (
        <div className="border-t border-white/[0.05] px-3 py-2 space-y-1.5">
          {order.status_reason && (
            <Detail k="status reason" v={order.status_reason} />
          )}
          {result?.summary && <Detail k="summary" v={result.summary} />}
          {result && Object.entries(result.outputs || {}).map(([k, v]) => (
            <Detail key={k} k={`out · ${k}`} v={v} />
          ))}
          {order.produces.length > 0 && !result && (
            <Detail k="promises" v={order.produces.join(", ")} />
          )}
          {result?.error && <Detail k="error" v={result.error} err />}
        </div>
      )}
    </div>
  );
}

function Detail({ k, v, err }: { k: string; v: string; err?: boolean }) {
  return (
    <div className="flex gap-2 text-[11px]">
      <span className="w-24 shrink-0 font-mono text-[9px] uppercase tracking-wider text-white/30 pt-[2px]">{k}</span>
      <span className={cn("min-w-0 flex-1 break-words", err ? "text-red-300/90" : "text-white/60")}>{v}</span>
    </div>
  );
}

function DecisionLog({ events }: { events: ApiEventRow[] }) {
  const decisions = events.filter((e) => e.type === "mission_decision");
  if (decisions.length === 0) {
    return <p className="text-[12px] text-white/35">No decision log persisted for this mission.</p>;
  }
  return (
    <div className="max-h-64 space-y-1 overflow-y-auto pr-1">
      {decisions.map((event) => {
        const d = event.payload as Record<string, any>;
        return (
          <div key={event.seq} className="flex gap-2 text-[11px]">
            <span className="w-8 shrink-0 font-mono text-[9px] text-white/25 tabular-nums pt-[2px]">
              #{d.cycle ?? event.seq}
            </span>
            <span className={cn("w-20 shrink-0 font-mono text-[10px] uppercase tracking-wider",
                                d.decision === "dispatch" ? "text-accent/80" :
                                d.decision === "abort" ? "text-red-400" :
                                d.decision === "finish" ? "text-accent" : "text-white/45")}>
              {String(d.decision || "")}
            </span>
            <span className="min-w-0 flex-1 truncate text-white/50" title={String(d.reason || "")}>
              {String(d.reason || "")}
            </span>
          </div>
        );
      })}
    </div>
  );
}

const TIMELINE_LABEL: Record<string, string> = {
  mission_started: "mission started",
  mission_planned: "work graph planned",
  work_dispatched: "dispatched",
  work_completed: "work finished",
  evidence_merged: "evidence merged",
  mission_completed: "mission finished",
  log: "note",
};

function Timeline({ events }: { events: ApiEventRow[] }) {
  const rows = events.filter((e) => e.type in TIMELINE_LABEL);
  if (rows.length === 0) {
    return (
      <p className="text-[12px] text-white/35">
        No persisted events — replay is available for missions run after the
        platform migration.
      </p>
    );
  }
  return (
    <div className="max-h-96 overflow-y-auto pr-1">
      <ol className="relative ml-1 border-l border-white/[0.07] space-y-2.5 py-1">
        {rows.map((event) => {
          const p = event.payload as Record<string, any>;
          return (
            <li key={event.seq} className="relative pl-4">
              <span className={cn("absolute -left-[3px] top-[5px] h-[5px] w-[5px] rounded-full",
                                  event.type === "mission_completed" ? "bg-accent" :
                                  event.type === "work_completed" && p.status !== "completed"
                                    ? "bg-red-400" : "bg-white/30")} />
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider text-white/50">
                  {TIMELINE_LABEL[event.type]}
                </span>
                <span className="font-mono text-[9px] text-white/25">
                  {event.ts ? new Date(event.ts).toLocaleTimeString() : `#${event.seq}`}
                </span>
              </div>
              <div className="mt-0.5 text-[11px] text-white/45 break-words">
                {describeEvent(event.type, p)}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function describeEvent(type: string, p: Record<string, any>): string {
  switch (type) {
    case "mission_started":
      return String(p.instruction || "");
    case "mission_planned":
      return `${(p.orders as any[] | undefined)?.length ?? 0} work order(s)`;
    case "work_dispatched":
      return `${p.objective ?? p.order} → ${p.specialist}${p.attempt > 1 ? ` (attempt ${p.attempt})` : ""}`;
    case "work_completed":
      return `${p.specialist}: ${p.status}${p.summary ? ` — ${String(p.summary).slice(0, 140)}` : ""}${p.error ? ` — ${p.error}` : ""}`;
    case "evidence_merged":
      return `${p.merged} claim(s) merged${p.graph ? ` · graph now ${p.graph.claims} claims / ${p.graph.entities} entities` : ""}`;
    case "mission_completed":
      return `${p.status} in ${p.duration_s}s`;
    default:
      return String(p.message || "");
  }
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

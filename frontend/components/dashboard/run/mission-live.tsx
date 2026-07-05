"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/** Wire-v1 event from /missions/stream: canonical type + nested data. */
export interface MissionWireEvent {
  type: string;
  seq?: number;
  task_id?: string;
  timestamp?: string;
  data?: Record<string, unknown>;
  [key: string]: unknown;
}

interface OrderView {
  id: string;
  objective: string;
  capability: string;
  status: string;
  specialist: string;
  summary: string;
  attempts: number;
}

export interface MissionView {
  status: string;            // planning | running | completed | partial | failed
  orders: OrderView[];
  decisions: Array<{ cycle: number; decision: string; reason: string }>;
  evidenceMerged: number;
  report: { executive_summary?: string; key_findings?: string[]; confidence?: number } | null;
  durationS: number | null;
  errors: string[];
}

/** Fold the wire stream into one render-ready view. Pure — replaying the
 * same events always yields the same board. */
export function deriveMissionView(events: MissionWireEvent[]): MissionView {
  const view: MissionView = {
    status: "planning",
    orders: [],
    decisions: [],
    evidenceMerged: 0,
    report: null,
    durationS: null,
    errors: [],
  };
  const byId = new Map<string, OrderView>();

  for (const event of events) {
    const d = (event.data || {}) as Record<string, any>;
    switch (event.type) {
      case "mission_planned":
        for (const o of (d.orders as any[]) || []) {
          byId.set(o.id, {
            id: o.id,
            objective: o.objective || "",
            capability: o.capability || "",
            status: o.status || "pending",
            specialist: o.assigned_to || "",
            summary: "",
            attempts: o.attempts || 0,
          });
        }
        view.status = "running";
        break;
      case "work_dispatched": {
        const order = byId.get(String(d.order));
        if (order) {
          order.status = "running";
          order.specialist = String(d.specialist || "");
          order.attempts = Number(d.attempt || order.attempts);
        }
        break;
      }
      case "work_completed": {
        const order = byId.get(String(d.order));
        if (order) {
          order.status = String(d.status || "completed");
          order.summary = String(d.summary || d.error || "");
        }
        break;
      }
      case "mission_decision":
        view.decisions.push({
          cycle: Number(d.cycle || view.decisions.length + 1),
          decision: String(d.decision || ""),
          reason: String(d.reason || ""),
        });
        break;
      case "evidence_merged":
        view.evidenceMerged += Number(d.merged || 0);
        break;
      case "mission_completed":
        view.status = String(d.status || "completed");
        view.durationS = Number(d.duration_s ?? 0);
        view.report = (d.report as MissionView["report"]) || null;
        view.errors = ((d.errors as string[]) || []).filter(Boolean);
        break;
      case "error":
        view.errors.push(String((event as any).message || d.message || "error"));
        break;
    }
  }
  view.orders = Array.from(byId.values());
  return view;
}

const STATUS_STYLE: Record<string, string> = {
  pending: "text-white/35 border-white/10",
  running: "text-amber-300 border-amber-300/30",
  completed: "text-accent border-accent/30",
  failed: "text-red-400 border-red-400/30",
  cancelled: "text-white/30 border-white/10 line-through",
  skipped: "text-white/30 border-white/10",
};

export function MissionLive({ events, running }: { events: MissionWireEvent[]; running: boolean }) {
  const view = useMemo(() => deriveMissionView(events), [events]);
  const lastDecision = view.decisions[view.decisions.length - 1];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-4"
    >
      {/* status header */}
      <div className="glass rounded-xl px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
          Mission
        </span>
        <span className={cn(
          "font-mono text-[11px] uppercase tracking-wider",
          view.status === "completed" && "text-accent",
          view.status === "partial" && "text-amber-300",
          view.status === "failed" && "text-red-400",
          (view.status === "running" || view.status === "planning") && "text-white/70",
        )}>
          {running && view.status === "planning" ? "decomposing mission…" : view.status}
        </span>
        <span className="font-mono text-[11px] text-white/40">
          {view.orders.length} order(s) · {view.evidenceMerged} evidence claim(s)
          {view.durationS != null && ` · ${view.durationS}s`}
        </span>
        {lastDecision && running && (
          <span className="font-mono text-[11px] text-white/40 truncate max-w-[40ch]">
            executive: {lastDecision.decision} — {lastDecision.reason}
          </span>
        )}
      </div>

      {/* work orders board */}
      {view.orders.length > 0 && (
        <div className="glass rounded-xl p-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/40 mb-3">
            Work orders
          </div>
          <div className="space-y-2">
            {view.orders.map((order) => (
              <div key={order.id}
                   className="flex items-start gap-3 rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2">
                <span className={cn(
                  "mt-[3px] shrink-0 rounded border px-1.5 py-[1px] font-mono text-[9px] uppercase tracking-wider",
                  STATUS_STYLE[order.status] || STATUS_STYLE.pending,
                )}>
                  {order.status}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] text-white/85 truncate">{order.objective}</div>
                  <div className="font-mono text-[10px] text-white/35 mt-0.5">
                    {order.capability}
                    {order.specialist && <> · {order.specialist}</>}
                    {order.attempts > 1 && <> · attempt {order.attempts}</>}
                    {order.summary && <> — {order.summary.slice(0, 120)}</>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* final report */}
      {view.report && (
        <div className="glass-strong rounded-xl p-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent/80 mb-2">
            Mission report
            {typeof view.report.confidence === "number" &&
              ` · confidence ${(view.report.confidence * 100).toFixed(0)}%`}
          </div>
          <p className="text-[13px] leading-relaxed text-white/80">
            {view.report.executive_summary}
          </p>
          {(view.report.key_findings || []).length > 0 && (
            <ul className="mt-3 space-y-1">
              {view.report.key_findings!.map((finding, i) => (
                <li key={i} className="text-[12px] text-white/60 flex gap-2">
                  <span className="text-accent">▸</span>
                  <span>{finding}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {view.errors.length > 0 && (
        <div className="rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3">
          {view.errors.map((error, i) => (
            <div key={i} className="font-mono text-[11px] text-red-300/90">{error}</div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

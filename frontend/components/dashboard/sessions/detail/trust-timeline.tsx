"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ShieldCheck,
  ShieldAlert,
  Pause,
  Play,
  Square,
  Check,
  X,
  UserCheck,
} from "lucide-react";
import { getSessionEvents, type ApiEventRow } from "@/lib/api";
import { isAbortError } from "@/lib/utils";

/**
 * The trust timeline — the audit-grade replay of everything the operator
 * needs to trust an autonomous run after the fact: every risk the agent
 * flagged, every approval it asked for and how it was settled, and every
 * time a human paused, resumed or stopped it. Derived entirely from the
 * persisted canonical event stream; nothing here is reconstructed.
 */

const TRUST_TYPES = new Set([
  "execution_paused",
  "execution_resumed",
  "execution_stopped",
  "risk_flagged",
  "approval_requested",
  "approval_decided",
]);

interface RiskFlag {
  kind: string;
  level: "low" | "medium" | "high";
  summary?: string;
  detail?: string;
}

export function TrustTimeline({ sessionId }: { sessionId: string }) {
  const [events, setEvents] = useState<ApiEventRow[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getSessionEvents(sessionId, 0, controller.signal)
      .then(setEvents)
      .catch((err) => {
        if (!isAbortError(err)) setFailed(true);
      });
    return () => controller.abort();
  }, [sessionId]);

  if (failed || events === null) return null; // silent until loaded; no error clutter

  const trust = events.filter((e) => TRUST_TYPES.has(e.type)).sort((a, b) => a.seq - b.seq);

  // A run with persisted events but no trust activity is itself a trust
  // signal: it ran cleanly, autonomously, with nothing to flag.
  if (trust.length === 0) {
    if (events.length === 0) return null;
    return (
      <Card>
        <div className="flex items-center gap-2.5 px-4 py-3.5">
          <ShieldCheck size={15} className="text-accent shrink-0" />
          <span className="text-[13px] text-white/70">
            Clean run — no risks were flagged and no human intervention was needed.
          </span>
        </div>
      </Card>
    );
  }

  const risks = trust.filter((e) => e.type === "risk_flagged").length;
  const approvals = trust.filter((e) => e.type === "approval_requested").length;
  const interventions = trust.filter(
    (e) =>
      e.type === "execution_paused" ||
      e.type === "execution_resumed" ||
      e.type === "execution_stopped" ||
      (e.type === "approval_decided" && !e.payload?.auto)
  ).length;

  return (
    <Card>
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 h-11">
        <div className="flex items-center gap-2">
          <ShieldAlert size={13} className="text-white/45" />
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
            trust timeline
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[10px] text-white/40">
          <span>{risks} risk{risks === 1 ? "" : "s"}</span>
          <span>{approvals} approval{approvals === 1 ? "" : "s"}</span>
          <span>{interventions} intervention{interventions === 1 ? "" : "s"}</span>
        </div>
      </div>
      <ol className="p-4 space-y-3">
        {trust.map((e) => (
          <Row key={e.seq} event={e} />
        ))}
      </ol>
    </Card>
  );
}

function Row({ event }: { event: ApiEventRow }) {
  const { icon, tone, title, detail, chips } = describe(event);
  const toneCls: Record<string, string> = {
    ok: "text-accent",
    warn: "text-amber-300",
    danger: "text-red-300",
    neutral: "text-white/55",
  };
  return (
    <li className="flex items-start gap-3">
      <span className={`mt-0.5 shrink-0 ${toneCls[tone]}`}>{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-[13px] text-white/85">{title}</span>
          <span className="ml-auto font-mono text-[10px] text-white/30 tabular-nums shrink-0">
            {formatTime(event.ts)}
          </span>
        </div>
        {detail && <p className="mt-0.5 text-[12px] leading-snug text-white/50">{detail}</p>}
        {chips && chips.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {chips.map((c, i) => (
              <span
                key={i}
                className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] ${chipTone(
                  c.level
                )}`}
                title={c.detail}
              >
                <ShieldAlert size={9} />
                {c.kind.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}

function describe(event: ApiEventRow): {
  icon: React.ReactNode;
  tone: "ok" | "warn" | "danger" | "neutral";
  title: string;
  detail?: string;
  chips?: RiskFlag[];
} {
  const p = event.payload || {};
  switch (event.type) {
    case "risk_flagged":
      return {
        icon: <ShieldAlert size={14} />,
        tone: p.level === "high" ? "danger" : "warn",
        title: `Risk flagged: ${String(p.summary || "consequential action")}`,
        detail: `Before step ${p.step_number ?? "?"} · ${String(p.action || "")}`.trim(),
        chips: (p.risks as RiskFlag[]) || [],
      };
    case "approval_requested":
      return {
        icon: <ShieldAlert size={14} />,
        tone: "warn",
        title: "Approval requested",
        detail: String(p.summary || ""),
        chips: (p.risks as RiskFlag[]) || [],
      };
    case "approval_decided": {
      const grant = p.decision === "grant";
      const auto = Boolean(p.auto);
      return {
        icon: grant ? <Check size={14} /> : <X size={14} />,
        tone: grant ? "ok" : "danger",
        title: auto
          ? `Auto-${grant ? "approved" : "denied"} (no approver attached)`
          : `${grant ? "Approved" : "Denied"}${p.decided_by ? " by operator" : ""}`,
        detail: p.reason ? String(p.reason) : undefined,
      };
    }
    case "execution_paused":
      return { icon: <Pause size={14} />, tone: "warn", title: "Paused by operator",
        detail: String(p.reason || "") };
    case "execution_resumed":
      return { icon: <Play size={14} />, tone: "ok", title: "Resumed by operator" };
    case "execution_stopped":
      return { icon: <Square size={13} />, tone: "danger", title: "Stopped",
        detail: String(p.reason || "") };
    default:
      return { icon: <UserCheck size={14} />, tone: "neutral", title: event.type };
  }
}

function chipTone(level?: string): string {
  if (level === "high") return "border-red-400/30 text-red-300";
  if (level === "medium") return "border-amber-400/30 text-amber-200";
  return "border-white/15 text-white/55";
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl"
      data-testid="trust-timeline"
    >
      {children}
    </motion.div>
  );
}

function formatTime(ts: string | null): string {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Pause,
  Play,
  Square,
  ShieldAlert,
  ShieldCheck,
  Check,
  X,
  Loader2,
  Activity,
  Gauge,
  FileText,
  ArrowRight,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import type { ApprovalDecision, ControlAction } from "@/lib/control";

/**
 * The Execution Cockpit — not a terminal, a cockpit. At every moment it
 * answers six questions without the operator having to ask: what is
 * happening now, why, what happens next, what the agent is waiting for,
 * what risks exist, and what actions the operator can take right now.
 *
 * Every field is derived from the canonical event stream. Trust and
 * control ride the same events as everything else; nothing here is faked.
 */

// ------------------------------------------------------------------- model

export type RiskLevel = "low" | "medium" | "high";

export interface RiskFlag {
  kind: string;
  level: RiskLevel;
  summary: string;
  detail?: string;
}

export interface PendingApproval {
  requestId: string;
  action: string;
  summary: string;
  level: RiskLevel;
  risks: RiskFlag[];
}

export type CockpitControl =
  | "idle"
  | "running"
  | "paused"
  | "stopping"
  | "done"
  | "error";

export interface CockpitState {
  control: CockpitControl;
  finalStatus?: "completed" | "failed";
  phase: string;
  nowTitle: string;
  nowAction: string;
  why: string;
  next: string;
  waitingReason: string;
  stepsTotal: number;
  stepsDone: number;
  confidence: number | null;
  risks: RiskFlag[];
  pending: PendingApproval | null;
  evidence: number;
  interventions: number;
  _steps: string[];
  _started: boolean;
}

export function emptyCockpit(): CockpitState {
  return {
    control: "idle",
    phase: "Idle",
    nowTitle: "",
    nowAction: "",
    why: "",
    next: "",
    waitingReason: "",
    stepsTotal: 0,
    stepsDone: 0,
    confidence: null,
    risks: [],
    pending: null,
    evidence: 0,
    interventions: 0,
    _steps: [],
    _started: false,
  };
}

const RANK: Record<RiskLevel, number> = { low: 0, medium: 1, high: 2 };

/** Fold one SSE event (any type) into cockpit state, immutably. */
export function applyCockpitEvent(
  s: CockpitState,
  e: Record<string, unknown> & { type: string }
): CockpitState {
  switch (e.type) {
    case "session_start":
      return { ...s, control: "running", phase: "Understanding the goal", _started: true };

    case "plan": {
      const steps = ((e.steps as { description?: string }[]) || []).map(
        (st) => String(st.description || "")
      );
      return {
        ...s,
        control: s.control === "idle" ? "running" : s.control,
        _steps: steps,
        stepsTotal: steps.length,
        phase: "Plan ready",
        next: steps[0] || "Final verification",
      };
    }

    case "step_start": {
      const n = Number(e.step_number || 0);
      return {
        ...s,
        control: s.pending ? s.control : s.control === "paused" ? s.control : "running",
        nowTitle: String(e.description || ""),
        nowAction: String(e.action || ""),
        phase: s.stepsTotal ? `Executing step ${n} of ${s.stepsTotal}` : `Executing step ${n}`,
        next: s._steps[n] || "Final verification",
        waitingReason: "",
      };
    }

    case "step_complete": {
      const step = (e.step || {}) as { status?: string; description?: string };
      const done = s.stepsDone + 1;
      const ok = step.status === "completed" || step.status === "healed";
      return {
        ...s,
        stepsDone: done,
        waitingReason: ok ? s.waitingReason : "",
      };
    }

    case "world": {
      const c = Number(e.confidence);
      return { ...s, confidence: Number.isFinite(c) ? c : s.confidence };
    }

    case "reasoning": {
      if (e.kind === "decision_made" && e.reason) {
        return { ...s, why: String(e.reason) };
      }
      if (e.kind === "progress_updated" && e.remaining_work) {
        return { ...s, next: String(e.remaining_work) || s.next };
      }
      return s;
    }

    case "log": {
      const msg = String(e.message || "");
      const ev = msg.match(/Collected (\d+) evidence/i);
      if (ev) return { ...s, evidence: s.evidence + Number(ev[1]) };
      if (/settle/i.test(msg)) return { ...s, waitingReason: "Letting the screen settle" };
      return s;
    }

    case "trust":
      return applyTrust(s, e);

    case "complete": {
      const status = String(e.status || "");
      return {
        ...s,
        control: "done",
        finalStatus: status === "completed" ? "completed" : "failed",
        phase: status === "completed" ? "Goal achieved" : "Run ended",
        pending: null,
        waitingReason: "",
        nowTitle: "",
      };
    }

    case "error":
      return { ...s, control: "error", phase: "Error", pending: null, waitingReason: "" };

    default:
      return s;
  }
}

function applyTrust(
  s: CockpitState,
  e: Record<string, unknown> & { type: string }
): CockpitState {
  const risks = (e.risks as RiskFlag[]) || [];
  switch (e.kind) {
    case "risk_flagged":
      return {
        ...s,
        risks: mergeRisks(s.risks, risks),
      };

    case "approval_requested":
      return {
        ...s,
        pending: {
          requestId: String(e.request_id || ""),
          action: String(e.action || ""),
          summary: String(e.summary || ""),
          level: (String(e.level || "medium") as RiskLevel),
          risks,
        },
        waitingReason: "Awaiting your approval to proceed",
        phase: "Approval required",
      };

    case "approval_decided":
      return {
        ...s,
        pending: null,
        waitingReason: "",
        interventions: s.interventions + (e.auto ? 0 : 1),
        phase: e.decision === "deny" ? "Action denied — replanning" : s.phase,
      };

    case "execution_paused":
      return {
        ...s,
        control: "paused",
        waitingReason: "Paused — awaiting your resume",
        phase: "Paused",
        interventions: s.interventions + 1,
      };

    case "execution_resumed":
      return {
        ...s,
        control: "running",
        waitingReason: "",
        phase: "Resumed",
        interventions: s.interventions + 1,
      };

    case "execution_stopped":
      return {
        ...s,
        control: "stopping",
        waitingReason: "",
        phase: "Stopping",
        pending: null,
      };

    default:
      return s;
  }
}

function mergeRisks(prev: RiskFlag[], next: RiskFlag[]): RiskFlag[] {
  const byKind = new Map(prev.map((r) => [r.kind, r]));
  for (const r of next) byKind.set(r.kind, r);
  return Array.from(byKind.values()).sort((a, b) => RANK[b.level] - RANK[a.level]).slice(0, 4);
}

export function peakRisk(risks: RiskFlag[]): RiskLevel | null {
  if (!risks.length) return null;
  return risks.reduce<RiskLevel>((hi, r) => (RANK[r.level] > RANK[hi] ? r.level : hi), "low");
}

// -------------------------------------------------------------- component

interface CockpitProps {
  state: CockpitState;
  running: boolean;
  onControl: (action: ControlAction) => Promise<void> | void;
  onApproval: (requestId: string, decision: ApprovalDecision) => Promise<void> | void;
}

export function ExecutionCockpit({ state, running, onControl, onApproval }: CockpitProps) {
  const [acting, setActing] = useState<string | null>(null);
  if (!state._started && state.control === "idle") return null;

  const act = async (fn: () => Promise<void> | void, key: string) => {
    setActing(key);
    try {
      await fn();
    } catch {
      /* surfaced via the stream/logs; buttons re-enable */
    } finally {
      setActing(null);
    }
  };

  const peak = peakRisk(state.risks);
  const live = running && (state.control === "running" || state.control === "paused");

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className="rounded-xl border border-white/[0.09] bg-white/[0.02] backdrop-blur-xl overflow-hidden"
      data-testid="execution-cockpit"
    >
      {/* Status strip: where the run is + the controls, always in reach */}
      <div className="flex items-center gap-3 border-b border-white/[0.07] px-4 h-12">
        <StatusBadge state={state} />
        <span className="font-mono text-[11px] text-white/50 truncate hidden sm:block">
          {state.phase}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {live && state.control !== "paused" && (
            <ControlButton
              onClick={() => act(() => onControl("pause"), "pause")}
              busy={acting === "pause"}
              icon={<Pause size={13} />}
              label="Pause"
            />
          )}
          {live && state.control === "paused" && (
            <ControlButton
              onClick={() => act(() => onControl("resume"), "resume")}
              busy={acting === "resume"}
              icon={<Play size={13} />}
              label="Resume"
              accent
            />
          )}
          {live && (
            <ControlButton
              onClick={() => act(() => onControl("stop"), "stop")}
              busy={acting === "stop"}
              icon={<Square size={12} />}
              label="Stop"
              danger
            />
          )}
        </div>
      </div>

      {/* Approval gate: the single most important state — full width, loud */}
      <AnimatePresence>
        {state.pending && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="border-b border-amber-400/20 bg-amber-400/[0.06]"
          >
            <div className="px-4 py-3.5">
              <div className="flex items-center gap-2">
                <ShieldAlert size={15} className="text-amber-300 shrink-0" />
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-amber-200/90">
                  approval required before this action
                </span>
              </div>
              <p className="mt-2 text-[15px] leading-snug text-white/90">
                {state.pending.summary || "A risky action needs your sign-off."}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {state.pending.risks.map((r, i) => (
                  <RiskChip key={i} risk={r} />
                ))}
              </div>
              <div className="mt-3.5 flex items-center gap-2.5">
                <button
                  onClick={() =>
                    act(() => onApproval(state.pending!.requestId, "grant"), "grant")
                  }
                  disabled={acting !== null}
                  className="inline-flex items-center gap-1.5 rounded-md bg-accent/90 px-3.5 h-9 text-[13px] font-medium text-black hover:bg-accent disabled:opacity-50 transition-colors"
                >
                  {acting === "grant" ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                  Approve &amp; continue
                </button>
                <button
                  onClick={() =>
                    act(() => onApproval(state.pending!.requestId, "deny"), "deny")
                  }
                  disabled={acting !== null}
                  className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-3.5 h-9 text-[13px] text-white/80 hover:bg-white/5 disabled:opacity-50 transition-colors"
                >
                  {acting === "deny" ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />}
                  Deny
                </button>
                <span className="ml-auto font-mono text-[10px] text-amber-200/60 hidden sm:block">
                  the agent is holding — it will not act until you decide
                </span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Now / Next / Waiting — the three questions, side by side */}
      <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr] divide-y md:divide-y-0 md:divide-x divide-white/[0.06]">
        <div className="p-4">
          <FieldLabel icon={<Activity size={11} />}>happening now</FieldLabel>
          {state.nowTitle ? (
            <>
              <p className="mt-2 text-[15px] leading-snug text-white/90">{state.nowTitle}</p>
              {state.nowAction && (
                <span className="mt-1.5 inline-block font-mono text-[9px] uppercase tracking-[0.14em] rounded px-1.5 py-0.5 border border-white/10 text-white/45">
                  {state.nowAction.replace(/_/g, " ")}
                </span>
              )}
            </>
          ) : (
            <p className="mt-2 text-[14px] text-white/40">{idleNow(state)}</p>
          )}
          {state.why && (
            <p className="mt-3 text-[12px] leading-relaxed text-white/50 border-t border-white/[0.06] pt-2.5">
              <span className="text-white/35">why:</span> {state.why}
            </p>
          )}
        </div>

        <div className="p-4 space-y-3.5">
          <div>
            <FieldLabel icon={<ArrowRight size={11} />}>next</FieldLabel>
            <p className="mt-1.5 text-[13px] leading-snug text-white/70 truncate" title={state.next}>
              {state.next || (state.control === "done" ? "—" : "Planning…")}
            </p>
          </div>
          <div>
            <FieldLabel icon={<Loader2 size={11} className={live && state.waitingReason ? "animate-spin" : ""} />}>
              waiting for
            </FieldLabel>
            <p className="mt-1.5 text-[13px] leading-snug text-white/70">
              {state.waitingReason || (live ? "Nothing — actively executing" : "—")}
            </p>
          </div>
        </div>
      </div>

      {/* Instrument rail: confidence, risk, evidence, progress */}
      <div className="grid grid-cols-2 sm:grid-cols-4 border-t border-white/[0.06] divide-x divide-white/[0.06]">
        <Instrument
          icon={<Gauge size={12} />}
          label="confidence"
          value={state.confidence == null ? "—" : `${Math.round(state.confidence * 100)}%`}
        />
        <Instrument
          icon={peak ? <ShieldAlert size={12} /> : <ShieldCheck size={12} />}
          label="risk"
          value={peak ? peak.toUpperCase() : "clear"}
          tone={peak === "high" ? "danger" : peak === "medium" ? "warn" : "ok"}
        />
        <Instrument icon={<FileText size={12} />} label="evidence" value={String(state.evidence)} />
        <Instrument
          icon={<Activity size={12} />}
          label="steps"
          value={state.stepsTotal ? `${state.stepsDone}/${state.stepsTotal}` : String(state.stepsDone)}
        />
      </div>
    </motion.div>
  );
}

// ------------------------------------------------------------ primitives

function StatusBadge({ state }: { state: CockpitState }) {
  const { tone, label, spin } = statusLook(state);
  const cls: Record<string, string> = {
    ok: "border-accent/30 bg-accent/10 text-accent",
    warn: "border-amber-400/30 bg-amber-400/10 text-amber-200",
    danger: "border-red-400/30 bg-red-400/10 text-red-300",
    neutral: "border-white/15 bg-white/5 text-white/70",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2.5 h-7 font-mono text-[10px] uppercase tracking-[0.14em]",
        cls[tone]
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full bg-current", spin && "animate-pulse")} />
      {label}
    </span>
  );
}

function statusLook(state: CockpitState): {
  tone: "ok" | "warn" | "danger" | "neutral";
  label: string;
  spin: boolean;
} {
  if (state.pending) return { tone: "warn", label: "approval needed", spin: true };
  switch (state.control) {
    case "paused":
      return { tone: "warn", label: "paused", spin: false };
    case "stopping":
      return { tone: "danger", label: "stopping", spin: true };
    case "error":
      return { tone: "danger", label: "error", spin: false };
    case "done":
      return state.finalStatus === "completed"
        ? { tone: "ok", label: "completed", spin: false }
        : { tone: "danger", label: "ended", spin: false };
    case "running":
      return { tone: "ok", label: "running", spin: true };
    default:
      return { tone: "neutral", label: "idle", spin: false };
  }
}

function idleNow(state: CockpitState): string {
  if (state.control === "done")
    return state.finalStatus === "completed" ? "Goal achieved." : "Run ended.";
  if (state.control === "stopping") return "Stopping at the next safe checkpoint…";
  if (state.control === "paused") return "Paused. Resume when you're ready.";
  return "Planning the approach…";
}

function ControlButton({
  onClick,
  busy,
  icon,
  label,
  accent,
  danger,
}: {
  onClick: () => void;
  busy: boolean;
  icon: React.ReactNode;
  label: string;
  accent?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2.5 h-7 text-[12px] transition-colors disabled:opacity-50",
        accent && "border-accent/40 text-accent hover:bg-accent/10",
        danger && "border-red-400/30 text-red-300 hover:bg-red-400/10",
        !accent && !danger && "border-white/15 text-white/75 hover:bg-white/5"
      )}
    >
      {busy ? <Loader2 size={12} className="animate-spin" /> : icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

function RiskChip({ risk }: { risk: RiskFlag }) {
  const tone =
    risk.level === "high"
      ? "border-red-400/30 text-red-300"
      : risk.level === "medium"
        ? "border-amber-400/30 text-amber-200"
        : "border-white/15 text-white/60";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em]",
        tone
      )}
      title={risk.detail || risk.summary}
    >
      <ShieldAlert size={9} />
      {risk.kind.replace(/_/g, " ")}
    </span>
  );
}

function FieldLabel({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <span className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.2em] text-white/35">
      {icon}
      {children}
    </span>
  );
}

function Instrument({
  icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "warn" | "danger";
}) {
  const color: Record<string, string> = {
    neutral: "text-white/80",
    ok: "text-accent",
    warn: "text-amber-200",
    danger: "text-red-300",
  };
  return (
    <div className="px-3 py-2.5">
      <span className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-white/35">
        {icon}
        {label}
      </span>
      <p className={cn("mt-1 font-mono text-[15px] tabular-nums", color[tone])}>{value}</p>
    </div>
  );
}

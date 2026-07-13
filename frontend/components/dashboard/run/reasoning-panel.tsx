"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  CheckCircle2,
  Circle,
  GitBranch,
  XCircle,
} from "lucide-react";

/**
 * Live reasoning viewer: what the agent believes, how sure it is, which
 * explanations are alive, and why it chose each action. Every element
 * mirrors a canonical reasoning event — nothing here is decorative.
 *
 * Encoding rules: confidence/progress/uncertainty are magnitudes → one
 * hue, fill encodes value; hypothesis status is state → icon + label,
 * never color alone; text wears ink tokens, never the series color.
 */

// ---------------------------------------------------------------- events

type ReasoningEvent = {
  kind: string;
  timestamp?: string;
  [key: string]: unknown;
};

export interface BeliefRow {
  statement: string;
  kind: string;
  subject: string;
  confidence: number;
  delta: number;
  reason: string;
  source: string;
  contradictions: number;
}

export interface HypothesisRow {
  explanation: string;
  kind: string;
  probability: number;
  status: "open" | "confirmed" | "rejected";
  reason?: string;
  source: string;
}

export interface DecisionRow {
  cycle: number;
  decision: string;
  reason: string;
  changed: boolean;
  uncertainty: number;
  progress: number;
}

export interface BudgetRow {
  steps_used: number;
  steps_max: number;
  replans_used: number;
  replans_max: number;
  recoveries_used: number;
  recoveries_max: number;
  llm_calls_used: number;
  llm_calls_max: number;
  elapsed_s: number;
  time_max_s: number;
  pressure: number;
}

export interface ReasoningStream {
  strategy?: { name: string; description: string; reason: string };
  decisions: DecisionRow[];
  beliefs: Record<string, BeliefRow>;
  hypotheses: Record<string, HypothesisRow>;
  uncertainty: number;
  signals: { kind: string; detail: string; severity: number }[];
  uncertaintyHistory: number[];
  progress?: {
    completion: number;
    confidence: number;
    objectives_met: number;
    objectives_total: number;
    risk: number;
    remaining_work: string;
  };
  budget?: BudgetRow;
  recoveries: { recovered: boolean; hypothesis: string; detail: string }[];
}

export function emptyReasoning(): ReasoningStream {
  return {
    decisions: [],
    beliefs: {},
    hypotheses: {},
    uncertainty: 0,
    signals: [],
    uncertaintyHistory: [],
    recoveries: [],
  };
}

/** Fold one `reasoning` SSE event into the stream state (immutably). */
export function applyReasoningEvent(
  state: ReasoningStream,
  event: ReasoningEvent
): ReasoningStream {
  switch (event.kind) {
    case "strategy_selected":
      return {
        ...state,
        strategy: {
          name: String(event.strategy ?? ""),
          description: String(event.description ?? ""),
          reason: String(event.reason ?? ""),
        },
      };

    case "decision_made": {
      const factors = (event.factors ?? {}) as Record<string, number>;
      const row: DecisionRow = {
        cycle: Number(event.cycle ?? 0),
        decision: String(event.decision ?? ""),
        reason: String(event.reason ?? ""),
        changed: Boolean(event.changed),
        uncertainty: Number(factors.uncertainty ?? 0),
        progress: Number(factors.progress ?? 0),
      };
      return {
        ...state,
        decisions: [...state.decisions.slice(-39), row],
        budget: (event.budget as BudgetRow | undefined) ?? state.budget,
        uncertaintyHistory: [
          ...state.uncertaintyHistory.slice(-63),
          row.uncertainty,
        ],
      };
    }

    case "belief_updated": {
      const key = `${event.kind_ ?? event.kind}:${event.subject}`;
      const row: BeliefRow = {
        statement: String(event.statement ?? ""),
        kind: String(event.kind ?? ""),
        subject: String(event.subject ?? ""),
        confidence: Number(event.confidence ?? 0),
        delta: Number(event.delta ?? 0),
        reason: String(event.reason ?? ""),
        source: String(event.source ?? ""),
        contradictions: Number(event.contradictions ?? 0),
      };
      return {
        ...state,
        beliefs: { ...state.beliefs, [`${row.kind}:${row.subject}`]: row },
      };
    }

    case "uncertainty_changed":
      return {
        ...state,
        uncertainty: Number(event.score ?? 0),
        signals: (event.signals as ReasoningStream["signals"]) ?? [],
      };

    case "progress_updated":
      return {
        ...state,
        progress: {
          completion: Number(event.completion ?? 0),
          confidence: Number(event.confidence ?? 0),
          objectives_met: Number(event.objectives_met ?? 0),
          objectives_total: Number(event.objectives_total ?? 0),
          risk: Number(event.risk ?? 0),
          remaining_work: String(event.remaining_work ?? ""),
        },
      };

    case "hypothesis_created": {
      const key = `${event.kind}:${event.explanation}`;
      return {
        ...state,
        hypotheses: {
          ...state.hypotheses,
          [key]: {
            explanation: String(event.explanation ?? ""),
            kind: String(event.kind ?? ""),
            probability: Number(event.probability ?? 0),
            status: "open",
            source: String(event.source ?? ""),
          },
        },
      };
    }

    case "hypothesis_resolved": {
      const key = `${event.kind}:${event.explanation}`;
      const existing = state.hypotheses[key];
      if (!existing) return state;
      return {
        ...state,
        hypotheses: {
          ...state.hypotheses,
          [key]: {
            ...existing,
            status: (event.status as HypothesisRow["status"]) ?? "open",
            reason: String(event.reason ?? ""),
          },
        },
      };
    }

    case "recovery_completed":
      return {
        ...state,
        recoveries: [
          ...state.recoveries,
          {
            recovered: Boolean(event.recovered),
            hypothesis: String(event.hypothesis ?? ""),
            detail: String(event.detail ?? ""),
          },
        ],
      };

    default:
      return state;
  }
}

// ----------------------------------------------------------------- panel

export function ReasoningPanel({ stream }: { stream: ReasoningStream }) {
  if (!stream.strategy && stream.decisions.length === 0) return null;

  const beliefs = Object.values(stream.beliefs)
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 8);
  const hypotheses = Object.values(stream.hypotheses).slice(-6).reverse();
  const decisions = [...stream.decisions].reverse();
  const progress = stream.progress;

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl"
      data-testid="reasoning-panel"
    >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 h-10">
        <div className="flex items-center gap-2 min-w-0">
          <Brain size={12} className="text-white/40 shrink-0" />
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
            reasoning
          </span>
          {stream.strategy && (
            <span
              className="font-mono text-[9px] uppercase tracking-[0.14em] rounded px-1.5 py-0.5 border border-white/[0.08] text-white/45 truncate"
              title={stream.strategy.description}
            >
              {stream.strategy.name} strategy
            </span>
          )}
        </div>
        <Meter value={stream.uncertainty} width={72} label="uncertainty" caption="uncertainty" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[0.9fr_1.3fr_1.1fr] gap-0 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.06]">
        {/* Progress + budgets */}
        <section className="p-4">
          <SectionLabel>goal progress</SectionLabel>
          <div className="mt-3 flex items-center gap-4">
            <ProgressRing value={progress?.completion ?? 0} />
            <dl className="space-y-1.5 min-w-0">
              <MiniStat
                label="objectives"
                value={
                  progress
                    ? `${progress.objectives_met}/${progress.objectives_total}`
                    : "—"
                }
              />
              <MiniStat label="risk" value={progress ? pct(progress.risk) : "—"} />
              <MiniStat
                label="estimate trust"
                value={progress ? pct(progress.confidence) : "—"}
              />
            </dl>
          </div>
          {progress?.remaining_work && (
            <p
              className="mt-3 font-mono text-[10px] leading-relaxed text-white/45 border-t border-white/[0.06] pt-2 truncate"
              title={progress.remaining_work}
            >
              next: {progress.remaining_work}
            </p>
          )}

          {stream.budget && (
            <div className="mt-4 border-t border-white/[0.06] pt-3 space-y-2">
              <SectionLabel>execution budget</SectionLabel>
              <BudgetBar label="steps" used={stream.budget.steps_used} max={stream.budget.steps_max} />
              <BudgetBar label="replans" used={stream.budget.replans_used} max={stream.budget.replans_max} />
              <BudgetBar label="recoveries" used={stream.budget.recoveries_used} max={stream.budget.recoveries_max} />
              <BudgetBar label="llm calls" used={stream.budget.llm_calls_used} max={stream.budget.llm_calls_max} />
              <BudgetBar
                label="time"
                used={Math.round(stream.budget.elapsed_s)}
                max={Math.round(stream.budget.time_max_s)}
                unit="s"
              />
            </div>
          )}
        </section>

        {/* Decision feed */}
        <section className="p-4 min-w-0">
          <div className="flex items-center justify-between">
            <SectionLabel>decision feed</SectionLabel>
            <span className="font-mono text-[9px] text-white/30">
              {stream.decisions.length} cycles
            </span>
          </div>
          <ul className="mt-3 space-y-2 max-h-[210px] overflow-y-auto pr-1">
            <AnimatePresence initial={false}>
              {decisions.map((d) => (
                <motion.li
                  key={d.cycle}
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.22 }}
                  className="flex items-start gap-2"
                >
                  <span className="font-mono text-[9px] text-white/30 tabular-nums w-[22px] pt-0.5 shrink-0">
                    {d.cycle}
                  </span>
                  <span
                    className={`font-mono text-[9px] uppercase tracking-[0.12em] rounded px-1.5 py-0.5 border shrink-0 ${
                      d.changed
                        ? "border-white/[0.2] text-white/80"
                        : "border-white/[0.08] text-white/45"
                    }`}
                    title={d.changed ? "decision changed" : "decision unchanged"}
                  >
                    {d.decision.replace(/_/g, " ")}
                  </span>
                  <span className="font-mono text-[10px] leading-snug text-white/55 min-w-0">
                    {d.reason}
                  </span>
                </motion.li>
              ))}
            </AnimatePresence>
            {decisions.length === 0 && (
              <li className="font-mono text-[10px] text-white/30">no decisions yet</li>
            )}
          </ul>

          {/* Uncertainty history: magnitude bars, one neutral hue */}
          {stream.uncertaintyHistory.length > 1 && (
            <div className="mt-3 border-t border-white/[0.06] pt-2">
              <div
                className="flex items-end gap-[2px] h-[28px]"
                role="img"
                aria-label={`uncertainty per cycle; latest ${pct(stream.uncertainty)}`}
              >
                {stream.uncertaintyHistory.slice(-48).map((u, i) => (
                  <div
                    key={i}
                    className="flex-1 max-w-[8px] rounded-t-[1px] bg-white/35"
                    style={{ height: `${Math.max(4, u * 28)}px` }}
                    title={`uncertainty ${pct(u)}`}
                  />
                ))}
              </div>
              <span className="font-mono text-[9px] text-white/30">uncertainty per cycle</span>
            </div>
          )}
        </section>

        {/* Beliefs + hypotheses */}
        <section className="p-4 min-w-0">
          <SectionLabel>beliefs</SectionLabel>
          <ul className="mt-3 space-y-2 max-h-[120px] overflow-y-auto pr-1">
            <AnimatePresence initial={false}>
              {beliefs.map((b) => (
                <motion.li
                  key={`${b.kind}:${b.subject}`}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.25 }}
                  className="flex items-center gap-2.5"
                  title={`${b.reason}${b.source ? ` (${b.source})` : ""}`}
                >
                  <Meter value={b.confidence} width={40} label={`${b.statement} ${pct(b.confidence)}`} />
                  <span className="font-mono text-[11px] text-white/75 truncate min-w-0">
                    {b.statement}
                  </span>
                  <span
                    className={`font-mono text-[9px] tabular-nums shrink-0 ${
                      b.delta >= 0 ? "text-white/45" : "text-[#FF7A6B]"
                    }`}
                  >
                    {b.delta >= 0 ? "+" : ""}
                    {Math.round(b.delta * 100)}
                  </span>
                </motion.li>
              ))}
            </AnimatePresence>
            {beliefs.length === 0 && (
              <li className="font-mono text-[10px] text-white/30">no beliefs formed yet</li>
            )}
          </ul>

          <div className="mt-4 border-t border-white/[0.06] pt-3">
            <SectionLabel>hypotheses</SectionLabel>
            <ul className="mt-2 space-y-2 max-h-[110px] overflow-y-auto pr-1">
              <AnimatePresence initial={false}>
                {hypotheses.map((h) => (
                  <motion.li
                    key={`${h.kind}:${h.explanation}`}
                    initial={{ opacity: 0, y: -3 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.22 }}
                    className="rounded-md border border-white/[0.07] px-2 py-1.5"
                    title={h.reason || h.explanation}
                  >
                    <div className="flex items-center gap-1.5">
                      <HypothesisStatus status={h.status} />
                      <span className="font-mono text-[9px] uppercase tracking-wider text-white/40 shrink-0">
                        {h.kind.replace(/_/g, " ")}
                      </span>
                      <span className="ml-auto font-mono text-[9px] text-white/40 tabular-nums shrink-0">
                        {pct(h.probability)}
                      </span>
                    </div>
                    <p className="mt-0.5 font-mono text-[10px] leading-snug text-white/60 truncate">
                      {h.explanation}
                    </p>
                  </motion.li>
                ))}
              </AnimatePresence>
              {hypotheses.length === 0 && (
                <li className="font-mono text-[10px] text-white/30">
                  no failures — no hypotheses needed
                </li>
              )}
            </ul>
          </div>
        </section>
      </div>
    </motion.div>
  );
}

// ------------------------------------------------------------ primitives

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-white/35">
      {children}
    </span>
  );
}

/** Magnitude meter: one hue, fill width encodes value; number in ink. */
function Meter({
  value,
  width,
  label,
  caption,
}: {
  value: number;
  width: number;
  label: string;
  caption?: string;
}) {
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <span className="flex items-center gap-1.5 shrink-0" role="img" aria-label={`${label} ${pct(clamped)}`}>
      {caption && (
        <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-white/30">
          {caption}
        </span>
      )}
      <span className="h-[3px] rounded-full bg-white/[0.08] overflow-hidden" style={{ width }}>
        <span
          className="block h-full rounded-full bg-accent/80 transition-[width] duration-300"
          style={{ width: `${clamped * 100}%` }}
        />
      </span>
      <span className="font-mono text-[10px] text-white/55 tabular-nums w-[30px] text-right">
        {pct(clamped)}
      </span>
    </span>
  );
}

/** Business-progress ring: single hue arc; number in ink at center. */
function ProgressRing({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(1, value));
  const r = 34;
  const c = 2 * Math.PI * r;
  return (
    <span role="img" aria-label={`goal completion ${pct(clamped)}`} className="shrink-0">
      <svg width="84" height="84" viewBox="0 0 84 84">
        <circle cx="42" cy="42" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="5" />
        <circle
          cx="42"
          cy="42"
          r={r}
          fill="none"
          stroke="#34D399"
          strokeOpacity="0.85"
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - clamped)}
          transform="rotate(-90 42 42)"
          style={{ transition: "stroke-dashoffset 400ms cubic-bezier(0.22,1,0.36,1)" }}
        />
        <text
          x="42"
          y="46"
          textAnchor="middle"
          fill="rgba(255,255,255,0.85)"
          fontSize="15"
          fontFamily="var(--font-mono), monospace"
        >
          {pct(clamped)}
        </text>
      </svg>
    </span>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="font-mono text-[9px] uppercase tracking-[0.16em] text-white/30 w-[86px] shrink-0">
        {label}
      </dt>
      <dd className="font-mono text-[12px] text-white/80 tabular-nums">{value}</dd>
    </div>
  );
}

function BudgetBar({
  label,
  used,
  max,
  unit = "",
}: {
  label: string;
  used: number;
  max: number;
  unit?: string;
}) {
  const ratio = max > 0 ? Math.min(1, used / max) : 0;
  return (
    <div className="flex items-center gap-2" role="img" aria-label={`${label} ${used}${unit} of ${max}${unit}`}>
      <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-white/30 w-[74px] shrink-0">
        {label}
      </span>
      <span className="h-[3px] flex-1 rounded-full bg-white/[0.08] overflow-hidden">
        <span
          className="block h-full rounded-full bg-accent/70 transition-[width] duration-300"
          style={{ width: `${ratio * 100}%` }}
        />
      </span>
      <span className="font-mono text-[9px] text-white/45 tabular-nums w-[64px] text-right shrink-0">
        {used}
        {unit} / {max}
        {unit}
      </span>
    </div>
  );
}

/** Hypothesis state: icon + label, never color alone. */
function HypothesisStatus({ status }: { status: HypothesisRow["status"] }) {
  if (status === "confirmed") {
    return (
      <span className="flex items-center gap-1 text-accent/90 shrink-0">
        <CheckCircle2 size={10} aria-hidden />
        <span className="font-mono text-[9px] uppercase tracking-wider">confirmed</span>
      </span>
    );
  }
  if (status === "rejected") {
    return (
      <span className="flex items-center gap-1 text-[#FF7A6B] shrink-0">
        <XCircle size={10} aria-hidden />
        <span className="font-mono text-[9px] uppercase tracking-wider">rejected</span>
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-white/50 shrink-0">
      <Circle size={9} aria-hidden />
      <span className="font-mono text-[9px] uppercase tracking-wider">open</span>
    </span>
  );
}

function pct(v: number) {
  return `${Math.round(v * 100)}%`;
}

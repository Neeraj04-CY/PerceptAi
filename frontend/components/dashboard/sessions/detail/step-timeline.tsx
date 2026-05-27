"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, X, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ApiSessionStep } from "@/lib/api";
import { JsonViewer } from "./json-viewer";

interface Props {
  steps: ApiSessionStep[];
}

const ACTION_EXPLANATIONS: Record<string, string> = {
  browser: "Browser control — launches or attaches a chromium session for the agent.",
  vision: "Visual perception — captures screen frames and grounds the perception graph.",
  plan: "Planning — composes the trajectory of actions needed to satisfy the goal.",
  action: "UI action — performs a click, type, or scroll against a grounded element.",
  click: "Click — issues a mouse click against a perception-grounded UI element.",
  type: "Type — issues keystrokes with human-like pacing.",
  navigate: "Navigation — moves to a new URL or workspace.",
  verify: "Verification — cross-checks the result against expected output.",
  done: "Completion — finalizes the run and persists the trace.",
  intent: "Intent grounding — identifies the user's goal inside the perception graph.",
  embed: "Embedding — converts the current frame into a 768-d perception vector.",
  trace: "Tracing — persists execution context for later replay.",
};

export function StepTimeline({ steps }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const maxDuration = Math.max(...steps.map((s) => Number(s.duration) || 0), 0.001);

  if (!steps?.length) {
    return (
      <div
        className="rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl p-6"
        data-testid="step-timeline"
      >
        <div className="text-[13px] text-white/45 text-center py-8">
          No steps recorded for this session.
        </div>
      </div>
    );
  }

  return (
    <div
      className="rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl p-5 md:p-7"
      data-testid="step-timeline"
    >
      <div className="flex items-center justify-between mb-6">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
          Execution timeline
        </span>
        <span className="font-mono text-[10px] text-white/30">
          {steps.length} {steps.length === 1 ? "step" : "steps"} · tap to inspect
        </span>
      </div>

      <ol className="relative">
        {steps.map((step, i) => (
          <StepRow
            key={`${step.step_number}-${i}`}
            step={step}
            index={i}
            isLast={i === steps.length - 1}
            isOpen={expanded === i}
            onToggle={() => setExpanded((cur) => (cur === i ? null : i))}
            maxDuration={maxDuration}
          />
        ))}
      </ol>
    </div>
  );
}

function StepRow({
  step,
  index,
  isLast,
  isOpen,
  onToggle,
  maxDuration,
}: {
  step: ApiSessionStep;
  index: number;
  isLast: boolean;
  isOpen: boolean;
  onToggle: () => void;
  maxDuration: number;
}) {
  const ok = step.status === "completed";
  const explanation =
    ACTION_EXPLANATIONS[step.action?.toLowerCase()] ||
    "Custom action — runtime executed an agent-defined operation.";

  return (
    <motion.li
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.35, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
      className="relative"
      data-testid={`step-row-${step.step_number}`}
    >
      {!isLast && (
        <span
          className={cn(
            "absolute left-[11px] top-7 bottom-0 w-px",
            ok ? "bg-accent/25" : "bg-[#FF3B3B]/25"
          )}
        />
      )}

      <button
        type="button"
        onClick={onToggle}
        data-testid={`step-toggle-${step.step_number}`}
        className="w-full flex items-start gap-4 py-2.5 text-left group"
      >
        <span
          className={cn(
            "relative z-10 mt-0.5 flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full",
            ok ? "bg-accent text-black" : "bg-[#FF3B3B] text-black"
          )}
          aria-label={ok ? "completed" : "failed"}
        >
          {ok ? <Check size={11} strokeWidth={3} /> : <X size={11} strokeWidth={3} />}
        </span>

        <div className="flex-1 min-w-0 pr-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-[11px] text-accent">
              #{String(step.step_number).padStart(2, "0")}
            </span>
            <span className="text-[13.5px] text-white tracking-tight">
              {step.description}
            </span>
          </div>
          <div className="mt-1.5 flex items-center gap-2 flex-wrap">
            {step.action && (
              <span className="rounded-sm bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-white/55">
                {step.action}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0 mt-1">
          <div className="font-mono text-[11px] text-white/45 tabular-nums">
            {formatDuration(step.duration)}
          </div>
          <motion.span
            animate={{ rotate: isOpen ? 90 : 0 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="text-white/35 group-hover:text-white/70 transition-colors"
          >
            <ChevronRight size={14} />
          </motion.span>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            key="expand"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="ml-[38px] mb-4 mt-2 rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 space-y-4">
              {/* Plain English action explanation */}
              <Field label="What this means">
                <span className="text-[12.5px] text-white/65 leading-relaxed">
                  {explanation}
                </span>
              </Field>

              {/* Precise timestamp */}
              <div className="grid grid-cols-2 gap-4">
                <Field label="Timestamp">
                  <span
                    className="font-mono text-[12px] text-white/75"
                    data-testid={`step-timestamp-${step.step_number}`}
                  >
                    {formatPreciseTimestamp(step.timestamp)}
                  </span>
                </Field>
                <Field label="Duration">
                  <DurationBar
                    duration={Number(step.duration) || 0}
                    max={maxDuration}
                    ok={ok}
                  />
                </Field>
              </div>

              {/* Full JSON */}
              <Field label="Step result">
                <JsonViewer value={step.result ?? step} />
              </Field>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.li>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/35 mb-1.5">
        {label}
      </div>
      {children}
    </div>
  );
}

function DurationBar({
  duration,
  max,
  ok,
}: {
  duration: number;
  max: number;
  ok: boolean;
}) {
  const pct = Math.max(2, (duration / max) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-white/[0.05] overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className={ok ? "h-full bg-accent/80" : "h-full bg-[#FF3B3B]/70"}
        />
      </div>
      <span className="font-mono text-[11px] text-white/65 tabular-nums shrink-0">
        {formatDuration(duration)}
      </span>
    </div>
  );
}

function formatDuration(d: number | undefined | null): string {
  if (d == null || Number.isNaN(d)) return "—";
  const n = Number(d);
  if (n < 1) return `${Math.round(n * 1000)}ms`;
  return `${n.toFixed(2)}s`;
}

function formatPreciseTimestamp(ts: string): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const pad = (n: number, l = 2) => String(n).padStart(l, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(
      d.getMilliseconds(),
      3
    )}`
  );
}

"use client";

import { motion } from "framer-motion";
import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ApiSessionStep } from "@/lib/api";

export function StepTimeline({ steps }: { steps: ApiSessionStep[] }) {
  if (!steps?.length) {
    return (
      <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl p-6">
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
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">
          Execution timeline
        </span>
        <span className="font-mono text-[10px] text-white/30">
          {steps.length} {steps.length === 1 ? "step" : "steps"}
        </span>
      </div>

      <ol className="relative space-y-1">
        {steps.map((step, i) => (
          <StepRow
            key={`${step.step_number}-${i}`}
            step={step}
            index={i}
            isLast={i === steps.length - 1}
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
}: {
  step: ApiSessionStep;
  index: number;
  isLast: boolean;
}) {
  const ok = step.status === "completed";

  return (
    <motion.li
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.35, delay: index * 0.06, ease: [0.22, 1, 0.36, 1] }}
      className="relative flex items-start gap-4 py-2.5"
      data-testid={`step-row-${step.step_number}`}
    >
      {!isLast && (
        <span
          className={cn(
            "absolute left-[11px] top-7 bottom-[-10px] w-px",
            ok ? "bg-accent/25" : "bg-[#FF3B3B]/25"
          )}
        />
      )}

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

      <div className="font-mono text-[11px] text-white/45 shrink-0 mt-1 tabular-nums">
        {formatDuration(step.duration)}
      </div>
    </motion.li>
  );
}

function formatDuration(d: number): string {
  if (d == null || Number.isNaN(d)) return "—";
  if (d < 1) return `${Math.round(d * 1000)}ms`;
  return `${d.toFixed(2)}s`;
}

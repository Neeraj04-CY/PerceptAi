"use client";

import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import type { ApiSessionStep } from "@/lib/api";
import { GlassCard } from "@/components/ui/glass-card";

interface Props {
  steps: ApiSessionStep[];
  status: "completed" | "failed" | "running";
  duration: string;
}

export function generateSummary(
  steps: ApiSessionStep[],
  status: Props["status"],
  duration: string
): string {
  const completedCount = steps.filter((s) => s.status === "completed").length;
  const failedCount = steps.length - completedCount;
  const actions = Array.from(new Set(steps.map((s) => s.action).filter(Boolean)));
  const actionsTxt = actions.length ? actions.join(", ") : "no action types";

  if (status === "running") {
    return `Agent is mid-run — ${completedCount} of ${steps.length} steps completed so far across ${actionsTxt}.`;
  }
  if (status === "failed") {
    return `Agent ran for ${duration} and failed after ${completedCount} successful step${
      completedCount === 1 ? "" : "s"
    }${failedCount > 0 ? ` (${failedCount} failed)` : ""}. Inspected actions: ${actionsTxt}.`;
  }
  return `Agent completed ${completedCount} step${
    completedCount === 1 ? "" : "s"
  } in ${duration} using ${actionsTxt} actions.`;
}

export function ExecutionSummary({ steps, status, duration }: Props) {
  const summary = generateSummary(steps, status, duration);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
    >
      <GlassCard padding="md" data-testid="execution-summary">
        <div className="flex items-center gap-2 mb-3">
          <span className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-accent/25 bg-accent/[0.08] text-accent">
            <Sparkles size={11} strokeWidth={1.6} />
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
            Execution summary
          </span>
          <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.18em] text-white/30">
            generated
          </span>
        </div>
        <p
          className="text-[14px] leading-relaxed text-white/65 italic"
          data-testid="summary-text"
        >
          {summary}
        </p>
      </GlassCard>
    </motion.div>
  );
}

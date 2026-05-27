"use client";

import { motion } from "framer-motion";
import type { ApiSessionStep } from "@/lib/api";
import { GlassCard } from "@/components/ui/glass-card";
import { cn } from "@/lib/utils";

interface Props {
  steps: ApiSessionStep[];
}

function formatDuration(d: number): string {
  if (d == null || Number.isNaN(d)) return "—";
  if (d < 1) return `${Math.round(d * 1000)}ms`;
  return `${d.toFixed(2)}s`;
}

function truncate(value: string, max: number): string {
  if (!value) return "";
  if (value.length <= max) return value;
  return value.slice(0, max).trimEnd() + "…";
}

export function DurationChart({ steps }: Props) {
  if (!steps?.length) return null;

  const total = steps.reduce((acc, s) => acc + (Number(s.duration) || 0), 0);
  const max = Math.max(...steps.map((s) => Number(s.duration) || 0), 0.001);
  if (total <= 0) return null;

  return (
    <GlassCard padding="md" data-testid="duration-chart">
      <div className="flex items-center justify-between mb-4">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
          Step durations
        </span>
        <span className="font-mono text-[10px] text-white/40">
          total {formatDuration(total)}
        </span>
      </div>

      <div className="space-y-2">
        {steps.map((step, i) => {
          const d = Number(step.duration) || 0;
          const pct = (d / max) * 100;
          const ok = step.status === "completed";
          return (
            <motion.div
              key={`${step.step_number}-${i}`}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{
                duration: 0.35,
                delay: Math.min(i * 0.05, 0.5),
                ease: [0.22, 1, 0.36, 1],
              }}
              className="flex items-center gap-3"
              data-testid={`duration-row-${step.step_number}`}
            >
              <span className="w-6 shrink-0 font-mono text-[10px] text-white/35 tabular-nums text-right">
                #{String(step.step_number).padStart(2, "0")}
              </span>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-3 mb-1">
                  <span
                    className="text-[12px] text-white/75 truncate"
                    title={step.description}
                  >
                    {truncate(step.description, 60)}
                  </span>
                  <span className="font-mono text-[11px] text-white/55 shrink-0 tabular-nums">
                    {formatDuration(d)}
                  </span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-white/[0.04] overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{
                      duration: 0.7,
                      delay: 0.1 + i * 0.05,
                      ease: [0.22, 1, 0.36, 1],
                    }}
                    className={cn(
                      "h-full rounded-full",
                      ok ? "bg-accent/80" : "bg-[#FF3B3B]/70"
                    )}
                  />
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </GlassCard>
  );
}

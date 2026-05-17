"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TimelineStep } from "./mock-data";

interface Props {
  steps: TimelineStep[];
  activeIndex: number;
  visible: boolean;
}

export function ExecutionTimeline({ steps, activeIndex, visible }: Props) {
  return (
    <AnimatePresence initial={false}>
      {visible && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="overflow-hidden"
        >
          <div
            className="rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl p-5 md:p-7"
            data-testid="execution-timeline"
          >
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">
                  Execution timeline
                </span>
                <span className="font-mono text-[10px] text-white/30">
                  · {Math.min(activeIndex + 1, steps.length)} / {steps.length}
                </span>
              </div>
              <ProgressBar value={(Math.min(activeIndex + 1, steps.length) / steps.length) * 100} />
            </div>

            <ol className="relative space-y-1">
              {steps.map((step, i) => (
                <TimelineRow
                  key={step.id}
                  step={step}
                  index={i}
                  isLast={i === steps.length - 1}
                  isActive={i === activeIndex && step.status === "running"}
                />
              ))}
            </ol>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="w-32 h-1 rounded-full bg-white/[0.05] overflow-hidden">
      <motion.div
        className="h-full bg-accent"
        animate={{ width: `${value}%` }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      />
    </div>
  );
}

function TimelineRow({
  step,
  index,
  isLast,
  isActive,
}: {
  step: TimelineStep;
  index: number;
  isLast: boolean;
  isActive: boolean;
}) {
  return (
    <motion.li
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, delay: index * 0.06, ease: [0.22, 1, 0.36, 1] }}
      className="relative flex items-start gap-4 py-2.5"
      data-testid={`timeline-step-${index}`}
    >
      {/* Connector */}
      {!isLast && (
        <span
          className={cn(
            "absolute left-[11px] top-7 bottom-[-10px] w-px",
            step.status === "completed" ? "bg-accent/30" : "bg-white/[0.08]"
          )}
        />
      )}

      {/* Indicator */}
      <span
        className={cn(
          "relative z-10 mt-0.5 flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border transition-colors duration-300",
          step.status === "completed" && "border-accent/50 bg-accent/15",
          step.status === "running" && "border-accent/60 bg-accent/15",
          step.status === "failed" && "border-[#FF3B3B]/50 bg-[#FF3B3B]/15",
          (step.status === "pending") && "border-white/10 bg-white/[0.02]"
        )}
      >
        {step.status === "completed" && <Check size={11} className="text-accent" strokeWidth={3} />}
        {step.status === "failed" && <X size={11} className="text-[#FF3B3B]" strokeWidth={3} />}
        {step.status === "running" && (
          <>
            <span className="absolute inset-0 rounded-full bg-accent/30 animate-ping" />
            <span className="relative h-2 w-2 rounded-full bg-accent" />
          </>
        )}
        {step.status === "pending" && <span className="h-1.5 w-1.5 rounded-full bg-white/25" />}
      </span>

      {/* Content */}
      <div className="flex-1 min-w-0 pr-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={cn(
              "text-[13.5px] font-medium tracking-tight transition-colors",
              step.status === "pending" ? "text-white/45" : "text-white"
            )}
          >
            {step.action}
          </span>
          {step.tag && (
            <span className="rounded-sm bg-white/[0.04] px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.16em] text-white/45">
              {step.tag}
            </span>
          )}
          {isActive && (
            <span className="font-mono text-[10px] uppercase tracking-wider text-accent flex items-center gap-1">
              <span className="h-1 w-1 rounded-full bg-accent animate-pulse" />
              in progress
            </span>
          )}
        </div>
        <div className="mt-0.5 text-[12.5px] text-white/45 leading-relaxed truncate">
          {step.description}
        </div>
      </div>

      {/* Duration */}
      <div
        className={cn(
          "font-mono text-[11px] shrink-0 transition-colors mt-1",
          step.status === "completed" ? "text-white/55" : "text-white/25"
        )}
      >
        {step.status === "running" ? <RunningTimer /> : step.status !== "pending" ? step.duration : "—"}
      </div>
    </motion.li>
  );
}

function RunningTimer() {
  return (
    <motion.span
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="text-accent"
    >
      …
    </motion.span>
  );
}

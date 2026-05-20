"use client";

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { ApiSessionStep } from "@/lib/api";

export function RuntimeLogs({ steps }: { steps: ApiSessionStep[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [steps.length]);

  return (
    <div
      className="rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl overflow-hidden"
      data-testid="runtime-logs"
    >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 h-10">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
          runtime · logs
        </span>
        <span className="font-mono text-[10px] text-white/40">
          {steps.length} entries
        </span>
      </div>

      <div
        ref={ref}
        className="bg-[#080808] max-h-[420px] overflow-y-auto px-4 py-3 font-mono text-[12px]"
        style={{ lineHeight: 1.9 }}
      >
        {steps.length === 0 ? (
          <div className="text-white/30 text-[12px]">No log entries.</div>
        ) : (
          steps.map((step, i) => <LogLine key={i} step={step} index={i} />)
        )}
      </div>
    </div>
  );
}

function LogLine({ step, index }: { step: ApiSessionStep; index: number }) {
  const ok = step.status === "completed";
  return (
    <motion.div
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.25, delay: Math.min(index * 0.03, 0.4) }}
      className="flex items-start gap-3"
    >
      <span className="shrink-0 text-white/30">[{formatTimestamp(step.timestamp)}]</span>
      <span
        className={cn(
          "shrink-0 whitespace-pre font-medium",
          ok ? "text-accent" : "text-[#FF3B3B]"
        )}
      >
        {ok ? "OK " : "ERR"}
      </span>
      <span className="text-white/75 break-all flex-1 min-w-0">
        {step.description}
        {step.action && (
          <span className="ml-2 text-white/40">[{step.action}]</span>
        )}
      </span>
    </motion.div>
  );
}

function formatTimestamp(ts: string): string {
  if (!ts) return "--:--:--";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

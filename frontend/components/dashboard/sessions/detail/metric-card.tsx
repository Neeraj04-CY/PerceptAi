"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  icon: ReactNode;
  value: ReactNode;
  trailing?: ReactNode;
  index?: number;
  testId?: string;
}

export function MetricCard({ label, icon, value, trailing, index = 0, testId }: MetricCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
      className="rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl p-4"
      data-testid={testId}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">
          {label}
        </span>
        <span className="text-white/40">{icon}</span>
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">{value}</div>
        {trailing && <div className="shrink-0">{trailing}</div>}
      </div>
    </motion.div>
  );
}

"use client";

import { motion } from "framer-motion";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { staggerItem } from "@/lib/motion";
import type { ReactNode } from "react";

export interface MetricCardProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  trend?: {
    direction: "up" | "down" | "flat";
    value: string;
  };
  className?: string;
  testId?: string;
  trailing?: ReactNode;
}

export function MetricCard({
  label,
  value,
  sub,
  icon,
  trend,
  className,
  testId,
  trailing,
}: MetricCardProps) {
  return (
    <motion.div
      variants={staggerItem}
      className={cn(
        "rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl p-5",
        "transition-colors duration-300 hover:border-white/[0.14]",
        className
      )}
      data-testid={testId}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
          {label}
        </span>
        {icon && (
          <span className="text-white/40 shrink-0" aria-hidden>
            {icon}
          </span>
        )}
      </div>

      <div className="mt-4 flex items-end justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[26px] font-semibold tracking-tight text-white tabular-nums truncate">
            {value}
          </div>
          {sub && (
            <div className="mt-1.5 text-[12px] text-white/45 truncate">{sub}</div>
          )}
        </div>
        {trailing}
      </div>

      {trend && (
        <div className="mt-3 inline-flex items-center gap-1 font-mono text-[10.5px] uppercase tracking-wider">
          {trend.direction === "up" && (
            <>
              <ArrowUpRight size={11} className="text-accent" />
              <span className="text-accent">{trend.value}</span>
            </>
          )}
          {trend.direction === "down" && (
            <>
              <ArrowDownRight size={11} className="text-[#FF3B3B]" />
              <span className="text-[#FF3B3B]">{trend.value}</span>
            </>
          )}
          {trend.direction === "flat" && (
            <span className="text-white/45">— {trend.value}</span>
          )}
        </div>
      )}
    </motion.div>
  );
}

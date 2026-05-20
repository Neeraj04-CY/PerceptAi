"use client";

import { motion } from "framer-motion";
import { pageEntry } from "@/lib/motion";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function PageHeader({
  title,
  description,
  eyebrow,
  action,
  className,
}: PageHeaderProps) {
  return (
    <motion.div
      {...pageEntry}
      className={cn(
        "flex flex-col md:flex-row md:items-end md:justify-between gap-4 pb-6 border-b border-white/[0.06]",
        className
      )}
      data-testid="page-header"
    >
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-2.5 font-mono text-[10px] uppercase tracking-[0.22em] text-accent/90">
            {eyebrow}
          </div>
        )}
        <h1
          className="text-[24px] sm:text-[28px] font-semibold tracking-tight text-white leading-tight"
          data-testid="page-header-title"
        >
          {title}
        </h1>
        {description && (
          <p className="mt-2 text-[13.5px] text-white/55 leading-relaxed max-w-2xl">
            {description}
          </p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </motion.div>
  );
}

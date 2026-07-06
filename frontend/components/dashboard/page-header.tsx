"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/** The single page-title pattern for every dashboard screen. One <h1> per
 * page, a calm subtitle, and a right-aligned actions slot. The top utility
 * bar deliberately does NOT repeat this — it only shows a small breadcrumb. */
export function PageHeader({
  title,
  subtitle,
  actions,
  eyebrow,
  className,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  eyebrow?: string;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between",
        className
      )}
    >
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-accent/70">
            {eyebrow}
          </div>
        )}
        <h1 className="text-[22px] sm:text-[24px] font-semibold tracking-tight text-white leading-tight">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1.5 max-w-2xl text-[13.5px] leading-relaxed text-white/50">
            {subtitle}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </motion.div>
  );
}

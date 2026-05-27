"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export function Switch({
  checked,
  onChange,
  disabled,
  className,
  "data-testid": testId,
  ariaLabel,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  className?: string;
  "data-testid"?: string;
  ariaLabel?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      data-testid={testId}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors duration-200",
        checked
          ? "bg-accent/25 border-accent/50"
          : "bg-white/[0.04] border-white/[0.10] hover:border-white/20",
        disabled && "opacity-50 cursor-not-allowed",
        className
      )}
    >
      <motion.span
        layout
        transition={{ type: "spring", stiffness: 520, damping: 32, mass: 0.6 }}
        className={cn(
          "block h-3.5 w-3.5 rounded-full shadow-sm",
          checked ? "bg-accent ml-auto mr-[3px]" : "bg-white/55 ml-[3px]"
        )}
      />
    </button>
  );
}

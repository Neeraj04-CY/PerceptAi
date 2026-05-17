"use client";

import { cn } from "@/lib/utils";

export type Status = "pending" | "running" | "completed" | "failed" | "queued";

const map: Record<Status, { label: string; dot: string; bg: string; text: string }> = {
  pending: { label: "Pending", dot: "bg-white/30", bg: "bg-white/[0.04]", text: "text-white/50" },
  queued: { label: "Queued", dot: "bg-white/30", bg: "bg-white/[0.04]", text: "text-white/50" },
  running: { label: "Running", dot: "bg-accent animate-pulse", bg: "bg-accent/[0.08]", text: "text-accent" },
  completed: { label: "Completed", dot: "bg-accent", bg: "bg-accent/[0.08]", text: "text-accent" },
  failed: { label: "Failed", dot: "bg-[#FF3B3B]", bg: "bg-[#FF3B3B]/10", text: "text-[#FF3B3B]" },
};

export function StatusPill({
  status,
  label,
  className,
}: {
  status: Status;
  label?: string;
  className?: string;
}) {
  const s = map[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em]",
        s.bg,
        s.text,
        className
      )}
      data-testid={`status-${status}`}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      {label || s.label}
    </span>
  );
}

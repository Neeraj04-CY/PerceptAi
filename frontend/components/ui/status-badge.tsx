import { cn } from "@/lib/utils";

export type BadgeStatus =
  | "completed"
  | "failed"
  | "running"
  | "queued"
  | "pending";

const MAP: Record<BadgeStatus, { label: string; dot: string; bg: string; text: string }> = {
  completed: {
    label: "Completed",
    dot: "bg-accent",
    bg: "bg-accent/[0.08]",
    text: "text-accent",
  },
  failed: {
    label: "Failed",
    dot: "bg-[#FF3B3B]",
    bg: "bg-[#FF3B3B]/10",
    text: "text-[#FF3B3B]",
  },
  running: {
    label: "Running",
    dot: "bg-[#E8C44A] animate-pulse",
    bg: "bg-[#E8C44A]/10",
    text: "text-[#E8C44A]",
  },
  queued: {
    label: "Queued",
    dot: "bg-white/35",
    bg: "bg-white/[0.04]",
    text: "text-white/55",
  },
  pending: {
    label: "Pending",
    dot: "bg-white/35",
    bg: "bg-white/[0.04]",
    text: "text-white/55",
  },
};

export function StatusBadge({
  status,
  label,
  className,
  size = "md",
}: {
  status: BadgeStatus;
  label?: string;
  className?: string;
  size?: "sm" | "md";
}) {
  const s = MAP[status] ?? MAP.pending;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-mono uppercase tracking-[0.16em]",
        size === "sm" ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-0.5 text-[10px]",
        s.bg,
        s.text,
        className
      )}
      data-testid={`status-badge-${status}`}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      {label ?? s.label}
    </span>
  );
}

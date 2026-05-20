import { cn } from "@/lib/utils";

type SessionStatus = "completed" | "failed" | "running";

const map: Record<SessionStatus, { label: string; dot: string; bg: string; text: string }> = {
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
};

export function SessionStatusPill({
  status,
  className,
}: {
  status: SessionStatus;
  className?: string;
}) {
  const s = map[status] ?? map.completed;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em]",
        s.bg,
        s.text,
        className
      )}
      data-testid={`session-status-${status}`}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  );
}

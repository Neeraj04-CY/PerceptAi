// Legacy wrapper — delegates to the unified StatusBadge primitive.
import { StatusBadge } from "@/components/ui/status-badge";

type SessionStatus = "completed" | "failed" | "running";

export function SessionStatusPill({
  status,
  className,
}: {
  status: SessionStatus;
  className?: string;
}) {
  return <StatusBadge status={status} className={className} />;
}

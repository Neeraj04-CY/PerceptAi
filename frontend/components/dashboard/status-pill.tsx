// Legacy wrapper — delegates to the unified StatusBadge primitive.
// Kept to preserve existing imports without parallel UI versions.
import { StatusBadge, type BadgeStatus } from "@/components/ui/status-badge";

export type Status = BadgeStatus;

export function StatusPill({
  status,
  label,
  className,
}: {
  status: Status;
  label?: string;
  className?: string;
}) {
  return <StatusBadge status={status} label={label} className={className} />;
}

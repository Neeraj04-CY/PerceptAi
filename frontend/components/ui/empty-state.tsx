import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  minHeight?: number | string;
  testId?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  minHeight = 280,
  testId = "empty-state",
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center px-6",
        className
      )}
      style={{ minHeight }}
      data-testid={testId}
    >
      {icon && (
        <div className="h-12 w-12 rounded-full border border-white/[0.08] bg-white/[0.02] flex items-center justify-center text-white/35 mb-5">
          {icon}
        </div>
      )}
      <div className="text-[15px] text-white font-medium">{title}</div>
      {description && (
        <p className="mt-2 text-[12.5px] text-white/50 max-w-sm leading-relaxed">
          {description}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

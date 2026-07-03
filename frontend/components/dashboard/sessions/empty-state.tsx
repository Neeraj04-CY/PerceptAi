"use client";

import Link from "next/link";
import { History, ArrowRight } from "lucide-react";

export function EmptyState() {
  return (
    <div
      className="flex flex-col items-center justify-center text-center px-6"
      style={{ minHeight: 300 }}
      data-testid="sessions-empty"
    >
      <div className="h-12 w-12 rounded-full border border-white/[0.08] bg-white/[0.02] flex items-center justify-center text-white/35">
        <History size={22} strokeWidth={1.5} />
      </div>
      <div className="mt-5 text-[15px] text-white font-medium">No sessions yet</div>
      <p className="mt-2 text-[12.5px] text-white/50 max-w-xs">
        Your agent runs will land here. Kick one off and we&apos;ll start tracing.
      </p>
      <Link
        href="/dashboard"
        data-testid="empty-run-first-task"
        className="mt-5 inline-flex items-center gap-1.5 rounded-full bg-accent px-4 h-9 text-[13px] font-medium text-black hover:shadow-[0_0_40px_-8px_rgba(0,255,133,0.55)] transition-shadow"
      >
        Run your first task
        <ArrowRight size={13} />
      </Link>
    </div>
  );
}

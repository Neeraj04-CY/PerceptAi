"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      className="rounded-xl border border-[#FF3B3B]/30 bg-[#FF3B3B]/[0.04] backdrop-blur-xl p-6 flex items-start gap-4"
      data-testid="sessions-error"
    >
      <span className="shrink-0 mt-0.5 inline-flex h-9 w-9 items-center justify-center rounded-full bg-[#FF3B3B]/15 text-[#FF3B3B]">
        <AlertTriangle size={16} />
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-[14px] text-white font-medium">Couldn&apos;t load sessions</div>
        <p className="mt-1 text-[12.5px] text-white/55 leading-relaxed break-words">
          {message}
        </p>
      </div>
      <button
        onClick={onRetry}
        data-testid="sessions-retry"
        className="shrink-0 inline-flex items-center gap-1.5 rounded-md border border-white/[0.10] bg-white/[0.04] hover:bg-white/[0.08] px-3 h-9 text-[12px] text-white transition-colors"
      >
        <RefreshCw size={12} />
        Retry
      </button>
    </div>
  );
}

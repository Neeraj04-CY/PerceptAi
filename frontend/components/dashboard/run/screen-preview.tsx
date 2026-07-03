"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Monitor, Eye } from "lucide-react";
import { cn } from "@/lib/utils";

export function ScreenPreview({
  active,
  stepLabel,
  timestamp,
}: {
  active: boolean;
  stepLabel?: string;
  timestamp?: string;
}) {
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!active) {
      setScreenshotUrl(null);
      return;
    }

    const base = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
    const update = () => setScreenshotUrl(`${base}/api/v1/screenshot?t=${Date.now()}`);
    update();
    const id = setInterval(update, 2000);
    return () => clearInterval(id);
  }, [active]);

  return (
    <div
      className="flex flex-col rounded-xl border border-white/[0.08] bg-[#0A0A0A] overflow-hidden h-full min-h-[280px]"
      data-testid="screen-preview"
    >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 h-10 shrink-0">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
          screen · preview
        </span>
        <span className="font-mono text-[10px] text-white/40">{active ? timestamp : "—"}</span>
      </div>

      <div className="relative flex-1 p-3">
        <div
          className={cn(
            "relative h-full rounded-lg border border-white/[0.08] overflow-hidden",
            active ? "bg-[#0F1115]" : "bg-white/[0.015]"
          )}
        >
          <AnimatePresence mode="wait">
            {!active ? (
              <motion.div
                key="idle"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-white/30"
              >
                <Monitor size={26} strokeWidth={1.4} />
                <div className="text-[12px]">No active capture</div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-white/25">
                  start a task to begin
                </div>
              </motion.div>
            ) : screenshotUrl ? (
              <motion.div
                key="active"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="absolute inset-0"
              >
                <img
                  src={screenshotUrl}
                  alt="Last perception capture"
                  className="h-full w-full object-contain rounded-lg"
                  onError={() => setScreenshotUrl(null)}
                />
                <div className="absolute bottom-2 right-2 font-mono text-[10px] text-white/40 bg-black/60 px-2 py-1 rounded">
                  {timestamp || "last capture"}
                </div>
                <div className="absolute top-2 left-2 flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                  <span className="font-mono text-[10px] text-white/60">LIVE</span>
                </div>
                {stepLabel && (
                  <div className="absolute bottom-3 left-3 right-3 rounded-md border border-white/10 bg-black/60 backdrop-blur px-2.5 py-1.5">
                    <div className="font-mono text-[10px] uppercase tracking-wider text-white/40">
                      current step
                    </div>
                    <div className="text-[12px] text-white truncate">{stepLabel}</div>
                  </div>
                )}
              </motion.div>
            ) : (
              <motion.div
                key="waiting"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-white/30"
              >
                <Eye size={22} strokeWidth={1.4} />
                <div className="text-[12px]">Waiting for capture…</div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-white/25">
                  runtime live
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

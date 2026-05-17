"use client";

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
            ) : (
              <motion.div
                key="active"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="absolute inset-0"
              >
                <MockBrowser />
                {/* Scan line overlay */}
                <motion.div
                  initial={{ y: "-100%" }}
                  animate={{ y: "120%" }}
                  transition={{ duration: 2.6, repeat: Infinity, ease: "linear" }}
                  className="absolute left-0 right-0 h-24 pointer-events-none"
                  style={{
                    background:
                      "linear-gradient(to bottom, transparent, rgba(0,255,133,0.10), transparent)",
                  }}
                />
                {/* Shimmer */}
                <div
                  className="absolute inset-0 pointer-events-none opacity-50"
                  style={{
                    background:
                      "radial-gradient(60% 50% at 50% 50%, rgba(0,255,133,0.04), transparent 70%)",
                  }}
                />
                {/* Perceiving label */}
                <div className="absolute top-3 left-3 flex items-center gap-2 rounded-full border border-accent/30 bg-black/60 backdrop-blur px-2.5 py-1">
                  <Eye size={11} className="text-accent" />
                  <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
                    Perceiving…
                  </span>
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
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

function MockBrowser() {
  return (
    <div className="absolute inset-0 flex flex-col">
      {/* Browser chrome */}
      <div className="h-7 bg-[#16181E] border-b border-white/5 flex items-center px-3 gap-1.5 shrink-0">
        <span className="h-2 w-2 rounded-full bg-white/15" />
        <span className="h-2 w-2 rounded-full bg-white/15" />
        <span className="h-2 w-2 rounded-full bg-white/15" />
        <div className="ml-3 flex-1 h-4 rounded bg-white/[0.04] flex items-center px-2">
          <span className="font-mono text-[9px] text-white/40 truncate">
            https://news.ycombinator.com
          </span>
        </div>
      </div>
      {/* Fake content */}
      <div className="flex-1 p-3 space-y-2">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-accent" />
          <div className="h-2 w-32 rounded bg-white/15" />
        </div>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-2 opacity-80">
            <div className="font-mono text-[9px] text-white/30">{i + 1}.</div>
            <div className="h-1.5 rounded bg-white/[0.07]" style={{ width: `${72 - i * 6}%` }} />
            {i === 2 && (
              <div className="ml-auto h-3 px-1.5 rounded border border-accent/40 bg-accent/10 flex items-center">
                <span className="font-mono text-[8px] uppercase tracking-wider text-accent">target</span>
              </div>
            )}
          </div>
        ))}
        <div className="pt-2 grid grid-cols-3 gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="rounded border border-white/[0.06] bg-white/[0.02] p-2 space-y-1">
              <div className="h-1.5 w-3/4 rounded bg-white/10" />
              <div className="h-1 w-1/2 rounded bg-white/[0.06]" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

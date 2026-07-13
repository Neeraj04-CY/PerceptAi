"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";

const logLines = [
  { t: "00:00.012", tag: "BOOT", msg: "perception runtime online" },
  { t: "00:00.038", tag: "VISION", msg: "ingest stream@ws://agent-7" },
  { t: "00:00.071", tag: "EMBED", msg: "frame#0421 → 768d vector" },
  { t: "00:00.094", tag: "INTENT", msg: "click[btn.checkout] confidence=0.97" },
  { t: "00:00.118", tag: "PLAN", msg: "navigate → /cart → submit" },
  { t: "00:00.142", tag: "TRACE", msg: "span saved · 14ms" },
  { t: "00:00.166", tag: "OK", msg: "agent step committed ✓" },
];

export function TerminalCard() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (count >= logLines.length) {
      const reset = setTimeout(() => setCount(0), 2400);
      return () => clearTimeout(reset);
    }
    const id = setTimeout(() => setCount((c) => c + 1), 520);
    return () => clearTimeout(id);
  }, [count]);

  return (
    <div
      className="relative rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-xl overflow-hidden shadow-[0_20px_80px_-30px_rgba(52,211,153,0.25)]"
      data-testid="terminal-card"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 bg-black/30">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          <span className="h-2.5 w-2.5 rounded-full bg-accent/70" />
        </div>
        <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-white/40">
          percept · live trace
        </div>
        <div className="flex items-center gap-1.5 font-mono text-[10px] text-accent">
          <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-dot" />
          live
        </div>
      </div>

      {/* Body */}
      <div className="px-5 py-5 font-mono text-[12.5px] leading-relaxed">
        <div className="text-white/40">
          <span className="text-accent">$</span> percept run --agent=ops-bot-7
        </div>
        <div className="mt-3 space-y-1.5">
          {logLines.slice(0, count).map((line, i) => (
            <motion.div
              key={`${count}-${i}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.35, ease: "easeOut" }}
              className="flex items-start gap-3"
            >
              <span className="text-white/30 shrink-0">{line.t}</span>
              <span
                className={`shrink-0 inline-flex justify-center min-w-[58px] text-[10px] uppercase tracking-wider rounded-sm px-1.5 py-0.5 ${tagColor(
                  line.tag
                )}`}
              >
                {line.tag}
              </span>
              <span className="text-white/75">{line.msg}</span>
            </motion.div>
          ))}
          {count < logLines.length && (
            <div className="flex items-center gap-2 pt-1">
              <span className="text-white/30">{">"}</span>
              <span className="inline-block h-3 w-1.5 bg-accent animate-pulse-dot" />
            </div>
          )}
        </div>

        {/* Status footer */}
        <div className="mt-6 pt-4 border-t border-white/5 grid grid-cols-3 gap-3 text-[10px] font-mono uppercase tracking-[0.16em]">
          <Stat label="cpu" value="22%" />
          <Stat label="mem" value="612mb" />
          <Stat label="gpu" value="t4 · 41%" />
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-white/30">{label}</span>
      <span className="text-white/80">{value}</span>
    </div>
  );
}

function tagColor(t: string) {
  switch (t) {
    case "OK":
      return "bg-accent/15 text-accent";
    case "VISION":
      return "bg-white/[0.06] text-white/80";
    case "INTENT":
      return "bg-accent/10 text-accent/90";
    case "PLAN":
      return "bg-white/[0.06] text-white/80";
    case "TRACE":
      return "bg-white/[0.05] text-white/60";
    case "EMBED":
      return "bg-white/[0.05] text-white/70";
    default:
      return "bg-white/[0.05] text-white/50";
  }
}

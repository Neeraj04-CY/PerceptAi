"use client";

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { LogLine } from "./mock-data";

const levelClass: Record<LogLine["level"], string> = {
  info: "text-white/55",
  ok: "text-accent",
  warn: "text-[#E8C44A]",
  err: "text-[#FF3B3B]",
};

const levelTag: Record<LogLine["level"], string> = {
  info: "INFO",
  ok: "OK  ",
  warn: "WARN",
  err: "ERR ",
};

export function TerminalLogs({ logs, running }: { logs: LogLine[]; running: boolean }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    ref.current.scrollTop = ref.current.scrollHeight;
  }, [logs.length]);

  return (
    <div
      className="flex flex-col rounded-xl border border-white/[0.08] bg-[#0A0A0A] overflow-hidden h-full min-h-[280px]"
      data-testid="terminal-logs"
    >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 h-10 shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
            runtime · logs
          </span>
        </div>
        <div className="flex items-center gap-1.5 font-mono text-[10px] text-white/40">
          {running && <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />}
          {running ? "streaming" : "idle"}
        </div>
      </div>

      <div
        ref={ref}
        className="flex-1 overflow-y-auto px-4 py-3 font-mono text-[11.5px] leading-[1.65] space-y-0.5"
      >
        {logs.length === 0 && (
          <div className="text-white/25">Waiting for run…</div>
        )}
        {logs.map((l, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2 }}
            className="flex items-start gap-3"
          >
            <span className="shrink-0 text-white/25">{l.ts}</span>
            <span className={cn("shrink-0 whitespace-pre", levelClass[l.level])}>{levelTag[l.level]}</span>
            <span className="text-white/75 break-all">{l.msg}</span>
          </motion.div>
        ))}
        {running && (
          <div className="flex items-center gap-2 pt-1">
            <span className="text-white/30">{">"}</span>
            <span className="inline-block h-3 w-1.5 bg-accent animate-pulse" />
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Loader2, KeyRound } from "lucide-react";
import { cn } from "@/lib/utils";

interface TaskInputProps {
  running: boolean;
  onRun: (task: string) => void;
  onStop?: () => void;
  apiKeyValue?: string;
}

const suggestions = [
  "Open Spotify and play a jazz playlist",
  "Launch Chrome and summarize the latest AI news",
  "Navigate legacy ERP dashboard and export today's invoices",
];

function formatKeyPreview(key: unknown) {
  if (!key) return "No key selected";
  if (typeof key === "string") return key;
  if (typeof key === "object") {
    const record = key as { key_prefix?: string; prefix?: string };
    return record.key_prefix || record.prefix || "pk_••••••••";
  }
  return "pk_••••••••";
}

export function TaskInput({ running, onRun, onStop, apiKeyValue }: TaskInputProps) {
  const [task, setTask] = useState("Launch Chrome and summarize the latest AI news");
  const [focused, setFocused] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    ref.current.style.height = "auto";
    ref.current.style.height = `${Math.min(ref.current.scrollHeight, 220)}px`;
  }, [task]);

  const displayKey = formatKeyPreview(apiKeyValue) || "—";

  return (
    <div
      className={cn(
        "relative rounded-xl border bg-white/[0.03] backdrop-blur-xl transition-all duration-300",
        focused ? "border-accent/35 shadow-[0_0_0_3px_rgba(0,255,133,0.06)]" : "border-white/[0.08]"
      )}
      data-testid="task-input"
    >
      {focused && (
        <div className="pointer-events-none absolute -inset-px rounded-xl bg-gradient-to-b from-accent/10 to-transparent opacity-50" />
      )}

      <div className="relative p-5 md:p-6">
        <div className="flex items-center gap-2 mb-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">
            New task
          </span>
          <span className="h-px flex-1 bg-white/[0.06]" />
          <span className="font-mono text-[10px] text-white/30">⌘↵ to run</span>
        </div>

        <textarea
          ref={ref}
          value={task}
          onChange={(e) => setTask(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && task.trim() && !running) {
              onRun(task);
            }
          }}
          placeholder="What should I automate today?"
          disabled={running}
          rows={1}
          data-testid="task-textarea"
          className="w-full resize-none bg-transparent text-[17px] leading-relaxed text-white placeholder:text-white/25 focus:outline-none font-sans tracking-tight"
        />

        {/* Suggestion chips */}
        {!running && task.length === 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => setTask(s)}
                className="rounded-full border border-white/[0.08] bg-white/[0.02] px-3 py-1 text-[11px] text-white/55 hover:text-white hover:border-white/20 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Bottom row */}
        <div className="mt-5 pt-4 border-t border-white/[0.06] flex flex-wrap items-center justify-between gap-3">
          {/* Key selector */}
          <div className="flex items-center gap-2 h-9 rounded-lg border border-white/[0.08] bg-white/[0.02] px-3">
            <KeyRound size={13} className="text-white/45" />
            <span className="font-mono text-[12px] text-white/75" data-testid="api-key-display">
              {displayKey}
            </span>
            <span className="rounded border border-white/[0.08] px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-white/40">
              runtime
            </span>
          </div>

          {/* Run button */}
          <RunButton running={running} disabled={!task.trim()} onRun={() => onRun(task)} onStop={onStop} />
        </div>
      </div>
    </div>
  );
}

function RunButton({
  running,
  disabled,
  onRun,
  onStop,
}: {
  running: boolean;
  disabled: boolean;
  onRun: () => void;
  onStop?: () => void;
}) {
  return (
    <motion.button
      onClick={running ? onStop : onRun}
      disabled={disabled && !running}
      data-testid="run-task-btn"
      whileTap={{ scale: 0.98 }}
      className={cn(
        "relative inline-flex items-center gap-2 h-10 px-5 rounded-full text-[13px] font-medium transition-all duration-300 overflow-hidden",
        running
          ? "bg-white/[0.04] border border-white/[0.10] text-white hover:bg-white/[0.06]"
          : "bg-accent text-black hover:shadow-[0_0_40px_-8px_rgba(0,255,133,0.6)]",
        disabled && !running && "opacity-40 cursor-not-allowed"
      )}
    >
      <AnimatePresence mode="wait" initial={false}>
        {running ? (
          <motion.span
            key="running"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18 }}
            className="flex items-center gap-2"
          >
            <Loader2 size={14} className="animate-spin text-accent" />
            <span>Running…</span>
            <span className="ml-1 font-mono text-[10px] uppercase tracking-wider text-white/45">stop</span>
          </motion.span>
        ) : (
          <motion.span
            key="idle"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18 }}
            className="flex items-center gap-2"
          >
            <Play size={13} strokeWidth={2.5} fill="currentColor" />
            <span>Run task</span>
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  );
}

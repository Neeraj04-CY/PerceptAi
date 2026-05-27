"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Loader2, ChevronDown, KeyRound, Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface TaskInputProps {
  running: boolean;
  onRun: (task: string, keyId: string) => void;
  onStop?: () => void;
  initialTask?: string;
}

const apiKeys = [
  { id: "k1", label: "production", value: "sk_live_••••f2a1" },
  { id: "k2", label: "staging", value: "sk_test_••••88c4" },
  { id: "k3", label: "local-dev", value: "sk_test_••••0091" },
];

const suggestions = [
  "Open Spotify and play a jazz playlist",
  "Launch Chrome and summarize the latest AI news",
  "Navigate legacy ERP dashboard and export today's invoices",
];

const DEFAULT_TASK = "Launch Chrome and summarize the latest AI news";

export function TaskInput({ running, onRun, onStop, initialTask }: TaskInputProps) {
  const [task, setTask] = useState(initialTask?.trim() ? initialTask : DEFAULT_TASK);
  const [keyId, setKeyId] = useState(apiKeys[0].id);
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  // Sync if initialTask updates (e.g., URL param change)
  useEffect(() => {
    if (initialTask && initialTask.trim()) {
      setTask(initialTask);
    }
  }, [initialTask]);

  useEffect(() => {
    if (!ref.current) return;
    ref.current.style.height = "auto";
    ref.current.style.height = `${Math.min(ref.current.scrollHeight, 220)}px`;
  }, [task]);

  const activeKey = apiKeys.find((k) => k.id === keyId)!;

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
              onRun(task, keyId);
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
          <div className="relative">
            <button
              onClick={() => setOpen((v) => !v)}
              data-testid="api-key-selector"
              className="flex items-center gap-2 h-9 rounded-lg border border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.04] hover:border-white/[0.12] px-3 transition-colors"
            >
              <KeyRound size={13} className="text-white/45" />
              <span className="font-mono text-[12px] text-white/75">{activeKey.value}</span>
              <span className="rounded border border-white/[0.08] px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-white/40">
                {activeKey.label}
              </span>
              <ChevronDown size={12} className={cn("text-white/40 transition-transform", open && "rotate-180")} />
            </button>
            <AnimatePresence>
              {open && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.15 }}
                  className="absolute left-0 top-full mt-1.5 w-72 rounded-lg border border-white/[0.08] bg-[#0D0D0D] shadow-2xl z-20 overflow-hidden"
                >
                  {apiKeys.map((k) => (
                    <button
                      key={k.id}
                      onClick={() => { setKeyId(k.id); setOpen(false); }}
                      className="w-full flex items-center justify-between gap-3 px-3 py-2.5 hover:bg-white/[0.03] text-left transition-colors"
                    >
                      <div className="flex flex-col">
                        <span className="font-mono text-[12px] text-white/85">{k.value}</span>
                        <span className="font-mono text-[10px] uppercase tracking-wider text-white/35 mt-0.5">{k.label}</span>
                      </div>
                      {k.id === keyId && <Check size={14} className="text-accent" />}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Run button */}
          <RunButton running={running} disabled={!task.trim()} onRun={() => onRun(task, keyId)} onStop={onStop} />
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

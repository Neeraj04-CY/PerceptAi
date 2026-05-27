"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  Search,
  Zap,
  History,
  KeyRound,
  BarChart3,
  Clock,
  BookOpen,
  Settings,
  Play,
  Plus,
  LogOut,
  FileText,
  CornerDownLeft,
  ArrowUp,
  ArrowDown,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  zap: Zap,
  history: History,
  key: KeyRound,
  "bar-chart": BarChart3,
  clock: Clock,
  book: BookOpen,
  settings: Settings,
  play: Play,
  plus: Plus,
  "log-out": LogOut,
  "file-text": FileText,
};

type CommandGroup = "Navigation" | "Actions" | "Recent sessions";

interface CommandItem {
  id: string;
  label: string;
  icon: string;
  group: CommandGroup;
  hint?: string;
  action: () => void;
}

interface RecentSession {
  id: string;
  instruction: string;
}

const RECENT_KEY = "perceptai_recent_sessions";

function readRecentSessions(): RecentSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(0, 3) : [];
  } catch {
    return [];
  }
}

export function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [recent, setRecent] = useState<RecentSession[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Build command list (rebuilt each render — cheap)
  const allCommands = useMemo<CommandItem[]>(() => {
    const navAndActions: CommandItem[] = [
      // Navigation
      { id: "run-task", label: "Go to Run Task", icon: "zap", group: "Navigation", hint: "G R", action: () => router.push("/dashboard") },
      { id: "sessions", label: "View Sessions", icon: "history", group: "Navigation", hint: "G S", action: () => router.push("/dashboard/sessions") },
      { id: "api-keys", label: "Manage API Keys", icon: "key", group: "Navigation", hint: "G K", action: () => router.push("/dashboard/keys") },
      { id: "usage", label: "View Usage", icon: "bar-chart", group: "Navigation", action: () => router.push("/dashboard/usage") },
      { id: "scheduled", label: "Scheduled Tasks", icon: "clock", group: "Navigation", action: () => router.push("/dashboard/scheduled") },
      { id: "playbook", label: "Task Playbook", icon: "book", group: "Navigation", action: () => router.push("/dashboard/playbook") },
      { id: "settings", label: "Settings", icon: "settings", group: "Navigation", action: () => router.push("/dashboard/settings") },
      // Actions
      { id: "new-task", label: "Run New Task", icon: "play", group: "Actions", action: () => router.push("/dashboard") },
      { id: "create-key", label: "Create API Key", icon: "plus", group: "Actions", action: () => router.push("/dashboard/keys?create=true") },
      {
        id: "sign-out",
        label: "Sign Out",
        icon: "log-out",
        group: "Actions",
        action: () => {
          try { window.localStorage.clear(); } catch {}
          router.push("/signin");
        },
      },
    ];

    const recentCmds: CommandItem[] = recent.map((s) => ({
      id: `recent-${s.id}`,
      label: s.instruction,
      icon: "file-text",
      group: "Recent sessions",
      action: () => router.push(`/dashboard/sessions/${s.id}`),
    }));

    return [...navAndActions, ...recentCmds];
  }, [router, recent]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allCommands;
    return allCommands.filter((c) => c.label.toLowerCase().includes(q));
  }, [query, allCommands]);

  const grouped = useMemo(() => {
    const out: Record<CommandGroup, CommandItem[]> = {
      Navigation: [],
      Actions: [],
      "Recent sessions": [],
    };
    filtered.forEach((c) => out[c.group].push(c));
    return out;
  }, [filtered]);

  // Reset state on open
  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      setRecent(readRecentSessions());
      // Focus on next tick after animation
      const t = setTimeout(() => inputRef.current?.focus(), 30);
      return () => clearTimeout(t);
    }
  }, [open]);

  // Body scroll lock
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Reset active index when filter changes
  useEffect(() => {
    setActive(0);
  }, [query]);

  // Ensure active stays in bounds
  useEffect(() => {
    if (active >= filtered.length) setActive(0);
  }, [filtered.length, active]);

  const execute = useCallback(
    (cmd?: CommandItem) => {
      const target = cmd || filtered[active];
      if (!target) return;
      onClose();
      // Defer action until close animation tick
      setTimeout(() => target.action(), 50);
    },
    [filtered, active, onClose]
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (filtered.length ? (i + 1) % filtered.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) =>
        filtered.length ? (i - 1 + filtered.length) % filtered.length : 0
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      execute();
    }
  };

  // Scroll active into view
  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector(
      `[data-cmd-index="${active}"]`
    ) as HTMLElement | null;
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [active]);

  // Render rows with running global index for active highlight
  let runningIndex = -1;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="palette-root"
          className="fixed inset-0 z-[80] flex items-start justify-center px-4 pt-[12vh] sm:pt-[15vh]"
          data-testid="command-palette"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15, ease: [0.22, 1, 0.36, 1] }}
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
            data-testid="palette-backdrop"
            aria-hidden
          />

          {/* Palette */}
          <motion.div
            role="dialog"
            aria-label="Command palette"
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -2 }}
            transition={{ duration: 0.15, ease: [0.22, 1, 0.36, 1] }}
            className="relative w-full max-w-[560px] rounded-xl border border-white/[0.12] bg-[#0D0D0D] shadow-2xl overflow-hidden"
            onKeyDown={onKeyDown}
            tabIndex={-1}
          >
            {/* Search */}
            <div className="flex items-center gap-3 h-14 px-4 border-b border-white/[0.06]">
              <Search size={15} className="text-white/40 shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search commands, sessions, tasks..."
                data-testid="palette-input"
                className="flex-1 h-full bg-transparent text-[15px] text-white placeholder:text-white/30 focus:outline-none font-sans"
              />
              <kbd className="shrink-0 rounded-md border border-white/[0.10] bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-white/55">
                ESC
              </kbd>
            </div>

            {/* Results */}
            <div
              ref={listRef}
              className="max-h-[360px] overflow-y-auto py-1"
              data-testid="palette-results"
            >
              {filtered.length === 0 ? (
                <div
                  className="px-4 py-16 text-center text-[13px] text-white/45"
                  data-testid="palette-empty"
                >
                  No commands found
                </div>
              ) : (
                (["Navigation", "Actions", "Recent sessions"] as CommandGroup[]).map((group) => {
                  const items = grouped[group];
                  if (!items.length) return null;
                  return (
                    <div key={group}>
                      <div className="px-4 pt-3 pb-1.5 font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
                        {group}
                      </div>
                      {items.map((cmd) => {
                        runningIndex += 1;
                        const idx = runningIndex;
                        const isActive = idx === active;
                        const Icon = ICONS[cmd.icon] || Zap;
                        return (
                          <button
                            key={cmd.id}
                            data-cmd-index={idx}
                            data-testid={`palette-cmd-${cmd.id}`}
                            onMouseEnter={() => setActive(idx)}
                            onClick={() => execute(cmd)}
                            className={cn(
                              "relative w-full flex items-center gap-3 h-11 px-4 text-left transition-colors",
                              isActive ? "bg-white/[0.05]" : "hover:bg-white/[0.03]"
                            )}
                          >
                            {isActive && (
                              <span
                                className="absolute left-0 top-1/2 -translate-y-1/2 h-6 w-[2px] rounded-r bg-accent"
                                aria-hidden
                              />
                            )}
                            <Icon
                              size={15}
                              strokeWidth={1.6}
                              className={cn(
                                "shrink-0 transition-colors",
                                isActive ? "text-white" : "text-white/55"
                              )}
                            />
                            <span
                              className={cn(
                                "flex-1 text-[13.5px] truncate",
                                isActive ? "text-white" : "text-white/85"
                              )}
                            >
                              {cmd.label}
                            </span>
                            {cmd.hint && (
                              <span className="hidden sm:inline-flex shrink-0 font-mono text-[11px] uppercase tracking-wider text-white/35">
                                {cmd.hint}
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  );
                })
              )}
            </div>

            {/* Footer hint bar */}
            <div className="flex items-center justify-between gap-3 h-9 px-4 border-t border-white/[0.06] bg-black/30">
              <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-wider text-white/40">
                <span className="flex items-center gap-1">
                  <KbdIcon><ArrowUp size={9} /></KbdIcon>
                  <KbdIcon><ArrowDown size={9} /></KbdIcon>
                  navigate
                </span>
                <span className="flex items-center gap-1">
                  <KbdIcon><CornerDownLeft size={9} /></KbdIcon>
                  select
                </span>
              </div>
              <span className="font-mono text-[10px] uppercase tracking-wider text-white/35">
                {filtered.length} result{filtered.length === 1 ? "" : "s"}
              </span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function KbdIcon({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-4 w-4 items-center justify-center rounded-sm border border-white/[0.10] bg-white/[0.04] text-white/55">
      {children}
    </kbd>
  );
}

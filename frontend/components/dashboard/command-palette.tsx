"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  LayoutDashboard,
  PlayCircle,
  Network,
  PenTool,
  Layers,
  ShieldCheck,
  BarChart3,
  Building2,
  KeyRound,
  Search,
  CornerDownLeft,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";

const OPEN_EVENT = "perceptai:open-palette";

/** Fire this to open the palette from anywhere (e.g. the topbar button). */
export function openCommandPalette() {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT));
}

interface Command {
  id: string;
  label: string;
  hint?: string;
  icon: typeof LayoutDashboard;
  keywords?: string;
  run: (router: ReturnType<typeof useRouter>) => void;
}

const nav: Array<{ label: string; href: string; icon: Command["icon"]; hint: string }> = [
  { label: "Mission Control", href: "/dashboard", icon: LayoutDashboard, hint: "Operations overview" },
  { label: "Run", href: "/dashboard/run", icon: PlayCircle, hint: "Start a task or mission" },
  { label: "Missions", href: "/dashboard/missions", icon: Network, hint: "Workforce runs" },
  { label: "Studio", href: "/dashboard/studio", icon: PenTool, hint: "Author workflows" },
  { label: "Sessions", href: "/dashboard/sessions", icon: Layers, hint: "Task history & replay" },
  { label: "Approvals", href: "/dashboard/approvals", icon: ShieldCheck, hint: "Pending decisions" },
  { label: "Analytics", href: "/dashboard/analytics", icon: BarChart3, hint: "Usage & outcomes" },
  { label: "Organization", href: "/dashboard/org", icon: Building2, hint: "Members, workspaces, secrets" },
  { label: "API Keys", href: "/dashboard/keys", icon: KeyRound, hint: "Credentials" },
];

const commands: Command[] = [
  ...nav.map((n) => ({
    id: `nav:${n.href}`,
    label: n.label,
    hint: n.hint,
    icon: n.icon,
    keywords: `${n.label} ${n.hint}`,
    run: (router: ReturnType<typeof useRouter>) => router.push(n.href),
  })),
  {
    id: "action:sign-out",
    label: "Sign out",
    hint: "End this session",
    icon: LogOut,
    keywords: "sign out logout log out",
    run: (router) => {
      try {
        window.localStorage.removeItem("perceptai_token");
        document.cookie = "perceptai_token=; Max-Age=0; path=/";
      } catch {
        /* ignore */
      }
      router.push("/signin");
    },
  },
];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) =>
      (c.keywords || c.label).toLowerCase().includes(q)
    );
  }, [query]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setActive(0);
  }, []);

  const runCommand = useCallback(
    (cmd: Command) => {
      close();
      cmd.run(router);
    },
    [close, router]
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape") {
        close();
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_EVENT, onOpen as EventListener);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_EVENT, onOpen as EventListener);
    };
  }, [close]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30);
  }, [open]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  const onListKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && results[active]) {
      e.preventDefault();
      runCommand(results[active]);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[100] flex items-start justify-center bg-black/60 backdrop-blur-sm pt-[12vh] px-4"
          onClick={close}
        >
          <motion.div
            initial={{ opacity: 0, y: -12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="w-full max-w-[560px] overflow-hidden rounded-2xl border border-white/[0.1] bg-[#0B0B0C] shadow-2xl shadow-black/60"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={onListKey}
          >
            <div className="flex items-center gap-3 border-b border-white/[0.06] px-4">
              <Search size={16} className="text-white/35 shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search pages and actions…"
                className="h-12 w-full bg-transparent text-[14px] text-white placeholder:text-white/30 outline-none"
              />
              <kbd className="rounded border border-white/[0.1] px-1.5 py-0.5 font-mono text-[10px] text-white/35">
                ESC
              </kbd>
            </div>
            <div className="max-h-[340px] overflow-y-auto p-2">
              {results.length === 0 ? (
                <div className="px-3 py-6 text-center text-[13px] text-white/35">
                  No matches for &ldquo;{query}&rdquo;
                </div>
              ) : (
                results.map((cmd, i) => {
                  const Icon = cmd.icon;
                  return (
                    <button
                      key={cmd.id}
                      onMouseEnter={() => setActive(i)}
                      onClick={() => runCommand(cmd)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                        i === active ? "bg-white/[0.06]" : "hover:bg-white/[0.03]"
                      )}
                    >
                      <span
                        className={cn(
                          "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
                          i === active
                            ? "border-accent/30 bg-accent/10 text-accent"
                            : "border-white/[0.08] bg-white/[0.02] text-white/55"
                        )}
                      >
                        <Icon size={15} strokeWidth={1.7} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13.5px] text-white/90">
                          {cmd.label}
                        </span>
                        {cmd.hint && (
                          <span className="block truncate text-[11.5px] text-white/40">
                            {cmd.hint}
                          </span>
                        )}
                      </span>
                      {i === active && (
                        <CornerDownLeft size={14} className="shrink-0 text-white/30" />
                      )}
                    </button>
                  );
                })
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

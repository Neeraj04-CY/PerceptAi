"use client";

import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Search, Bell, Command } from "lucide-react";

const titles: Record<string, { title: string; sub: string }> = {
  "/dashboard": { title: "Run Task", sub: "Spin up a perception-driven agent run in seconds" },
  "/dashboard/sessions": { title: "Sessions", sub: "Replay, audit, and triage every agent run" },
  "/dashboard/keys": { title: "API Keys", sub: "Manage credentials for production and dev environments" },
};

export function Topbar() {
  const pathname = usePathname();
  const meta = titles[pathname] || { title: "Dashboard", sub: "" };

  return (
    <header
      className="sticky top-0 z-30 h-[64px] border-b border-white/[0.06] bg-[#050505]/85 backdrop-blur-xl"
      data-testid="topbar"
    >
      <div className="h-full px-6 flex items-center justify-between gap-6">
        <motion.div
          key={pathname}
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="min-w-0"
        >
          <div className="flex items-center gap-2">
            <h1 className="text-[15px] font-semibold tracking-tight text-white truncate" data-testid="topbar-title">
              {meta.title}
            </h1>
            <span className="hidden sm:inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-white/35">
              <span className="h-1 w-1 rounded-full bg-accent animate-pulse" />
              runtime online
            </span>
          </div>
          <p className="hidden md:block text-[12px] text-white/45 mt-0.5 truncate">{meta.sub}</p>
        </motion.div>

        <div className="flex items-center gap-2">
          <button
            className="hidden md:flex items-center gap-2.5 h-9 px-3 rounded-lg border border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.04] transition-colors text-[12px] text-white/55"
            data-testid="topbar-search"
          >
            <Search size={13} />
            <span>Search sessions, keys…</span>
            <span className="ml-3 flex items-center gap-0.5 rounded-md border border-white/[0.08] px-1.5 py-0.5 font-mono text-[10px] text-white/40">
              <Command size={9} /> K
            </span>
          </button>
          <button
            className="relative h-9 w-9 rounded-lg border border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.04] transition-colors flex items-center justify-center text-white/60"
            data-testid="topbar-notifications"
            aria-label="Notifications"
          >
            <Bell size={14} />
            <span className="absolute top-2 right-2 h-1.5 w-1.5 rounded-full bg-accent" />
          </button>
        </div>
      </div>
    </header>
  );
}

"use client";

import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Search, Bell, Command } from "lucide-react";
import { useCommandPalette } from "@/components/dashboard/command-palette-provider";

const titles: Record<string, { title: string; sub: string }> = {
  "/dashboard": { title: "Run Task", sub: "Spin up a perception-driven agent run in seconds" },
  "/dashboard/overview": { title: "Overview", sub: "Monitor executions, runtime health, and platform activity" },
  "/dashboard/playbook": { title: "Playbook", sub: "Ready-to-run agent templates" },
  "/dashboard/sessions": { title: "Sessions", sub: "Replay, audit, and triage every agent run" },
  "/dashboard/scheduled": { title: "Scheduled Tasks", sub: "Automate recurring agent runs on your schedule" },
  "/dashboard/keys": { title: "API Keys", sub: "Manage credentials for production and dev environments" },
};

function matchTitle(pathname: string) {
  if (pathname.startsWith("/dashboard/sessions/") && pathname !== "/dashboard/sessions") {
    return { title: "Session detail", sub: "Replay traces and inspect step-level perception" };
  }
  return titles[pathname] || { title: "Dashboard", sub: "" };
}

export function Topbar() {
  const pathname = usePathname();
  const meta = matchTitle(pathname);
  const palette = useCommandPalette();

  return (
    <header
      className="sticky top-0 z-30 h-[64px] border-b border-white/[0.06] bg-[#050505]/85 backdrop-blur-xl"
      data-testid="topbar"
    >
      <div className="h-full px-4 sm:px-6 lg:px-8 flex items-center justify-between gap-6">
        <motion.div
          key={pathname}
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="min-w-0 flex items-center gap-3"
        >
          <RuntimeIndicator />
          <EnvBadge env="production" />
          <div className="hidden lg:block h-5 w-px bg-white/[0.08]" />
          <div className="hidden lg:block min-w-0">
            <span className="text-[13.5px] text-white truncate" data-testid="topbar-title">
              {meta.title}
            </span>
            <span className="ml-3 text-[12px] text-white/40 truncate">{meta.sub}</span>
          </div>
        </motion.div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => palette.open()}
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

function RuntimeIndicator() {
  return (
    <div
      className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.02] px-2.5 h-7"
      data-testid="runtime-indicator"
    >
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-60 animate-ping" />
        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-accent" />
      </span>
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/70">
        Runtime online
      </span>
    </div>
  );
}

function EnvBadge({ env }: { env: "production" | "staging" | "development" }) {
  const map = {
    production: "bg-accent/10 text-accent border-accent/25",
    staging: "bg-[#E8C44A]/10 text-[#E8C44A] border-[#E8C44A]/25",
    development: "bg-white/[0.04] text-white/60 border-white/[0.10]",
  } as const;
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 h-6 font-mono text-[10px] uppercase tracking-[0.2em] ${map[env]}`}
      data-testid="env-badge"
    >
      {env}
    </span>
  );
}

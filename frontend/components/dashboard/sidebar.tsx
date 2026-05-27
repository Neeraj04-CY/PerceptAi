"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  PlayCircle,
  Layers,
  KeyRound,
  BarChart3,
  Settings,
  CalendarClock,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { label: "Overview", href: "/dashboard/overview", icon: LayoutDashboard, testid: "nav-overview", enabled: true },
  { label: "Run Task", href: "/dashboard", icon: PlayCircle, testid: "nav-run", enabled: true },
  { label: "Sessions", href: "/dashboard/sessions", icon: Layers, testid: "nav-sessions", enabled: true },
  { label: "Scheduled", href: "/dashboard/scheduled", icon: CalendarClock, testid: "nav-scheduled", enabled: true },
  { label: "API Keys", href: "/dashboard/keys", icon: KeyRound, testid: "nav-keys", enabled: true },
  { label: "Analytics", href: "#", icon: BarChart3, testid: "nav-analytics", enabled: false },
  { label: "Settings", href: "#", icon: Settings, testid: "nav-settings", enabled: false },
];

export interface SidebarUser {
  email?: string;
  plan?: string;
  initials?: string;
}

export function Sidebar({ user }: { user?: SidebarUser }) {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();

  const initials =
    user?.initials ||
    (user?.email
      ? user.email.split("@")[0].slice(0, 2).toUpperCase()
      : "PA");
  const emailDisplay = user?.email || "you@perceptai.dev";

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 h-screen border-r border-white/[0.06] bg-[#0A0A0A] flex-col transition-[width] duration-300 ease-out hidden md:flex",
        collapsed ? "w-[64px]" : "w-[240px]"
      )}
      data-testid="sidebar"
    >
      {/* Logo */}
      <Link
        href="/"
        className={cn(
          "flex items-center gap-2.5 h-[64px] border-b border-white/[0.06] px-4 shrink-0",
          collapsed && "justify-center px-0"
        )}
        data-testid="sidebar-logo"
      >
        <div className="relative h-7 w-7 shrink-0">
          <div className="absolute inset-0 rounded-md border border-accent/40" />
          <div className="absolute inset-[4px] rounded-[3px] bg-accent/15" />
          <div className="absolute inset-[9px] rounded-[2px] bg-accent" />
        </div>
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.18 }}
              className="flex items-center gap-2 min-w-0"
            >
              <span className="font-display tracking-[0.12em] text-[15px] text-white truncate">
                PERCEPT<span className="text-accent">AI</span>
              </span>
              <span className="rounded-sm border border-accent/30 bg-accent/10 px-1.5 py-[2px] font-mono text-[9px] uppercase tracking-[0.18em] text-accent">
                Beta
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </Link>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-0.5">
        {nav.map((item) => {
          const active = item.enabled && pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.label}
              href={item.enabled ? item.href : "#"}
              data-testid={item.testid}
              className={cn(
                "group relative flex items-center gap-3 rounded-lg px-3 h-9 text-[13px] transition-colors",
                active
                  ? "bg-white/[0.04] text-white"
                  : "text-white/55 hover:text-white hover:bg-white/[0.02]",
                !item.enabled && "opacity-40 cursor-not-allowed pointer-events-none",
                collapsed && "justify-center px-0"
              )}
            >
              {active && (
                <motion.span
                  layoutId="sidebar-active"
                  className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[2px] rounded-r bg-accent"
                  transition={{ type: "spring", stiffness: 380, damping: 30 }}
                />
              )}
              <Icon size={16} strokeWidth={1.6} className="shrink-0" />
              {!collapsed && <span className="truncate flex-1">{item.label}</span>}
              {!collapsed && !item.enabled && (
                <span className="text-[9px] font-mono uppercase tracking-wider text-white/30">
                  soon
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* User */}
      <div className="border-t border-white/[0.06] p-3">
        <div
          className={cn(
            "flex items-center gap-3 rounded-lg p-2 hover:bg-white/[0.02] transition-colors",
            collapsed && "justify-center"
          )}
          data-testid="sidebar-user"
        >
          <div className="h-8 w-8 rounded-full bg-gradient-to-br from-accent/60 to-accent/20 flex items-center justify-center text-[11px] font-medium text-black shrink-0">
            {initials}
          </div>
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <div className="text-[12.5px] text-white truncate" data-testid="sidebar-user-email">
                {emailDisplay}
              </div>
              <div className="text-[11px] text-white/40 truncate font-mono">
                {user?.plan || "pro · seat 01"}
              </div>
            </div>
          )}
        </div>
        <button
          onClick={() => setCollapsed((v) => !v)}
          data-testid="sidebar-collapse"
          className={cn(
            "mt-2 flex items-center gap-2 rounded-md px-2.5 h-8 text-[11px] font-mono uppercase tracking-wider text-white/40 hover:text-white hover:bg-white/[0.03] w-full transition-colors",
            collapsed && "justify-center"
          )}
        >
          {collapsed ? (
            <ChevronsRight size={14} />
          ) : (
            <>
              <ChevronsLeft size={14} /> Collapse
            </>
          )}
        </button>
      </div>
    </aside>
  );
}

export function MobileBottomNav() {
  const pathname = usePathname();
  return (
    <div
      className="md:hidden fixed bottom-0 inset-x-0 z-40 border-t border-white/[0.08] bg-[#0A0A0A]/95 backdrop-blur-xl"
      data-testid="mobile-bottom-nav"
    >
      <div className="flex items-center justify-around h-16 px-2">
        {nav
          .filter((n) => n.enabled)
          .map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.label}
                href={item.href}
                className={cn(
                  "flex flex-col items-center justify-center gap-1 flex-1 h-full text-[10px] font-mono uppercase tracking-wider",
                  active ? "text-accent" : "text-white/45"
                )}
              >
                <Icon size={18} strokeWidth={1.6} />
                <span>{item.label}</span>
              </Link>
            );
          })}
      </div>
    </div>
  );
}

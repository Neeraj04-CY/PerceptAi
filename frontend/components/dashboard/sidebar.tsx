"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  PlayCircle,
  Network,
  PenTool,
  Layers,
  ShieldCheck,
  KeyRound,
  BarChart3,
  Building2,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { label: "Mission Control", href: "/dashboard", icon: LayoutDashboard, testid: "nav-home", enabled: true },
  { label: "Run", href: "/dashboard/run", icon: PlayCircle, testid: "nav-run", enabled: true },
  { label: "Missions", href: "/dashboard/missions", icon: Network, testid: "nav-missions", enabled: true },
  { label: "Studio", href: "/dashboard/studio", icon: PenTool, testid: "nav-studio", enabled: true },
  { label: "Sessions", href: "/dashboard/sessions", icon: Layers, testid: "nav-sessions", enabled: true },
  { label: "Approvals", href: "/dashboard/approvals", icon: ShieldCheck, testid: "nav-approvals", enabled: true },
  { label: "Analytics", href: "/dashboard/analytics", icon: BarChart3, testid: "nav-analytics", enabled: true },
  { label: "Organization", href: "/dashboard/org", icon: Building2, testid: "nav-org", enabled: true },
  { label: "API Keys", href: "/dashboard/keys", icon: KeyRound, testid: "nav-keys", enabled: true },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const [user, setUser] = useState<{ email?: string; sub?: string }>({});

  useEffect(() => {
    const readUser = () => {
      const token = window.localStorage.getItem("perceptai_token");
      const payload = decodeJwt(token);
      setUser({ email: payload?.email, sub: payload?.sub });
    };
    readUser();
    const handler = () => readUser();
    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }, []);

  const initials = useMemo(() => {
    const source = user.email || user.sub || "";
    const parts = source.split(/[^a-zA-Z0-9]/).filter(Boolean);
    const letters = parts.slice(0, 2).map((p) => p[0] || "").join("");
    return letters ? letters.toUpperCase() : "??";
  }, [user.email, user.sub]);

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 h-screen border-r border-white/[0.06] bg-[#0A0A0A] flex flex-col transition-[width] duration-300 ease-out hidden md:flex",
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
      <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-1">
        {nav.map((item) => {
          const active = item.enabled && isActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.label}
              href={item.enabled ? item.href : "#"}
              data-testid={item.testid}
              className={cn(
                "group relative flex items-center gap-3 rounded-lg px-3 h-9 text-sm transition-colors",
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
              {!collapsed && (
                <span className="truncate flex-1 text-[13px]">{item.label}</span>
              )}
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
              <div className="text-[13px] text-white truncate">
                {user.email || "Signed out"}
              </div>
              <div className="text-[11px] text-white/40 truncate font-mono">
                {user.sub ? `user · ${user.sub.slice(0, 8)}` : "no active session"}
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
          {collapsed ? <ChevronsRight size={14} /> : <><ChevronsLeft size={14} /> Collapse</>}
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
        {nav.filter((n) => n.enabled).slice(0, 5).map((item) => {
          const Icon = item.icon;
          const active = isActive(pathname, item.href);
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

function decodeJwt(token: string | null): { email?: string; sub?: string } | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length < 2) return null;
  try {
    const payload = parts[1]
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(parts[1].length / 4) * 4, "=");
    const json = atob(payload);
    return JSON.parse(json) as { email?: string; sub?: string };
  } catch {
    return null;
  }
}

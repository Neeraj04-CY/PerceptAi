"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Sunrise,
  Users,
  History,
  BookOpen,
  Fingerprint,
  ShieldCheck,
  Settings2,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getApprovals,
  getDashboardStats,
  getMemory,
  getWorkflows,
} from "@/lib/api";

// Progressive disclosure: a section earns its place in navigation only
// once it holds real data — a brand-new account sees Home and Settings
// and nothing else. Presence is cached so returning users never watch
// the nav pop in.
interface NavPresence {
  operations: boolean;
  workforce: boolean;
  knowledge: boolean;
  approvals: boolean;
}
const PRESENCE_KEY = "perceptai_nav_presence";
const NO_PRESENCE: NavPresence = {
  operations: false, workforce: false, knowledge: false, approvals: false,
};

function useNavPresence(): NavPresence {
  const [presence, setPresence] = useState<NavPresence>(() => {
    try {
      const raw = window.localStorage.getItem(PRESENCE_KEY);
      if (raw) return { ...NO_PRESENCE, ...(JSON.parse(raw) as NavPresence) };
    } catch { /* first visit */ }
    return NO_PRESENCE;
  });

  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled([
      getDashboardStats(controller.signal),
      getWorkflows(controller.signal),
      getApprovals("all", controller.signal),
      getMemory(controller.signal),
    ]).then(([stats, workflows, approvals, memory]) => {
      const sessions = stats.status === "fulfilled" ? stats.value.total_sessions : 0;
      const wfs = workflows.status === "fulfilled" ? workflows.value.length : 0;
      const aps = approvals.status === "fulfilled" ? approvals.value.length : 0;
      const lessons = memory.status === "fulfilled" ? memory.value.lessons.length : 0;
      const next: NavPresence = {
        operations: sessions > 0,
        workforce: wfs > 0 || sessions > 0,
        knowledge: lessons > 0 || sessions > 0,
        approvals: aps > 0,
      };
      setPresence((prev) => {
        // Sections never disappear once earned — nav must feel stable.
        const merged = {
          operations: prev.operations || next.operations,
          workforce: prev.workforce || next.workforce,
          knowledge: prev.knowledge || next.knowledge,
          approvals: prev.approvals || next.approvals,
        };
        try { window.localStorage.setItem(PRESENCE_KEY, JSON.stringify(merged)); } catch { /* ok */ }
        return merged;
      });
    });
    return () => controller.abort();
  }, []);

  return presence;
}

const nav = [
  { label: "Home", href: "/dashboard", icon: Sunrise, testid: "nav-home", enabled: true,
    matches: ["/dashboard/run"], gate: null as keyof NavPresence | null },
  { label: "Workforce", href: "/dashboard/workforce", icon: Users, testid: "nav-workforce", enabled: true,
    matches: ["/dashboard/templates", "/dashboard/studio"], gate: "workforce" as const },
  { label: "Operations", href: "/dashboard/operations", icon: History, testid: "nav-operations", enabled: true,
    matches: ["/dashboard/sessions", "/dashboard/missions"], gate: "operations" as const },
  { label: "Knowledge", href: "/dashboard/knowledge", icon: BookOpen, testid: "nav-knowledge", enabled: true,
    matches: ["/dashboard/answers", "/dashboard/analytics"], gate: "knowledge" as const },
  { label: "Evidence", href: "/dashboard/evidence", icon: Fingerprint, testid: "nav-evidence", enabled: true,
    matches: [] as string[], gate: "operations" as const },
  { label: "Approvals", href: "/dashboard/approvals", icon: ShieldCheck, testid: "nav-approvals", enabled: true,
    matches: [] as string[], gate: "approvals" as const },
  { label: "Settings", href: "/dashboard/settings", icon: Settings2, testid: "nav-settings", enabled: true,
    matches: ["/dashboard/keys", "/dashboard/runners", "/dashboard/org"], gate: null },
];

function isActive(pathname: string, href: string, matches: string[] = []): boolean {
  if (href === "/dashboard") return pathname === href;
  if (pathname === href || pathname.startsWith(`${href}/`)) return true;
  return matches.some((m) => pathname === m || pathname.startsWith(`${m}/`));
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const presence = useNavPresence();
  const visible = nav.filter((item) => item.gate === null || presence[item.gate]);
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
        {visible.map((item) => {
          const active = item.enabled && isActive(pathname, item.href, item.matches);
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
  const presence = useNavPresence();
  const visible = nav.filter((item) => item.gate === null || presence[item.gate]);
  return (
    <div
      className="md:hidden fixed bottom-0 inset-x-0 z-40 border-t border-white/[0.08] bg-[#0A0A0A]/95 backdrop-blur-xl"
      data-testid="mobile-bottom-nav"
    >
      <div className="flex items-center justify-around h-16 px-2">
        {visible.filter((n) => n.enabled).slice(0, 5).map((item) => {
          const Icon = item.icon;
          const active = isActive(pathname, item.href, item.matches);
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

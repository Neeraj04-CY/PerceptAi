"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { ChevronRight, Command, Search } from "lucide-react";
import { RuntimeHealth } from "./runtime-health";
import { openCommandPalette } from "./command-palette";

/** Slim utility bar. It shows a small breadcrumb for context (never a big
 * page title — pages own that via <PageHeader>), the honest runtime status,
 * and a real ⌘K command palette trigger. No fake controls. */

const SECTIONS: Record<string, string> = {
  "/dashboard": "Today",
  "/dashboard/run": "Assign work",
  "/dashboard/operations": "Operations",
  "/dashboard/missions": "Operations",
  "/dashboard/sessions": "Operations",
  "/dashboard/templates": "Business Templates",
  "/dashboard/studio": "Business Templates",
  "/dashboard/approvals": "Approvals",
  "/dashboard/answers": "Answers",
  "/dashboard/analytics": "Supporting detail",
  "/dashboard/settings": "Settings",
  "/dashboard/org": "Workspace",
  "/dashboard/keys": "Developer API",
  "/dashboard/runners": "Machines",
};

function crumbs(pathname: string): Array<{ label: string; href?: string }> {
  // Exact match first
  if (SECTIONS[pathname]) return [{ label: SECTIONS[pathname] }];
  // Detail routes: /dashboard/<section>/<id>
  const parts = pathname.split("/").filter(Boolean); // ["dashboard","sessions","abc"]
  if (parts.length >= 3) {
    const sectionHref = `/${parts[0]}/${parts[1]}`;
    const section = SECTIONS[sectionHref] || cap(parts[1]);
    const tail = parts[2].length > 10 ? `${parts[2].slice(0, 8)}…` : parts[2];
    return [
      { label: section, href: sectionHref },
      { label: tail },
    ];
  }
  return [{ label: SECTIONS[`/${parts.join("/")}`] || "Dashboard" }];
}

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function Topbar() {
  const pathname = usePathname();
  const trail = crumbs(pathname);

  return (
    <header className="sticky top-0 z-30 h-[56px] border-b border-white/[0.06] bg-[#050505]/80 backdrop-blur-xl">
      <div className="flex h-full items-center justify-between gap-4 px-4 sm:px-6">
        {/* Breadcrumb — context, not a title */}
        <nav className="flex min-w-0 items-center gap-1.5 text-[13px]" aria-label="Breadcrumb">
          {trail.map((c, i) => (
            <span key={i} className="flex min-w-0 items-center gap-1.5">
              {i > 0 && <ChevronRight size={13} className="shrink-0 text-white/25" />}
              {c.href ? (
                <Link
                  href={c.href}
                  className="truncate text-white/45 transition-colors hover:text-white/80"
                >
                  {c.label}
                </Link>
              ) : (
                <span className="truncate font-medium text-white/85">{c.label}</span>
              )}
            </span>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <button
            onClick={openCommandPalette}
            data-testid="topbar-command"
            className="hidden items-center gap-2.5 rounded-lg border border-white/[0.08] bg-white/[0.02] px-3 h-8 text-[12.5px] text-white/45 transition-colors hover:bg-white/[0.04] hover:text-white/70 md:flex"
          >
            <Search size={13} />
            <span>Search</span>
            <span className="ml-2 flex items-center gap-0.5 rounded border border-white/[0.1] px-1.5 py-0.5 font-mono text-[10px] text-white/40">
              <Command size={9} /> K
            </span>
          </button>
          <button
            onClick={openCommandPalette}
            aria-label="Search"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/[0.08] bg-white/[0.02] text-white/55 transition-colors hover:bg-white/[0.04] md:hidden"
          >
            <Search size={14} />
          </button>
          <RuntimeHealth />
        </div>
      </div>
    </header>
  );
}

"use client";

/** Settings — one place for everything that configures the platform.
 * Operational surfaces (workspace, people, secrets, policies) live in
 * their existing pages; this hub is the single door. Machines (runners)
 * are deliberately here, not in the nav: infrastructure serves the
 * workforce, it isn't the product. */

import Link from "next/link";
import { ArrowUpRight, Building2, KeyRound, Server, ShieldCheck, type LucideIcon } from "lucide-react";

const groups: Array<{
  title: string;
  items: Array<{ icon: LucideIcon; label: string; description: string; href: string }>;
}> = [
  {
    title: "Workspace",
    items: [
      { icon: Building2, label: "Workspace & people", href: "/dashboard/org",
        description: "Members, roles, workspaces and environments." },
      { icon: ShieldCheck, label: "Policies, secrets & audit", href: "/dashboard/org",
        description: "Approval gates, data-egress policy, the credential vault, and the audit trail." },
    ],
  },
  {
    title: "Advanced",
    items: [
      { icon: Server, label: "Machines", href: "/dashboard/runners",
        description: "The desktops your workforce operates. Connect one to run work unattended." },
      { icon: KeyRound, label: "Developer API", href: "/dashboard/keys",
        description: "API keys for driving the platform programmatically." },
    ],
  },
];

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <header className="pt-6 pb-10">
        <h1 className="text-[24px] font-semibold tracking-tight text-white">Settings</h1>
        <p className="mt-1 text-[13px] text-white/40">
          Everything that governs how your workforce operates.
        </p>
      </header>

      <div className="space-y-10 pb-16">
        {groups.map((group) => (
          <section key={group.title}>
            <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">
              {group.title}
            </h2>
            <div className="mt-4 space-y-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <Link key={item.label} href={item.href}
                        className="group flex items-start gap-4 rounded-xl px-4 -mx-4 py-4 hover:bg-white/[0.02] transition-colors">
                    <Icon size={16} className="mt-0.5 text-white/35 group-hover:text-white/60 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 text-[14px] text-white/85 group-hover:text-white">
                        {item.label}
                        <ArrowUpRight size={12} className="text-white/25 group-hover:text-white/50" />
                      </div>
                      <p className="mt-0.5 text-[12.5px] leading-relaxed text-white/40">
                        {item.description}
                      </p>
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

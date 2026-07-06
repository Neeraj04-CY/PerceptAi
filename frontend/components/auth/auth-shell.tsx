"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Eye, ShieldCheck, Workflow } from "lucide-react";

/** Premium split-screen auth: a brand/proof panel on the left (desktop only)
 * and the form on the right. On laptops and phones it collapses to a single
 * centered column. This is the first screen a customer sees — it should read
 * as calm, credible and product-led, not a bare form on a black void. */

const PROOF = [
  {
    icon: Eye,
    title: "One world model, many sources",
    body: "UI Automation, OCR and vision fused into a single confidence-scored view of the screen.",
  },
  {
    icon: Workflow,
    title: "Plain English in, outcomes out",
    body: "Describe the goal. An agent perceives, plans, acts and verifies against real OS state.",
  },
  {
    icon: ShieldCheck,
    title: "Honest by design",
    body: "Every observation carries source-weighted confidence. Nothing runs silently, nothing is faked.",
  },
];

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-[#050505] text-white lg:grid lg:grid-cols-2">
      {/* Brand / proof panel */}
      <aside className="relative hidden overflow-hidden border-r border-white/[0.06] lg:flex lg:flex-col lg:justify-between p-12 xl:p-16">
        <div className="bg-grid bg-grid-fade absolute inset-0 opacity-60" />
        <div className="hero-glow absolute inset-0" />
        <div className="relative">
          <Link href="/" className="inline-flex items-center gap-2.5">
            <div className="relative h-8 w-8">
              <div className="absolute inset-0 rounded-md border border-accent/40" />
              <div className="absolute inset-[5px] rounded-[3px] bg-accent/15" />
              <div className="absolute inset-[11px] rounded-[2px] bg-accent" />
            </div>
            <span className="font-display text-[18px] tracking-[0.14em] text-white">
              PERCEPT<span className="text-accent">AI</span>
            </span>
          </Link>
        </div>

        <div className="relative max-w-md">
          <motion.h2
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="text-[30px] font-semibold leading-tight tracking-tight text-white"
          >
            The AI workforce that works your{" "}
            <span className="text-accent">real screen</span>.
          </motion.h2>
          <div className="mt-8 space-y-5">
            {PROOF.map((p, i) => (
              <motion.div
                key={p.title}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, delay: 0.1 + i * 0.1 }}
                className="flex gap-3.5"
              >
                <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/[0.08] bg-white/[0.03] text-accent">
                  <p.icon size={16} strokeWidth={1.7} />
                </span>
                <div>
                  <div className="text-[14px] font-medium text-white/90">{p.title}</div>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-white/45">{p.body}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        <div className="relative flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.16em] text-white/35">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          Perception infrastructure for autonomous agents
        </div>
      </aside>

      {/* Form panel */}
      <main className="flex min-h-screen items-center justify-center px-6 py-12 sm:px-10">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="w-full max-w-[400px]"
        >
          {/* Logo (mobile only — desktop shows it in the aside) */}
          <Link href="/" className="mb-10 inline-flex items-center gap-2.5 lg:hidden">
            <div className="relative h-8 w-8">
              <div className="absolute inset-0 rounded-md border border-accent/40" />
              <div className="absolute inset-[5px] rounded-[3px] bg-accent/15" />
              <div className="absolute inset-[11px] rounded-[2px] bg-accent" />
            </div>
            <span className="font-display text-[17px] tracking-[0.14em] text-white">
              PERCEPT<span className="text-accent">AI</span>
            </span>
          </Link>

          <h1 className="text-[26px] font-semibold tracking-tight text-white">{title}</h1>
          <p className="mt-1.5 text-[14px] text-white/50">{subtitle}</p>

          <div className="mt-8">{children}</div>

          <div className="mt-6 text-center text-[13px] text-white/45">{footer}</div>
        </motion.div>
      </main>
    </div>
  );
}

/** Shared field + submit styling so both auth forms match exactly. */
export function AuthField({
  label,
  hint,
  ...props
}: { label: string; hint?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <label className="text-[12.5px] font-medium text-white/70">{label}</label>
        {hint}
      </div>
      <input
        {...props}
        className="w-full rounded-lg border border-white/[0.1] bg-white/[0.02] px-3.5 h-11 text-[14px] text-white placeholder:text-white/30 outline-none transition-all focus:border-accent/50 focus:bg-white/[0.03] focus:ring-2 focus:ring-accent/15"
      />
    </div>
  );
}

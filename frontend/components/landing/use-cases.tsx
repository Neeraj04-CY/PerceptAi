"use client";

import { motion } from "framer-motion";
import { Monitor, Workflow, Globe, Package } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { staggerContainer, staggerChild } from "@/components/landing/motion-utils";

interface UseCase {
  category: string;
  title: string;
  body: string;
  pill: string;
  icon: LucideIcon;
}

const CASES: UseCase[] = [
  {
    category: "ENTERPRISE",
    title: "Legacy Software",
    body: "Automate Tally, SAP, and tools built before APIs existed. PerceptAI sees the screen and acts — no integration required.",
    pill: "Desktop Apps",
    icon: Monitor,
  },
  {
    category: "PRODUCTIVITY",
    title: "Cross-App Workflows",
    body: "Copy from one app, open another, paste and format — one instruction handles it all across any combination of applications.",
    pill: "Automation",
    icon: Workflow,
  },
  {
    category: "RESEARCH",
    title: "Web Data Extraction",
    body: "Navigate any website, extract structured data, save to file — without Selenium, Playwright, or browser extensions.",
    pill: "Extraction",
    icon: Globe,
  },
  {
    category: "DEVELOPERS",
    title: "Embeddable SDK",
    body: "pip install perceptai — add desktop perception to your own agent stack. The infrastructure layer your agents are missing.",
    pill: "pip install perceptai",
    icon: Package,
  },
];

export function UseCases() {
  return (
    <section
      id="use-cases"
      className="relative py-32 md:py-40"
      data-testid="use-cases-section"
    >
      <div className="mx-auto max-w-container px-6 lg:px-16">
        <div className="flex flex-col items-center text-center mb-16 md:mb-20">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2 mb-6"
          >
            <span className="h-px w-8 bg-accent/60" />
            <span className="font-mono text-[11px] uppercase tracking-[0.28em] text-accent/90">
              USE CASES
            </span>
            <span className="h-px w-8 bg-accent/60" />
          </motion.div>

          <motion.h2
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className="text-[clamp(2.25rem,5vw,3.25rem)] font-semibold tracking-tight text-white leading-[1.05]"
            data-testid="use-cases-heading"
          >
            Built for real automation.
          </motion.h2>
        </div>

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-80px" }}
          className="grid sm:grid-cols-2 gap-px overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.02]"
        >
          {CASES.map((c) => (
            <motion.div
              key={c.title}
              variants={staggerChild}
              data-testid={`use-case-${c.title.toLowerCase().replace(/\s+/g, "-")}`}
              className="group relative bg-[#050505] p-8 md:p-10 transition-colors duration-500 hover:bg-white/[0.015]"
            >
              {/* Hover top border */}
              <span className="pointer-events-none absolute left-0 top-0 h-[1.5px] w-0 bg-accent transition-all duration-500 ease-out group-hover:w-full" />

              <div className="flex items-start justify-between gap-4">
                <span className="font-mono text-[10px] uppercase tracking-[0.28em] text-white/35">
                  {c.category}
                </span>
                <div className="h-9 w-9 rounded-lg border border-white/[0.08] bg-white/[0.02] flex items-center justify-center text-white/65 transition-all duration-500 group-hover:border-accent/35 group-hover:bg-accent/[0.06] group-hover:text-accent">
                  <c.icon size={15} strokeWidth={1.6} />
                </div>
              </div>

              <h3 className="mt-6 text-[24px] md:text-[26px] font-semibold tracking-tight text-white leading-tight">
                {c.title}
              </h3>

              <p className="mt-4 text-[14.5px] text-white/55 leading-relaxed max-w-md">
                {c.body}
              </p>

              <div className="mt-7">
                <span className="inline-flex items-center rounded-full border border-white/[0.10] bg-white/[0.025] px-3 h-7 font-mono text-[10.5px] uppercase tracking-[0.18em] text-white/65 group-hover:border-accent/30 group-hover:text-accent/90 transition-colors duration-500">
                  {c.pill}
                </span>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

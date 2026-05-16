"use client";

import { Check, Minus } from "lucide-react";
import { motion } from "framer-motion";
import { SectionHeading } from "@/components/landing/section-heading";

type Cell = boolean | string;

const columns = ["PerceptAI", "DIY stack", "Legacy obs"];

const rows: { feature: string; cells: Cell[] }[] = [
  { feature: "Unified perception API (vision + DOM + audio)", cells: [true, false, false] },
  { feature: "Sub-50ms p50 latency at the edge", cells: [true, "Varies", false] },
  { feature: "Replayable agent traces", cells: [true, false, "Partial"] },
  { feature: "Step-level intent grounding", cells: [true, false, false] },
  { feature: "Zero-config SDK · TS / Py / Go", cells: [true, false, "TS only"] },
  { feature: "On-prem & VPC deployment", cells: [true, "DIY", true] },
  { feature: "Built-in eval + regression suite", cells: [true, false, false] },
  { feature: "SOC 2 Type II", cells: [true, false, true] },
];

export function Comparison() {
  return (
    <section
      id="compare"
      className="relative py-28 md:py-40"
      data-testid="comparison-section"
    >
      <div className="mx-auto max-w-container px-6">
        <SectionHeading
          eyebrow="Why PerceptAI"
          title={
            <>
              REPLACE YOUR
              <br />
              <span className="text-accent">DUCT-TAPED STACK.</span>
            </>
          }
          description="Most teams glue together OCR, vision models, browser drivers, and tracing tools. PerceptAI ships it as one cohesive runtime — purpose-built for agents."
        />

        <motion.div
          initial={{ opacity: 0, y: 28 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          className="mt-16 rounded-3xl border border-white/10 bg-white/[0.02] backdrop-blur-xl overflow-hidden"
          data-testid="comparison-table"
        >
          {/* Header */}
          <div className="grid grid-cols-[1.6fr_repeat(3,1fr)] border-b border-white/10">
            <div className="px-5 md:px-8 py-5 md:py-6 font-mono text-[11px] uppercase tracking-[0.24em] text-white/40">
              Capability
            </div>
            {columns.map((c, i) => (
              <div
                key={c}
                className={`px-3 md:px-6 py-5 md:py-6 text-sm font-medium border-l border-white/5 ${
                  i === 0
                    ? "text-accent font-display tracking-[0.08em] text-base md:text-lg"
                    : "text-white/60 font-display tracking-[0.08em] text-base md:text-lg"
                }`}
              >
                {c}
              </div>
            ))}
          </div>

          {/* Rows */}
          {rows.map((r, idx) => (
            <div
              key={r.feature}
              data-testid={`compare-row-${idx}`}
              className="grid grid-cols-[1.6fr_repeat(3,1fr)] border-b border-white/5 last:border-0 hover:bg-white/[0.015] transition-colors duration-300"
            >
              <div className="px-5 md:px-8 py-5 md:py-6 text-sm md:text-[15px] text-white/80">
                {r.feature}
              </div>
              {r.cells.map((cell, ci) => (
                <div
                  key={ci}
                  className={`px-3 md:px-6 py-5 md:py-6 border-l border-white/5 text-sm flex items-center ${
                    ci === 0 ? "bg-accent/[0.025]" : ""
                  }`}
                >
                  <CellRender value={cell} highlight={ci === 0} />
                </div>
              ))}
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

function CellRender({ value, highlight }: { value: Cell; highlight: boolean }) {
  if (value === true) {
    return (
      <div
        className={`flex items-center gap-2 ${
          highlight ? "text-accent" : "text-white/70"
        }`}
      >
        <span
          className={`flex h-5 w-5 items-center justify-center rounded-full ${
            highlight ? "bg-accent/15" : "bg-white/[0.04]"
          }`}
        >
          <Check size={12} strokeWidth={2.5} />
        </span>
      </div>
    );
  }
  if (value === false) {
    return (
      <div className="flex items-center gap-2 text-white/25">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/[0.03]">
          <Minus size={12} strokeWidth={2} />
        </span>
      </div>
    );
  }
  return (
    <span className="font-mono text-[11px] uppercase tracking-wider text-white/50">
      {value}
    </span>
  );
}

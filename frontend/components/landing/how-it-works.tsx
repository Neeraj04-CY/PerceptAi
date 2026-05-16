"use client";

import { motion } from "framer-motion";
import { Eye, GitBranch, Activity } from "lucide-react";
import { staggerContainer, staggerChild } from "@/components/landing/motion-utils";
import { SectionHeading } from "@/components/landing/section-heading";

const steps = [
  {
    n: "01",
    icon: Eye,
    title: "Perceive",
    desc: "Stream pixels, DOM, voice, or sensor data. PerceptAI normalises everything into a unified spatiotemporal frame graph.",
    code: `percept.ingest({\n  source: "browser:tab-3",\n  modality: ["pixels","dom"],\n})`,
  },
  {
    n: "02",
    icon: GitBranch,
    title: "Reason",
    desc: "Your agents query a structured perception layer instead of raw bytes — every step is grounded, explainable, and replayable.",
    code: `const intent = await percept\n  .query("checkout button")\n  .where({ visible: true })`,
  },
  {
    n: "03",
    icon: Activity,
    title: "Observe",
    desc: "Every decision is captured as a trace. Replay any agent run, diff perceptions, and ship fixes before users hit them.",
    code: `percept.trace.replay({\n  runId: "run_8f2a…",\n  step: 14,\n})`,
  },
];

export function HowItWorks() {
  return (
    <section
      id="how"
      className="relative py-28 md:py-40"
      data-testid="how-it-works-section"
    >
      <div className="mx-auto max-w-container px-6">
        <SectionHeading
          eyebrow="How it works"
          title={
            <>
              ONE RUNTIME.
              <br />
              <span className="text-white/40">THREE PRIMITIVES.</span>
            </>
          }
          description="Drop PerceptAI in front of any agent — vision, browser, OS, or robotics — and get production-grade perception, reasoning, and observability in a single API."
        />

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-80px" }}
          className="mt-20 grid md:grid-cols-3 gap-px overflow-hidden rounded-3xl border border-white/10 bg-white/[0.02]"
        >
          {steps.map((s) => (
            <motion.div
              key={s.n}
              variants={staggerChild}
              data-testid={`how-step-${s.n}`}
              className="group relative bg-background/40 p-8 md:p-10 transition-colors duration-500 hover:bg-white/[0.02]"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-white/30">
                  STEP / {s.n}
                </span>
                <div className="rounded-md border border-white/10 bg-white/[0.04] p-2 text-accent transition-all duration-300 group-hover:border-accent/40 group-hover:bg-accent/10">
                  <s.icon size={16} strokeWidth={1.6} />
                </div>
              </div>

              <h3 className="mt-8 font-display tracking-wide text-4xl md:text-5xl text-white">
                {s.title}
              </h3>

              <p className="mt-4 text-sm md:text-[15px] text-white/55 leading-relaxed max-w-sm">
                {s.desc}
              </p>

              <pre className="mt-8 rounded-lg border border-white/5 bg-black/40 p-4 font-mono text-[11.5px] leading-relaxed text-white/65 overflow-x-auto">
                <code>{s.code}</code>
              </pre>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

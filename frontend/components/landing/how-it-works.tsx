"use client";

import { motion } from "framer-motion";
import { staggerContainer, staggerChild } from "@/components/landing/motion-utils";

const steps = [
  {
    n: "01",
    eyebrow: "PERCEIVE",
    title: "See Any Screen",
    desc: "EasyOCR maps every element with real pixel coordinates. Vision AI understands the full UI context. Works on any app — no DOM, no APIs required.",
    code: `screen = perceive()
# 47 elements detected
# coordinates mapped`,
  },
  {
    n: "02",
    eyebrow: "PLAN",
    title: "Plan The Steps",
    desc: "Groq LLaMA 3.3 converts your plain English instruction into precise executable steps with full OS and window awareness.",
    code: `plan = agent.plan(instruction)
# 8 steps generated
# confidence: 0.97`,
  },
  {
    n: "03",
    eyebrow: "EXECUTE",
    title: "Act & Self-Heal",
    desc: "Actions execute on the real screen with precision. When steps fail, the self-healing loop re-perceives and recovers autonomously.",
    code: `result = agent.run()
# completed: 8/8 steps
# duration: 4.9s`,
  },
];

export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="relative py-32 md:py-40"
      data-testid="how-it-works-section"
    >
      <div className="mx-auto max-w-container px-6 lg:px-16">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="inline-flex items-center gap-2 mb-16"
        >
          <span className="h-px w-8 bg-accent/60" />
          <span className="font-mono text-[11px] uppercase tracking-[0.28em] text-accent/90">
            HOW IT WORKS
          </span>
        </motion.div>

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-80px" }}
          className="grid md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-white/[0.06] border border-white/[0.06] rounded-2xl overflow-hidden"
        >
          {steps.map((s) => (
            <motion.div
              key={s.n}
              variants={staggerChild}
              data-testid={`how-step-${s.n}`}
              className="group relative p-10 md:p-12 transition-colors duration-500 hover:bg-white/[0.015]"
            >
              {/* Sliding accent top border on hover */}
              <span className="pointer-events-none absolute left-0 top-0 h-[1.5px] w-0 bg-accent transition-all duration-500 ease-out group-hover:w-full" />

              <div className="font-mono text-[11px] tracking-[0.28em] text-accent/85">
                {s.n}
              </div>

              <h3 className="mt-6 text-[22px] font-semibold tracking-tight text-white leading-tight">
                {s.title}
              </h3>

              <p className="mt-4 text-[14.5px] text-white/55 leading-relaxed">
                {s.desc}
              </p>

              <pre className="mt-8 rounded-lg border border-white/[0.06] bg-black/50 backdrop-blur-xl p-4 font-mono text-[12px] leading-relaxed text-white/65 overflow-x-auto">
                <code>{s.code}</code>
              </pre>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Github } from "lucide-react";

export function CtaBlock() {
  return (
    <section
      className="relative py-24 md:py-32"
      data-testid="cta-block-section"
    >
      {/* Soft accent glow backdrop */}
      <div
        aria-hidden
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[60%] h-[260px] bg-accent/[0.07] blur-[120px] rounded-full pointer-events-none"
      />

      <div className="relative mx-auto max-w-container px-6 lg:px-16 text-center">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="inline-flex items-center gap-2 mb-7"
        >
          <span className="h-px w-8 bg-accent/60" />
          <span className="font-mono text-[11px] uppercase tracking-[0.28em] text-accent/90">
            GET STARTED
          </span>
          <span className="h-px w-8 bg-accent/60" />
        </motion.div>

        <motion.h2
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="font-display tracking-tight leading-[0.95] text-[clamp(2.75rem,7vw,4.5rem)] text-white"
          data-testid="cta-heading"
        >
          The perception layer
          <br />
          <span className="text-accent">agents need.</span>
        </motion.h2>

        <motion.p
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
          className="mt-7 text-base md:text-[17px] text-white/55"
        >
          Free forever. Open source. No credit card.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-3"
        >
          <Link
            href="/signup"
            data-testid="cta-start-building"
            className="group inline-flex items-center gap-2 rounded-full bg-accent text-black h-12 px-7 text-[14.5px] font-medium tracking-tight transition-all duration-300 hover:bg-accent/90 hover:shadow-[0_0_50px_-6px_rgba(0,255,133,0.55)]"
          >
            Start Building
            <ArrowRight
              size={15}
              strokeWidth={2.4}
              className="transition-transform group-hover:translate-x-0.5"
            />
          </Link>

          <a
            href="https://github.com/Neeraj04-CY/PerceptAi"
            target="_blank"
            rel="noreferrer"
            data-testid="cta-github"
            className="group inline-flex items-center gap-2 rounded-full border border-white/[0.10] bg-white/[0.02] text-white/85 hover:text-white hover:bg-white/[0.05] hover:border-white/20 h-12 px-7 text-[14.5px] font-medium tracking-tight transition-all duration-300"
          >
            <Github size={15} strokeWidth={1.8} />
            View on GitHub
          </a>
        </motion.div>
      </div>
    </section>
  );
}

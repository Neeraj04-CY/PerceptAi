"use client";

import { motion } from "framer-motion";
import { ArrowRight, Sparkles } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { TerminalCard } from "@/components/landing/terminal-card";

const metrics = [
  { label: "Latency p50", value: "38ms", testid: "metric-latency" },
  { label: "Frames / sec", value: "120", testid: "metric-fps" },
  { label: "Agents running", value: "14.2K", testid: "metric-agents" },
  { label: "Uptime", value: "99.99%", testid: "metric-uptime" },
];

export function Hero() {
  return (
    <section
      className="relative min-h-screen flex flex-col justify-center overflow-hidden pt-32 pb-20"
      data-testid="hero-section"
    >
      {/* Grid + glow background */}
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-grid bg-grid-fade opacity-70" />
        <div className="absolute inset-0 hero-glow animate-glow-pulse" />
        <div className="absolute inset-0 noise" />
      </div>

      <div className="mx-auto w-full max-w-container px-6">
        <div className="grid lg:grid-cols-[1.05fr_1fr] gap-14 items-center">
          {/* Left: copy */}
          <div className="text-left">
            <motion.div
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.05, ease: [0.22, 1, 0.36, 1] }}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] backdrop-blur-xl px-3 py-1.5 mb-8"
              data-testid="hero-badge"
            >
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-60 animate-ping" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-accent" />
              </span>
              <span className="text-[11px] font-mono uppercase tracking-[0.18em] text-white/70">
                v1.0 · perception runtime
              </span>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 22 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.85, delay: 0.18, ease: [0.22, 1, 0.36, 1] }}
              className="font-display tracking-[0.005em] leading-[0.92] text-[clamp(3rem,8vw,7.5rem)] text-white"
              data-testid="hero-headline"
            >
              SEE WHAT
              <br />
              YOUR AGENTS
              <br />
              <span className="text-accent">ACTUALLY SEE.</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.75, delay: 0.34, ease: [0.22, 1, 0.36, 1] }}
              className="mt-8 max-w-xl text-base md:text-lg text-white/60 leading-relaxed"
              data-testid="hero-subheadline"
            >
              PerceptAI is the perception layer for autonomous agents.
              Real-time multimodal understanding, end-to-end execution traces,
              and observability — packaged as one production-grade API.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.5, ease: [0.22, 1, 0.36, 1] }}
              className="mt-10 flex flex-wrap gap-3"
            >
              <Button
                variant="primary"
                size="lg"
                data-testid="hero-cta-primary"
                className="group gap-2"
                asChild
              >
                <Link href="/signup">
                  Start building
                  <ArrowRight
                    size={16}
                    className="transition-transform duration-300 group-hover:translate-x-1"
                  />
                </Link>
              </Button>
              <Button
                variant="secondary"
                size="lg"
                data-testid="hero-cta-secondary"
                className="gap-2"
                asChild
              >
                <Link href="/dashboard">
                  <Sparkles size={16} className="text-accent" />
                  See live demo
                </Link>
              </Button>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.7, ease: [0.22, 1, 0.36, 1] }}
              className="mt-14 grid grid-cols-2 md:grid-cols-4 gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/[0.02]"
              data-testid="hero-metrics"
            >
              {metrics.map((m) => (
                <div
                  key={m.label}
                  data-testid={m.testid}
                  className="bg-background/40 px-5 py-5 md:py-6"
                >
                  <div className="font-display text-3xl md:text-4xl text-white tracking-wide">
                    {m.value}
                  </div>
                  <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-white/40">
                    {m.label}
                  </div>
                </div>
              ))}
            </motion.div>
          </div>

          {/* Right: terminal card */}
          <motion.div
            initial={{ opacity: 0, y: 40, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 1, delay: 0.4, ease: [0.22, 1, 0.36, 1] }}
            className="relative"
          >
            <div className="absolute -inset-10 -z-10 hero-glow opacity-60 blur-2xl" />
            <TerminalCard />
          </motion.div>
        </div>
      </div>
    </section>
  );
}

"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ChevronLeft } from "lucide-react";
import { AnimatedTerminal } from "@/components/auth/animated-terminal";
import { SigninForm } from "@/components/auth/signin-form";

export default function SigninPage() {
  return (
    <div className="relative min-h-screen lg:h-screen lg:overflow-hidden bg-[#050505] text-white grid grid-cols-1 lg:grid-cols-[55%_45%]">
      {/* LEFT PANEL */}
      <motion.section
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="relative bg-[#0A0A0A] lg:border-r border-white/[0.06] flex flex-col"
        data-testid="signin-left"
      >
        {/* Background grain + soft accent glow */}
        <div
          aria-hidden
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(60% 40% at 30% 20%, rgba(0,255,133,0.06), transparent 70%)",
          }}
        />

        {/* Top */}
        <div className="relative px-8 lg:px-12 pt-10 lg:pt-12">
          <div className="flex items-center gap-2.5">
            <div className="relative h-8 w-8 shrink-0">
              <div className="absolute inset-0 rounded-md border border-accent/40" />
              <div className="absolute inset-[5px] rounded-[3px] bg-accent/15" />
              <div className="absolute inset-[10px] rounded-[2px] bg-accent" />
            </div>
            <span className="font-sans font-bold tracking-[0.18em] text-[15px] text-white">
              PERCEPTAI
            </span>
            <span className="rounded-sm border border-accent/30 bg-accent/10 px-1.5 py-[2px] font-mono text-[9px] uppercase tracking-[0.18em] text-accent">
              Beta
            </span>
          </div>

          <div className="mt-12 lg:mt-20 max-w-xl">
            <h1 className="font-sans font-bold tracking-tight leading-[1.05] text-[36px] sm:text-[42px]">
              <span className="text-white">The perception layer</span>
              <br />
              <span className="text-white/35">for autonomous agents.</span>
            </h1>
            <p className="mt-4 text-[15px] sm:text-[16px] text-white/55 leading-relaxed">
              Give AI eyes and hands on any screen.
            </p>
          </div>
        </div>

        {/* Middle: terminal */}
        <div className="relative flex-1 flex items-center justify-center px-6 lg:px-12 py-10 lg:py-0">
          <AnimatedTerminal />
        </div>

        {/* Bottom: trust indicators */}
        <div className="relative px-8 lg:px-12 pb-8 lg:pb-12">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[11px] text-white/40">
            <span className="flex items-center gap-1.5">
              <span className="text-white/30">$</span>
              <code className="text-white/70">pip install perceptai</code>
            </span>
            <span className="text-white/15">|</span>
            <span>
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent align-middle mr-1.5 animate-pulse" />
              Live on PyPI
            </span>
            <span className="text-white/15">|</span>
            <span>v0.1.1</span>
          </div>
        </div>
      </motion.section>

      {/* RIGHT PANEL */}
      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.45, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
        className="relative flex flex-col justify-center px-8 sm:px-12 lg:px-16 py-12 lg:py-0"
        data-testid="signin-right"
      >
        <Link
          href="/"
          data-testid="back-to-home"
          className="absolute top-6 left-6 lg:top-8 lg:left-8 inline-flex items-center gap-1 text-[12.5px] text-white/45 hover:text-white transition-colors"
        >
          <ChevronLeft size={14} />
          Back to home
        </Link>

        <div className="w-full max-w-[380px] mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.25 }}
            className="font-mono text-[10px] uppercase tracking-[0.28em] text-accent/65"
          >
            Runtime access
          </motion.div>

          <motion.h2
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.3 }}
            className="mt-2 text-[28px] font-sans font-bold tracking-tight text-white"
          >
            Welcome back
          </motion.h2>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4, delay: 0.35 }}
            className="mt-2 mb-8 text-[14px] text-white/50"
          >
            Sign in to your PerceptAI workspace
          </motion.p>

          <SigninForm />
        </div>
      </motion.section>
    </div>
  );
}

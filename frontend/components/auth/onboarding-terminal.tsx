"use client";

import { motion } from "framer-motion";

interface Line {
  text: string;
  tone?: "prompt" | "info" | "ok" | "muted";
}

const LINES: Line[] = [
  { text: "$ percept signup --email='you@company.com'", tone: "prompt" },
  { text: "→ creating workspace...", tone: "info" },
  { text: "→ provisioning runtime keys", tone: "info" },
  { text: "→ 1M perception calls allocated", tone: "info" },
  { text: "✓ workspace ready [0.4s]", tone: "ok" },
  { text: "✓ api key generated [0.2s]", tone: "ok" },
  { text: "✓ welcome to perceptai · 0.6s", tone: "ok" },
];

const toneClass: Record<NonNullable<Line["tone"]>, string> = {
  prompt: "text-white/85",
  info: "text-white/55",
  ok: "text-accent",
  muted: "text-white/40",
};

export function OnboardingTerminal() {
  return (
    <div
      className="relative w-full max-w-[480px] rounded-xl border border-white/[0.08] bg-[#0D0D0D] shadow-[0_24px_80px_-32px_rgba(0,0,0,0.8)] overflow-hidden"
      data-testid="signup-terminal"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-px rounded-xl opacity-60"
        style={{
          background:
            "radial-gradient(50% 50% at 50% 0%, rgba(0,255,133,0.10), transparent 70%)",
        }}
      />

      <div className="relative flex items-center justify-between px-4 h-10 border-b border-white/[0.06] bg-black/30">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[#FF5F56]/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#E8C44A]/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-accent/80" />
        </div>
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
          percept · onboarding
        </div>
        <div className="flex items-center gap-1.5 font-mono text-[10px] text-accent">
          <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
          provisioning
        </div>
      </div>

      <div className="relative px-5 py-5 font-mono text-[12px] leading-[2]">
        {LINES.map((line, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{
              duration: 0.35,
              delay: 0.4 + i * 0.3,
              ease: [0.22, 1, 0.36, 1],
            }}
            className={toneClass[line.tone || "info"]}
          >
            {line.text}
          </motion.div>
        ))}

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3, delay: 0.4 + LINES.length * 0.3 }}
          className="mt-1 flex items-center gap-2"
        >
          <span className="text-white/30">{">"}</span>
          <span className="inline-block h-3.5 w-1.5 bg-accent animate-pulse" />
        </motion.div>
      </div>

      <div className="relative grid grid-cols-3 gap-3 border-t border-white/[0.06] bg-black/20 px-5 py-3 font-mono text-[10px] uppercase tracking-[0.16em]">
        <Stat label="quota" value="1M / mo" />
        <Stat label="region" value="us-west-2" />
        <Stat label="plan" value="free" />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-white/30">{label}</span>
      <span className="text-white/75">{value}</span>
    </div>
  );
}

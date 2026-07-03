"use client";

import { motion } from "framer-motion";

const items = [
  "OPENAI",
  "ANTHROPIC",
  "LANGCHAIN",
  "VERCEL",
  "BROWSER USE",
  "PINECONE",
  "MODAL",
  "REPLICATE",
  "SUPABASE",
  "RAMP",
  "STRIPE",
  "LINEAR",
];

export function Ticker() {
  return (
    <section
      className="relative border-y border-white/5 bg-black/40 py-10"
      data-testid="ticker-section"
    >
      <div className="mx-auto max-w-container px-6">
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-8 font-mono text-[10px] uppercase tracking-[0.3em] text-white/35"
        >
          Trusted by teams shipping agents at scale
        </motion.div>

        <div
          className="relative overflow-hidden no-scrollbar"
          style={{
            maskImage:
              "linear-gradient(to right, transparent, #000 12%, #000 88%, transparent)",
            WebkitMaskImage:
              "linear-gradient(to right, transparent, #000 12%, #000 88%, transparent)",
          }}
        >
          <div className="flex w-max gap-16 animate-ticker">
            {[...items, ...items].map((label, i) => (
              <div
                key={i}
                className="font-display tracking-[0.18em] text-2xl md:text-3xl text-white/40 hover:text-white transition-colors duration-300 whitespace-nowrap"
                data-testid={`ticker-item-${i}`}
              >
                {label}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

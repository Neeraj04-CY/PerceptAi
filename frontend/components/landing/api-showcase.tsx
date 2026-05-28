"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { KeyRound, Zap, BarChart3, ArrowUpRight } from "lucide-react";

type Tab = "python" | "curl" | "javascript";

const CODE: Record<Tab, string> = {
  python: `import requests

response = requests.post(
  "https://perceptai-production.up.railway.app/api/v1/execute",
  headers={"X-API-Key": "pk_..."},
  json={"instruction": "open chrome and go to github.com"}
)

print(response.json()["status"])   # "completed"
print(response.json()["steps"])    # [...8 steps...]`,
  curl: `curl -X POST \\
  "https://perceptai-production.up.railway.app/api/v1/execute" \\
  -H "X-API-Key: pk_..." \\
  -H "Content-Type: application/json" \\
  -d '{"instruction": "open notepad and write hello"}'`,
  javascript: `const res = await fetch(
  "https://perceptai-production.up.railway.app/api/v1/execute",
  {
    method: "POST",
    headers: { "X-API-Key": "pk_..." },
    body: JSON.stringify({
      instruction: "open chrome"
    })
  }
)
const data = await res.json()`,
};

const TABS: { id: Tab; label: string }[] = [
  { id: "python", label: "Python" },
  { id: "curl", label: "cURL" },
  { id: "javascript", label: "JavaScript" },
];

const FEATURES = [
  {
    icon: KeyRound,
    title: "API Key Auth",
    desc: "Secure scoped keys",
  },
  {
    icon: Zap,
    title: "Live on Railway",
    desc: "Production endpoint ready",
  },
  {
    icon: BarChart3,
    title: "Session Tracking",
    desc: "Full execution history",
  },
];

export function ApiShowcase() {
  const [tab, setTab] = useState<Tab>("python");

  return (
    <section
      id="api"
      className="relative py-32 md:py-40 bg-[#0D0D0D] border-y border-white/[0.06]"
      data-testid="api-showcase-section"
    >
      <div className="mx-auto max-w-container px-6 lg:px-16">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
          {/* LEFT */}
          <div>
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center gap-2 mb-6"
            >
              <span className="h-px w-8 bg-accent/60" />
              <span className="font-mono text-[11px] uppercase tracking-[0.28em] text-accent/90">
                REST API
              </span>
            </motion.div>

            <motion.h2
              initial={{ opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
              className="text-[clamp(2rem,4.5vw,2.75rem)] font-semibold tracking-tight text-white leading-[1.05]"
              data-testid="api-heading"
            >
              Integrate in minutes.
            </motion.h2>

            <motion.p
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.7, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
              className="mt-5 text-[15px] md:text-base text-white/55 leading-relaxed max-w-md"
            >
              Send a plain English instruction. Get back structured execution
              results. Works with any language, any framework.
            </motion.p>

            <motion.div
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="mt-10 space-y-5"
            >
              {FEATURES.map((f) => (
                <div
                  key={f.title}
                  className="flex items-start gap-4"
                  data-testid={`api-feature-${f.title.toLowerCase().replace(/\s+/g, "-")}`}
                >
                  <div className="mt-0.5 h-9 w-9 shrink-0 rounded-lg border border-white/[0.08] bg-white/[0.02] flex items-center justify-center text-accent">
                    <f.icon size={14} strokeWidth={1.6} />
                  </div>
                  <div className="min-w-0">
                    <div className="text-[14px] text-white font-medium">
                      {f.title}
                    </div>
                    <div className="mt-0.5 text-[13px] text-white/45">
                      {f.desc}
                    </div>
                  </div>
                </div>
              ))}
            </motion.div>

            <motion.a
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.6, delay: 0.35 }}
              href="https://perceptai-production.up.railway.app/docs"
              target="_blank"
              rel="noreferrer"
              data-testid="api-docs-link"
              className="mt-10 inline-flex items-center gap-1.5 text-[14px] text-accent hover:text-accent/85 transition-colors group"
            >
              View API Docs
              <ArrowUpRight
                size={14}
                className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
              />
            </motion.a>
          </div>

          {/* RIGHT - Code panel */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            className="relative"
          >
            {/* Subtle accent glow */}
            <div
              aria-hidden
              className="absolute -inset-x-10 -inset-y-6 bg-accent/[0.04] blur-3xl rounded-full pointer-events-none"
            />

            <div
              className="relative rounded-xl backdrop-blur-xl bg-black/60 border border-white/[0.08] overflow-hidden"
              data-testid="api-code-panel"
            >
              {/* Window chrome + tabs */}
              <div className="flex items-center justify-between border-b border-white/[0.06] px-4 h-11">
                <div className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-white/[0.08]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-white/[0.08]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-white/[0.08]" />
                </div>
                <div
                  className="flex items-center gap-0.5 rounded-md border border-white/[0.06] bg-white/[0.02] p-0.5"
                  role="tablist"
                >
                  {TABS.map((t) => {
                    const active = tab === t.id;
                    return (
                      <button
                        key={t.id}
                        role="tab"
                        aria-selected={active}
                        onClick={() => setTab(t.id)}
                        data-testid={`api-tab-${t.id}`}
                        className="relative font-mono text-[10.5px] uppercase tracking-[0.18em] h-6 px-2.5 rounded-[5px] transition-colors"
                      >
                        {active && (
                          <motion.span
                            layoutId="api-tab-pill"
                            className="absolute inset-0 rounded-[5px] bg-white/[0.06] border border-white/[0.08]"
                            transition={{ type: "spring", stiffness: 380, damping: 30 }}
                          />
                        )}
                        <span
                          className={`relative ${
                            active ? "text-white" : "text-white/45 hover:text-white/75"
                          }`}
                        >
                          {t.label}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Code body */}
              <div className="relative min-h-[320px]">
                <AnimatePresence mode="wait">
                  <motion.pre
                    key={tab}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                    className="p-5 md:p-6 font-mono text-[13px] leading-[1.7] text-white/80 overflow-x-auto"
                    data-testid={`api-code-${tab}`}
                  >
                    <code>{CODE[tab]}</code>
                  </motion.pre>
                </AnimatePresence>
              </div>

              {/* Footer endpoint chip */}
              <div className="flex items-center justify-between border-t border-white/[0.06] px-4 h-9 bg-black/30">
                <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-white/35">
                  POST /api/v1/execute
                </span>
                <span className="inline-flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.18em] text-accent">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-60 animate-ping" />
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-accent" />
                  </span>
                  Live
                </span>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

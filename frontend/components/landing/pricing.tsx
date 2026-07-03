"use client";

import { motion } from "framer-motion";
import { Check } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/landing/section-heading";
import { staggerContainer, staggerChild } from "@/components/landing/motion-utils";

const plans = [
  {
    name: "Hobby",
    price: "$0",
    cadence: "/ forever",
    description: "For solo builders prototyping agents on weekends.",
    cta: "Start free",
    href: "/signup",
    variant: "secondary" as const,
    features: [
      "10K perception calls / mo",
      "1 concurrent agent",
      "Community Discord",
      "Replay last 24h of traces",
    ],
  },
  {
    name: "Pro",
    price: "$49",
    cadence: "/ month",
    description: "For teams shipping agents into production traffic.",
    cta: "Start 14-day trial",
    href: "/signup",
    variant: "primary" as const,
    highlight: true,
    features: [
      "1M perception calls / mo",
      "Unlimited agents",
      "Trace replay · 30 days",
      "SOC 2 + audit logs",
      "Priority email & Slack support",
    ],
  },
  {
    name: "Enterprise",
    price: "Custom",
    cadence: "annual",
    description: "VPC, on-prem, and dedicated regions with white-glove SLAs.",
    cta: "Contact sales",
    href: "mailto:neerajpatil0402@gmail.com",
    variant: "outline" as const,
    features: [
      "Unlimited everything",
      "On-prem / VPC deploy",
      "99.99% uptime SLA",
      "Dedicated infra engineer",
      "Custom eval suites",
    ],
  },
];

export function Pricing() {
  return (
    <section
      id="pricing"
      className="relative py-28 md:py-40"
      data-testid="pricing-section"
    >
      <div className="mx-auto max-w-container px-6">
        <SectionHeading
          eyebrow="Pricing"
          title={
            <>
              PRICED FOR
              <br />
              <span className="text-white/40">EVERY STAGE.</span>
            </>
          }
          description="Start free. Scale linearly. No surprise inference bills — perception calls are the only meter that matters."
        />

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-80px" }}
          className="mt-16 grid md:grid-cols-3 gap-5"
        >
          {plans.map((p) => (
            <motion.div
              key={p.name}
              variants={staggerChild}
              data-testid={`pricing-card-${p.name.toLowerCase()}`}
              className={`relative rounded-3xl p-7 md:p-9 transition-all duration-500 backdrop-blur-xl ${
                p.highlight
                  ? "border border-accent/40 bg-accent/[0.04] shadow-[0_30px_120px_-40px_rgba(0,255,133,0.4)]"
                  : "border border-white/10 bg-white/[0.03] hover:border-white/20"
              }`}
            >
              {p.highlight && (
                <div className="absolute -top-3 left-7">
                  <span className="rounded-full bg-accent text-black px-3 py-1 font-mono text-[10px] uppercase tracking-[0.18em]">
                    Most popular
                  </span>
                </div>
              )}

              <div className="font-mono text-[11px] uppercase tracking-[0.24em] text-white/50">
                {p.name}
              </div>

              <div className="mt-5 flex items-baseline gap-2">
                <span className="font-display text-6xl md:text-7xl tracking-tight text-white">
                  {p.price}
                </span>
                <span className="text-sm text-white/40">{p.cadence}</span>
              </div>

              <p className="mt-4 text-sm text-white/55 leading-relaxed min-h-[42px]">
                {p.description}
              </p>

              <Button
                variant={p.variant}
                size="md"
                data-testid={`pricing-cta-${p.name.toLowerCase()}`}
                className="mt-7 w-full"
                asChild
              >
                {p.href.startsWith("/") ? (
                  <Link href={p.href}>{p.cta}</Link>
                ) : (
                  <a href={p.href}>{p.cta}</a>
                )}
              </Button>

              <div className="mt-8 h-px bg-white/5" />

              <ul className="mt-7 space-y-3.5">
                {p.features.map((f) => (
                  <li
                    key={f}
                    className="flex items-start gap-3 text-sm text-white/70"
                  >
                    <span
                      className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                        p.highlight ? "bg-accent/15 text-accent" : "bg-white/[0.05] text-white/60"
                      }`}
                    >
                      <Check size={12} strokeWidth={2.5} />
                    </span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

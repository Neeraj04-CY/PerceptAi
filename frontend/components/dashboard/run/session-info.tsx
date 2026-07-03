"use client";

import { motion } from "framer-motion";
import { Copy, Check } from "lucide-react";
import { useState } from "react";
import { StatusPill, type Status } from "@/components/dashboard/status-pill";

export interface SessionMeta {
  id: string;
  status: Status;
  duration: string;
  stepsTotal: number;
  stepsCompleted: number;
  apiKey: string;
  plan: string;
  startedAt: string;
  region: string;
}

export function SessionInfo({ meta }: { meta: SessionMeta }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard?.writeText(meta.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  const rows: { label: string; value: React.ReactNode; mono?: boolean }[] = [
    { label: "Status", value: <StatusPill status={meta.status} /> },
    { label: "Duration", value: meta.duration, mono: true },
    {
      label: "Steps",
      value: (
        <span className="font-mono text-[12px] text-white/80">
          {meta.stepsCompleted}
          <span className="text-white/30"> / {meta.stepsTotal}</span>
        </span>
      ),
    },
    { label: "API key", value: meta.apiKey, mono: true },
    { label: "Plan", value: <span className="text-[12px] text-white/80">{meta.plan}</span> },
    { label: "Region", value: meta.region, mono: true },
    { label: "Started", value: meta.startedAt, mono: true },
  ];

  return (
    <div
      className="flex flex-col rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl h-full min-h-[280px]"
      data-testid="session-info"
    >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 h-10 shrink-0">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
          session
        </span>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 font-mono text-[10px] text-white/50 hover:text-white transition-colors"
          data-testid="session-id-copy"
        >
          <span>{meta.id}</span>
          {copied ? (
            <Check size={11} className="text-accent" />
          ) : (
            <Copy size={11} />
          )}
        </button>
      </div>

      <div className="p-4 flex-1 overflow-y-auto">
        <dl className="space-y-3">
          {rows.map((r, i) => (
            <motion.div
              key={r.label}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: i * 0.04 }}
              className="flex items-center justify-between gap-3"
            >
              <dt className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/35">
                {r.label}
              </dt>
              <dd
                className={
                  r.mono
                    ? "font-mono text-[12px] text-white/80 text-right truncate"
                    : "text-right"
                }
              >
                {r.value}
              </dd>
            </motion.div>
          ))}
        </dl>
      </div>
    </div>
  );
}

"use client";

import { motion } from "framer-motion";
import { Eye, AlertTriangle } from "lucide-react";
import type { ApiPerceptionStats } from "@/lib/api";

/**
 * How the agent SAW during this session: which perception sources ran,
 * their health and latency, and how confident the final world model was.
 * Uncertainty is shown, never hidden.
 */
export function PerceptionCard({ stats }: { stats: ApiPerceptionStats }) {
  const providers = Object.entries(stats.providers ?? {});
  if (providers.length === 0 && !stats.snapshots) return null;
  const confidence = stats.final_confidence;

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.05, ease: [0.22, 1, 0.36, 1] }}
      data-testid="perception-card"
      className="rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl overflow-hidden"
    >
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
        <div className="flex items-center gap-2 text-white/70">
          <Eye size={14} />
          <span className="text-[11px] font-medium uppercase tracking-[0.14em]">Perception</span>
        </div>
        <span className="font-mono text-[11px] text-white/45 tabular-nums">
          {stats.snapshots} snapshot{stats.snapshots === 1 ? "" : "s"}
        </span>
      </div>

      <div className="p-5 grid grid-cols-1 md:grid-cols-[1.4fr_1fr] gap-5">
        <div>
          <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-white/35">
            sources
          </span>
          <ul className="mt-2.5 space-y-2">
            {providers.map(([name, p]) => (
              <li key={name} className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 min-w-0">
                  {p.failures === 0 ? (
                    <span className="h-1.5 w-1.5 rounded-full bg-accent/80 shrink-0" aria-hidden />
                  ) : (
                    <AlertTriangle size={10} className="text-[#FF7A6B] shrink-0" />
                  )}
                  <span className="font-mono text-[11.5px] text-white/75">{name}</span>
                  {p.failures > 0 && (
                    <span className="font-mono text-[9px] uppercase tracking-wider text-[#FF7A6B]">
                      {p.failures} failure{p.failures === 1 ? "" : "s"}
                    </span>
                  )}
                </span>
                <span className="font-mono text-[10.5px] text-white/40 tabular-nums shrink-0">
                  {p.calls} call{p.calls === 1 ? "" : "s"} · {p.observations} obs ·{" "}
                  {Math.round(p.avg_latency_ms)}ms avg
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-3 md:border-l md:border-white/[0.06] md:pl-5">
          {typeof confidence === "number" && (
            <div>
              <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-white/35">
                final world confidence
              </span>
              <div className="mt-1.5 flex items-center gap-2.5">
                <span className="h-[4px] flex-1 rounded-full bg-white/[0.08] overflow-hidden">
                  <span
                    className="block h-full rounded-full bg-accent/80"
                    style={{ width: `${Math.round(Math.max(0, Math.min(1, confidence)) * 100)}%` }}
                  />
                </span>
                <span className="font-mono text-[13px] text-white/85 tabular-nums">
                  {Math.round(confidence * 100)}%
                </span>
              </div>
            </div>
          )}
          <dl className="grid grid-cols-2 gap-3">
            {typeof stats.final_elements === "number" && (
              <div>
                <dt className="font-mono text-[9px] uppercase tracking-[0.16em] text-white/30">
                  elements seen
                </dt>
                <dd className="font-mono text-[15px] text-white/85 tabular-nums">
                  {stats.final_elements}
                </dd>
              </div>
            )}
            {typeof stats.final_windows === "number" && (
              <div>
                <dt className="font-mono text-[9px] uppercase tracking-[0.16em] text-white/30">
                  windows
                </dt>
                <dd className="font-mono text-[15px] text-white/85 tabular-nums">
                  {stats.final_windows}
                </dd>
              </div>
            )}
          </dl>
        </div>
      </div>
    </motion.section>
  );
}

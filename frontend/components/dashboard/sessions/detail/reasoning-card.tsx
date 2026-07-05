"use client";

/** Reasoning replay: how the run *thought*. Confidence evolution as a
 * line chart plus the decision trajectory, straight from the replayable
 * record in TaskResult.metadata.reasoning.
 *
 * Series palette = reference dark categorical slots 1–3, validated
 * (lightness band, chroma, CVD ΔE 15.7+, ≥3:1 on this surface). */

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { BrainCircuit } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ApiReasoningSummary } from "@/lib/api";

const SERIES = [
  { key: "world_confidence", label: "world confidence", color: "#3987e5" },
  { key: "progress", label: "progress", color: "#199e70" },
  { key: "uncertainty", label: "uncertainty", color: "#c98500" },
] as const;

const W = 560;
const H = 150;
const PAD = { top: 10, right: 96, bottom: 20, left: 34 };

export function ReasoningCard({ reasoning }: { reasoning: ApiReasoningSummary }) {
  const history = useMemo(() => reasoning.confidence_history || [],
                          [reasoning.confidence_history]);
  const trajectory = reasoning.trajectory || [];
  const [hover, setHover] = useState<number | null>(null); // index into history

  const geometry = useMemo(() => {
    if (history.length < 2) return null;
    const cycles = history.map((h) => h.cycle);
    const xMin = Math.min(...cycles);
    const xMax = Math.max(...cycles);
    const x = (cycle: number) =>
      PAD.left + ((cycle - xMin) / Math.max(1, xMax - xMin)) * (W - PAD.left - PAD.right);
    const y = (v: number) => PAD.top + (1 - clamp01(v)) * (H - PAD.top - PAD.bottom);
    return { x, y, xMin, xMax };
  }, [history]);

  if (!geometry && trajectory.length === 0) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="glass rounded-xl p-5"
      data-testid="reasoning-card"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-3">
        <h3 className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
          <BrainCircuit size={13} /> Reasoning replay
        </h3>
        <span className="font-mono text-[10px] text-white/30">
          strategy: {reasoning.strategy || "—"} · {reasoning.cycles} cycles ·{" "}
          {reasoning.decision_changes} decision change(s) · hypotheses{" "}
          {reasoning.hypotheses?.confirmed ?? 0}✓/{reasoning.hypotheses?.rejected ?? 0}✗
        </span>
      </div>

      {geometry && (
        <div className="overflow-x-auto">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full min-w-[420px]"
            role="img"
            aria-label="Confidence, progress and uncertainty by reasoning cycle"
            onMouseMove={(e) => {
              const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
              const px = ((e.clientX - rect.left) / rect.width) * W;
              let best = 0;
              let bestDist = Infinity;
              history.forEach((h, i) => {
                const d = Math.abs(geometry.x(h.cycle) - px);
                if (d < bestDist) { bestDist = d; best = i; }
              });
              setHover(best);
            }}
            onMouseLeave={() => setHover(null)}
          >
            {/* recessive grid: 0 / 50 / 100% */}
            {[0, 0.5, 1].map((v) => (
              <g key={v}>
                <line x1={PAD.left} x2={W - PAD.right} y1={geometry.y(v)} y2={geometry.y(v)}
                      stroke="rgba(255,255,255,0.07)" strokeWidth="1" />
                <text x={PAD.left - 6} y={geometry.y(v) + 3} textAnchor="end"
                      fontSize="8" fill="rgba(255,255,255,0.35)" fontFamily="monospace">
                  {Math.round(v * 100)}%
                </text>
              </g>
            ))}
            {/* x labels: first & last cycle */}
            <text x={PAD.left} y={H - 6} fontSize="8" fill="rgba(255,255,255,0.35)"
                  fontFamily="monospace">cycle {geometry.xMin}</text>
            <text x={W - PAD.right} y={H - 6} textAnchor="end" fontSize="8"
                  fill="rgba(255,255,255,0.35)" fontFamily="monospace">{geometry.xMax}</text>

            {/* series lines + direct end labels */}
            {SERIES.map((series) => {
              const points = history
                .map((h) => `${geometry.x(h.cycle)},${geometry.y(Number(h[series.key] ?? 0))}`)
                .join(" ");
              const last = history[history.length - 1];
              return (
                <g key={series.key}>
                  <polyline points={points} fill="none" stroke={series.color}
                            strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
                  <text x={W - PAD.right + 6}
                        y={geometry.y(Number(last[series.key] ?? 0)) + 3}
                        fontSize="8.5" fill={series.color} fontFamily="monospace">
                    {series.label}
                  </text>
                </g>
              );
            })}

            {/* hover crosshair + markers */}
            {hover !== null && history[hover] && (
              <g>
                <line x1={geometry.x(history[hover].cycle)} x2={geometry.x(history[hover].cycle)}
                      y1={PAD.top} y2={H - PAD.bottom}
                      stroke="rgba(255,255,255,0.25)" strokeWidth="1" strokeDasharray="3 3" />
                {SERIES.map((series) => (
                  <circle key={series.key}
                          cx={geometry.x(history[hover].cycle)}
                          cy={geometry.y(Number(history[hover][series.key] ?? 0))}
                          r="3.5" fill={series.color}
                          stroke="#0A0A0A" strokeWidth="2" />
                ))}
              </g>
            )}
          </svg>

          {/* tooltip / readout row (also the always-available text alternative) */}
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] text-white/45"
               aria-live="polite">
            <span className="text-white/30">
              {hover !== null && history[hover]
                ? `cycle ${history[hover].cycle}`
                : `final (cycle ${history[history.length - 1].cycle})`}
            </span>
            {SERIES.map((series) => {
              const row = hover !== null && history[hover] ? history[hover] : history[history.length - 1];
              return (
                <span key={series.key} className="flex items-center gap-1.5">
                  <span className="h-[2px] w-3 rounded-full" style={{ background: series.color }} />
                  {series.label} {Math.round(clamp01(Number(row[series.key] ?? 0)) * 100)}%
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* decision trajectory */}
      {trajectory.length > 0 && (
        <div className="mt-4">
          <div className="mb-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-white/30">
            Decision trajectory
          </div>
          <div className="max-h-48 space-y-1 overflow-y-auto pr-1">
            {trajectory.map((step, i) => (
              <div key={i} className="flex gap-2 text-[11px]">
                <span className="w-7 shrink-0 pt-[1px] font-mono text-[9px] text-white/25 tabular-nums">
                  #{step.cycle}
                </span>
                <span className={cn("w-24 shrink-0 font-mono text-[10px] uppercase tracking-wider",
                                    decisionColor(step.decision))}>
                  {step.decision}
                </span>
                <span className="min-w-0 flex-1 truncate text-white/50" title={step.reason}>
                  {step.reason}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(reasoning.uncertainty_signals?.length ?? 0) > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {reasoning.uncertainty_signals.slice(0, 6).map((signal, i) => (
            <span key={i}
                  title={signal.detail}
                  className="rounded-full border border-white/10 px-2 py-[2px] font-mono text-[9px] uppercase tracking-wider text-white/40">
              {signal.kind} · {(signal.severity * 100).toFixed(0)}%
            </span>
          ))}
        </div>
      )}
    </motion.section>
  );
}

function decisionColor(decision: string): string {
  switch (decision) {
    case "finish": return "text-accent";
    case "abort":
    case "need_user": return "text-red-400";
    case "recover":
    case "replan": return "text-amber-300";
    default: return "text-white/45";
  }
}

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, Number.isFinite(v) ? v : 0));
}

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Eye, AlertTriangle } from "lucide-react";

/** One `world` SSE event — a fused perception snapshot. */
export interface WorldSnapshot {
  mode: "fast" | "full";
  focused_window: string;
  windows: number;
  elements: number;
  interactive: number;
  confidence: number; // 0..1
  providers: {
    name: string;
    source: string;
    ok: boolean;
    observations: number;
    latency_ms: number;
  }[];
  top_elements: {
    name: string;
    role: string;
    confidence: number;
    sources: string[];
  }[];
  changed: boolean;
  summary: string;
  timestamp: string;
  receivedAt: number;
}

/**
 * Live World Model viewer: what the agent currently sees, which sources
 * saw it, how confident perception is, and how the world evolved over
 * the run. Confidence is a magnitude — one hue, fill encodes value;
 * provider failures use icon + label, never color alone.
 */
export function WorldModelPanel({ snapshots }: { snapshots: WorldSnapshot[] }) {
  if (snapshots.length === 0) return null;
  const latest = snapshots[snapshots.length - 1];

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl"
      data-testid="world-model"
    >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 h-10">
        <div className="flex items-center gap-2">
          <Eye size={12} className="text-white/40" />
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
            world model
          </span>
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] rounded px-1.5 py-0.5 border border-white/[0.08] text-white/45">
            {latest.mode}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] text-white/35 truncate max-w-[280px]">
            {latest.focused_window || "no focused window"}
          </span>
          <ConfidenceMeter value={latest.confidence} width={72} label="perception confidence" />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.3fr_1fr] gap-0 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.06]">
        {/* Sources */}
        <section className="p-4">
          <SectionLabel>sources</SectionLabel>
          <ul className="mt-3 space-y-2.5">
            {latest.providers.map((p) => (
              <li key={p.name} className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 min-w-0">
                  {p.ok ? (
                    <span className="h-1.5 w-1.5 rounded-full bg-accent/80 shrink-0" aria-hidden />
                  ) : (
                    <AlertTriangle size={10} className="text-[#FF7A6B] shrink-0" />
                  )}
                  <span className="font-mono text-[11px] text-white/75 truncate">{p.name}</span>
                  {!p.ok && (
                    <span className="font-mono text-[9px] uppercase tracking-wider text-[#FF7A6B]">
                      failed
                    </span>
                  )}
                </span>
                <span className="font-mono text-[10px] text-white/40 shrink-0 tabular-nums">
                  {p.observations} obs · {formatMs(p.latency_ms)}
                </span>
              </li>
            ))}
            {latest.providers.length === 0 && (
              <li className="font-mono text-[10px] text-white/30">no providers reported</li>
            )}
          </ul>

          <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-white/[0.06] pt-3">
            <Stat label="windows" value={latest.windows} />
            <Stat label="elements" value={latest.elements} />
            <Stat label="interactive" value={latest.interactive} />
          </dl>
        </section>

        {/* Element inspector */}
        <section className="p-4 min-w-0">
          <SectionLabel>elements</SectionLabel>
          <ul className="mt-3 space-y-2 max-h-[190px] overflow-y-auto pr-1">
            <AnimatePresence initial={false}>
              {latest.top_elements.map((el, i) => (
                <motion.li
                  key={`${el.name}-${el.role}-${i}`}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.25, delay: i * 0.02 }}
                  className="flex items-center gap-2.5"
                >
                  <ConfidenceMeter
                    value={el.confidence}
                    width={40}
                    label={`${el.name} confidence ${pct(el.confidence)}`}
                  />
                  <span className="font-mono text-[11px] text-white/80 truncate min-w-0">
                    {el.name}
                  </span>
                  <span className="font-mono text-[9px] uppercase tracking-wider text-white/35 shrink-0">
                    {el.role}
                  </span>
                  <span className="ml-auto flex gap-1 shrink-0">
                    {el.sources.map((s) => (
                      <span
                        key={s}
                        className="font-mono text-[8px] uppercase tracking-wider rounded-sm border border-white/[0.1] px-1 py-px text-white/45"
                      >
                        {s}
                      </span>
                    ))}
                  </span>
                </motion.li>
              ))}
            </AnimatePresence>
            {latest.top_elements.length === 0 && (
              <li className="font-mono text-[10px] text-white/30">
                no named elements in this snapshot
              </li>
            )}
          </ul>
        </section>

        {/* Perception timeline */}
        <section className="p-4">
          <SectionLabel>perception timeline</SectionLabel>
          <div
            className="mt-3 flex items-end gap-[3px] h-[64px]"
            role="img"
            aria-label={`${snapshots.length} perception snapshots; latest confidence ${pct(latest.confidence)}`}
          >
            {snapshots.slice(-32).map((s, i) => (
              <div
                key={`${s.timestamp}-${i}`}
                className="relative flex-1 max-w-[14px] group"
                title={`${new Date(s.receivedAt).toLocaleTimeString()} · ${s.mode} · ${
                  s.elements
                } elements · confidence ${pct(s.confidence)}${s.summary ? ` · ${s.summary}` : ""}`}
              >
                {/* changed-marker: shape, not color-alone */}
                {s.changed && (
                  <span className="absolute -top-2 left-1/2 -translate-x-1/2 h-[3px] w-[3px] rounded-full bg-white/60" />
                )}
                <div
                  className="w-full rounded-t-[2px] bg-accent/70 group-hover:bg-accent transition-colors"
                  style={{ height: `${Math.max(6, s.confidence * 64)}px` }}
                />
              </div>
            ))}
          </div>
          <div className="mt-2 flex items-center justify-between font-mono text-[9px] text-white/30">
            <span>{snapshots.length} snapshots</span>
            <span className="flex items-center gap-1">
              <span className="h-[3px] w-[3px] rounded-full bg-white/60" /> world changed
            </span>
          </div>
          {latest.summary && (
            <p className="mt-2 font-mono text-[10px] leading-relaxed text-white/45 border-t border-white/[0.06] pt-2">
              {latest.summary}
            </p>
          )}
        </section>
      </div>
    </motion.div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-white/35">
      {children}
    </span>
  );
}

/** Magnitude meter: one hue, fill width encodes value; number in ink. */
function ConfidenceMeter({
  value,
  width,
  label,
}: {
  value: number;
  width: number;
  label: string;
}) {
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <span className="flex items-center gap-1.5 shrink-0" role="img" aria-label={label}>
      <span
        className="h-[3px] rounded-full bg-white/[0.08] overflow-hidden"
        style={{ width }}
      >
        <span
          className="block h-full rounded-full bg-accent/80"
          style={{ width: `${clamped * 100}%` }}
        />
      </span>
      <span className="font-mono text-[10px] text-white/55 tabular-nums w-[30px] text-right">
        {pct(clamped)}
      </span>
    </span>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt className="font-mono text-[9px] uppercase tracking-[0.16em] text-white/30">{label}</dt>
      <dd className="font-mono text-[15px] text-white/85 tabular-nums">{value}</dd>
    </div>
  );
}

function pct(v: number) {
  return `${Math.round(v * 100)}%`;
}

function formatMs(ms: number) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

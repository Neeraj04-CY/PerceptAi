"use client";

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { Search, Filter, ArrowUpRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { StatusPill, type Status } from "@/components/dashboard/status-pill";
import { sessions, type SessionRow } from "./mock";
import { cn } from "@/lib/utils";

const filters: Array<{ label: string; value: Status | "all" }> = [
  { label: "All", value: "all" },
  { label: "Completed", value: "completed" },
  { label: "Running", value: "running" },
  { label: "Failed", value: "failed" },
  { label: "Queued", value: "queued" },
];

export function SessionsTable() {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Status | "all">("all");

  const filtered = useMemo(() => {
    return sessions.filter((s) => {
      if (filter !== "all" && s.status !== filter) return false;
      if (q.trim() && !s.instruction.toLowerCase().includes(q.toLowerCase()) && !s.id.includes(q.toLowerCase())) {
        return false;
      }
      return true;
    });
  }, [q, filter]);

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center gap-3 justify-between">
        <div className="relative flex-1 max-w-md">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/35" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by instruction or run ID…"
            data-testid="sessions-search"
            className="pl-9 h-10"
          />
        </div>
        <div className="flex items-center gap-2 overflow-x-auto no-scrollbar">
          <Filter size={13} className="text-white/35 shrink-0" />
          {filters.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              data-testid={`sessions-filter-${f.value}`}
              className={cn(
                "rounded-full px-3 h-8 text-[11px] font-mono uppercase tracking-wider border transition-colors whitespace-nowrap",
                filter === f.value
                  ? "border-accent/40 bg-accent/10 text-accent"
                  : "border-white/[0.08] bg-white/[0.02] text-white/55 hover:text-white hover:border-white/20"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px overflow-hidden rounded-xl border border-white/[0.08] bg-white/[0.02]">
        {[
          { label: "Total runs", value: sessions.length.toString() },
          { label: "Avg duration", value: "12.4s" },
          { label: "Success rate", value: "94.2%" },
          { label: "Active now", value: sessions.filter((s) => s.status === "running").length.toString() },
        ].map((s) => (
          <div key={s.label} className="bg-[#080808] px-4 py-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">{s.label}</div>
            <div className="mt-1 text-[18px] text-white font-semibold tracking-tight">{s.value}</div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div
        className="rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl overflow-hidden"
        data-testid="sessions-table"
      >
        <div className="grid grid-cols-[1.7fr_120px_100px_80px_140px_110px_110px] gap-3 px-5 py-3 border-b border-white/[0.06] font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">
          <div>Instruction</div>
          <div>Status</div>
          <div>Duration</div>
          <div>Steps</div>
          <div>API Key</div>
          <div>Region</div>
          <div className="text-right">Started</div>
        </div>

        <div>
          {filtered.length === 0 && (
            <div className="px-5 py-12 text-center text-[13px] text-white/40">
              No sessions match your filters.
            </div>
          )}
          {filtered.map((s, i) => (
            <Row key={s.id} session={s} index={i} />
          ))}
        </div>
      </div>
    </div>
  );
}

function Row({ session, index }: { session: SessionRow; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.03, 0.3) }}
      className="group grid grid-cols-[1.7fr_120px_100px_80px_140px_110px_110px] gap-3 px-5 py-3.5 border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] transition-colors"
      data-testid={`session-row-${session.id}`}
    >
      <div className="min-w-0 flex items-center gap-2">
        <div className="flex flex-col min-w-0">
          <span className="text-[13.5px] text-white truncate">{session.instruction}</span>
          <span className="font-mono text-[10px] text-white/35 mt-0.5">{session.id}</span>
        </div>
        <ArrowUpRight
          size={13}
          className="opacity-0 group-hover:opacity-100 text-white/40 shrink-0 transition-opacity"
        />
      </div>
      <div className="flex items-center"><StatusPill status={session.status} /></div>
      <div className="flex items-center font-mono text-[12px] text-white/80">{session.duration}</div>
      <div className="flex items-center font-mono text-[12px] text-white/65">{session.steps}</div>
      <div className="flex items-center font-mono text-[12px] text-white/65 truncate">{session.apiKey}</div>
      <div className="flex items-center font-mono text-[11px] text-white/55">{session.region}</div>
      <div className="flex items-center justify-end font-mono text-[11px] text-white/45">{session.startedAgo}</div>
    </motion.div>
  );
}

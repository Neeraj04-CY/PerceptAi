"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, Network } from "lucide-react";
import { cn } from "@/lib/utils";
import { ApiMission, getMissions } from "@/lib/api";

const FILTERS = ["all", "running", "completed", "partial", "failed"] as const;

export default function MissionsPage() {
  const router = useRouter();
  const [missions, setMissions] = useState<ApiMission[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");

  useEffect(() => {
    const controller = new AbortController();
    getMissions(100, controller.signal)
      .then(setMissions)
      .catch((e) => {
        if (String(e).includes("Unauthorized")) router.replace("/signin");
        else setError(e instanceof Error ? e.message : "Failed to load missions");
      });
    return () => controller.abort();
  }, [router]);

  const visible = (missions ?? []).filter((m) => filter === "all" || m.status === filter);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[17px] font-medium text-white">Missions</h1>
          <p className="text-[12px] text-white/40 mt-0.5">
            Every workforce run: orders, evidence, decisions and the report it produced.
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-white/[0.07] bg-white/[0.02] p-1">
          {FILTERS.map((f) => (
            <button key={f} onClick={() => setFilter(f)}
                    className={cn(
                      "rounded-md px-2.5 h-6 font-mono text-[10px] uppercase tracking-wider transition-colors",
                      filter === f ? "bg-white/[0.07] text-white" : "text-white/40 hover:text-white",
                    )}>
              {f}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
          {error}
        </div>
      )}

      {missions === null && !error && (
        <div className="space-y-2 animate-pulse">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-14 rounded-xl bg-white/[0.04]" />
          ))}
        </div>
      )}

      {missions !== null && visible.length === 0 && (
        <div className="glass rounded-xl py-14 text-center">
          <Network size={22} className="mx-auto text-white/20" />
          <p className="mt-3 text-[13px] text-white/45">
            {filter === "all" ? "No missions yet." : `No ${filter} missions.`}
          </p>
          <Link href="/dashboard/run"
                className="mt-2 inline-flex items-center gap-1 text-[12px] text-accent hover:underline">
            Run your first mission <ArrowRight size={12} />
          </Link>
        </div>
      )}

      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2">
        {visible.map((mission) => (
          <Link key={mission.id} href={`/dashboard/missions/${mission.id}`}
                className="glass flex items-center gap-4 rounded-xl px-4 py-3 hover:border-accent/25 border border-transparent transition-colors group">
            <StatusPill status={mission.status} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] text-white/85 group-hover:text-white">
                {mission.instruction}
              </div>
              <div className="mt-0.5 font-mono text-[10px] text-white/30">
                {mission.metrics
                  ? `${mission.metrics.orders_completed}/${mission.metrics.orders_total} orders · ` +
                    `${mission.metrics.evidence_count} evidence · ` +
                    `${mission.metrics.reassignments} reassignment(s)` +
                    (mission.metrics.conflicts_open ? ` · ${mission.metrics.conflicts_open} conflict(s)` : "")
                  : "—"}
              </div>
            </div>
            <div className="shrink-0 text-right">
              <div className="font-mono text-[11px] text-white/50 tabular-nums">
                {mission.duration_s ? `${Math.round(mission.duration_s)}s` : "—"}
              </div>
              <div className="font-mono text-[10px] text-white/25">
                {new Date(mission.created_at).toLocaleString()}
              </div>
            </div>
          </Link>
        ))}
      </motion.div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const style =
    status === "completed" ? "text-accent border-accent/30 bg-accent/[0.06]" :
    status === "partial" ? "text-amber-300 border-amber-300/30 bg-amber-300/[0.06]" :
    status === "failed" ? "text-red-400 border-red-400/30 bg-red-400/[0.06]" :
    status === "running" ? "text-sky-300 border-sky-300/30 bg-sky-300/[0.06]" :
    "text-white/40 border-white/10 bg-white/[0.02]";
  return (
    <span className={cn("shrink-0 rounded border px-2 py-[2px] font-mono text-[9px] uppercase tracking-[0.14em]", style)}>
      {status}
    </span>
  );
}

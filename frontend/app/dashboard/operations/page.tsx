"use client";

/** Operations — the work record. Every piece of work the workforce has
 * done or is doing, in business language: what it was, whether the
 * outcome is proven, and where the evidence lives. Tasks and missions
 * are one record here — a COO doesn't care which internal path ran. */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Search } from "lucide-react";
import { cn, isAbortError } from "@/lib/utils";
import {
  ApiMission,
  ApiSession,
  getMissions,
  getSessions,
} from "@/lib/api";

type Filter = "all" | "review" | "failed" | "working";

interface Operation {
  id: string;
  kind: "task" | "mission";
  href: string;
  instruction: string;
  status: string;
  created_at: string;
  duration_s: number | null;
}

export default function OperationsPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<ApiSession[] | null>(null);
  const [missions, setMissions] = useState<ApiMission[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled([
      getSessions(controller.signal),
      getMissions(50, controller.signal),
    ]).then(([s, m]) => {
      if (s.status === "fulfilled") setSessions(s.value);
      else if (isAbortError(s.reason)) { /* ignore */ }
      else if (String(s.reason).includes("Unauthorized")) router.replace("/signin");
      else setError(s.reason instanceof Error ? s.reason.message : "Failed to load operations");
      if (m.status === "fulfilled") setMissions(m.value);
    });
    return () => controller.abort();
  }, [router]);

  const operations = useMemo<Operation[]>(() => {
    const fromSessions: Operation[] = (sessions ?? []).map((s) => ({
      id: s.id, kind: "task", href: `/dashboard/sessions/${s.id}`,
      instruction: s.instruction, status: s.status,
      created_at: s.created_at, duration_s: s.execution_time,
    }));
    const fromMissions: Operation[] = missions.map((m) => ({
      id: m.id, kind: "mission", href: `/dashboard/missions/${m.id}`,
      instruction: m.instruction, status: m.status,
      created_at: m.created_at, duration_s: null,
    }));
    return [...fromSessions, ...fromMissions]
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  }, [sessions, missions]);

  const filtered = operations.filter((op) => {
    if (query && !op.instruction.toLowerCase().includes(query.toLowerCase())) return false;
    if (filter === "review") return op.status === "unverified" || op.status === "partial";
    if (filter === "failed") return op.status === "failed";
    if (filter === "working") return op.status === "running";
    return true;
  });

  const counts = {
    review: operations.filter((o) => o.status === "unverified" || o.status === "partial").length,
    failed: operations.filter((o) => o.status === "failed").length,
    working: operations.filter((o) => o.status === "running").length,
  };

  return (
    <div className="mx-auto max-w-3xl">
      <header className="pt-6 pb-8">
        <h1 className="text-[24px] font-semibold tracking-tight text-white">Operations</h1>
        <p className="mt-1 text-[13px] text-white/40">
          Everything your workforce has done — each with its outcome proven, flagged, or explained.
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
          {error}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 pb-5">
        {([
          ["all", "All"],
          ["working", counts.working ? `Working · ${counts.working}` : "Working"],
          ["review", counts.review ? `Needs review · ${counts.review}` : "Needs review"],
          ["failed", counts.failed ? `Failed · ${counts.failed}` : "Failed"],
        ] as Array<[Filter, string]>).map(([key, label]) => (
          <button key={key} onClick={() => setFilter(key)}
                  className={cn("rounded-full px-3.5 h-7 text-[12px] transition-colors",
                    filter === key ? "bg-white/[0.08] text-white" : "text-white/45 hover:text-white")}>
            {label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 rounded-lg border border-white/[0.07] bg-white/[0.02] px-2.5 h-8">
          <Search size={12} className="text-white/30" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find work…"
                 className="w-36 bg-transparent text-[12px] text-white placeholder:text-white/25 focus:outline-none" />
        </div>
      </div>

      {sessions === null && !error ? (
        <ListSkeleton />
      ) : filtered.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-[13px] text-white/35">
            {operations.length === 0 ? "No operations yet." : "Nothing matches."}
          </p>
          {operations.length === 0 && (
            <Link href="/dashboard/templates"
                  className="mt-3 inline-flex items-center gap-1.5 text-[13px] text-accent hover:underline">
              Hire your workforce for its first role <ArrowRight size={12} />
            </Link>
          )}
        </div>
      ) : (
        <div className="divide-y divide-white/[0.04] pb-16">
          {filtered.map((op) => (
            <Link key={`${op.kind}-${op.id}`} href={op.href}
                  className="group flex items-center gap-4 py-3.5 px-3 -mx-3 rounded-lg hover:bg-white/[0.02] transition-colors">
              <OutcomeWord status={op.status} />
              <span className="flex-1 min-w-0 truncate text-[14px] text-white/75 group-hover:text-white">
                {op.instruction}
              </span>
              {op.kind === "mission" && (
                <span className="font-mono text-[9px] uppercase tracking-wider text-white/25 shrink-0">
                  team
                </span>
              )}
              {op.duration_s != null && (
                <span className="font-mono text-[11px] text-white/25 shrink-0">{op.duration_s.toFixed(0)}s</span>
              )}
              <span className="w-16 text-right font-mono text-[11px] text-white/25 shrink-0">
                {timeAgo(op.created_at)}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function OutcomeWord({ status }: { status: string }) {
  const map: Record<string, { word: string; cls: string }> = {
    completed: { word: "Verified", cls: "text-accent" },
    unverified: { word: "Review", cls: "text-amber-300" },
    partial: { word: "Partial", cls: "text-amber-300" },
    failed: { word: "Failed", cls: "text-red-300" },
    running: { word: "Working", cls: "text-sky-300" },
  };
  const m = map[status] ?? { word: status, cls: "text-white/40" };
  return (
    <span className={cn("w-16 shrink-0 font-mono text-[10px] uppercase tracking-[0.12em]", m.cls)}>
      {m.word}
    </span>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-2 animate-pulse">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-11 rounded-lg bg-white/[0.03]" />
      ))}
    </div>
  );
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, (Date.now() - then) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

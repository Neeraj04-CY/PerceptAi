"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Search, ChevronRight, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { getSessions, type ApiSession } from "@/lib/api";
import { SessionStatusPill } from "./session-status-pill";
import { SkeletonRow } from "./skeleton-row";
import { EmptyState } from "./empty-state";
import { ErrorState } from "./error-state";
import { formatRelativeTime, truncate } from "./format";

type Filter = "all" | "completed" | "failed";

const FILTERS: { label: string; value: Filter }[] = [
  { label: "All", value: "all" },
  { label: "Completed", value: "completed" },
  { label: "Failed", value: "failed" },
];

const REFRESH_MS = 30_000;

export function SessionsView() {
  const router = useRouter();
  const [sessions, setSessions] = useState<ApiSession[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const abortRef = useRef<AbortController | null>(null);

  const load = async (mode: "initial" | "refresh" = "initial") => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    if (mode === "initial") setLoading(true);
    else setRefreshing(true);
    setError(null);

    try {
      const data = await getSessions(controller.signal);
      setSessions(data);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setError((err as Error).message || "Unknown error");
    } finally {
      if (mode === "initial") setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    load("initial");
    const id = setInterval(() => load("refresh"), REFRESH_MS);
    return () => {
      clearInterval(id);
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    if (!sessions) return [];
    return sessions.filter((s) => {
      if (filter !== "all" && s.status !== filter) return false;
      if (query.trim()) {
        const q = query.toLowerCase();
        return (
          s.instruction.toLowerCase().includes(q) ||
          s.id.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [sessions, filter, query]);

  const total = sessions?.length ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="space-y-5"
    >
      {/* Header row */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-[22px] sm:text-2xl font-semibold tracking-tight text-white" data-testid="sessions-title">
            Sessions
          </h1>
          <CountBadge value={total} loading={loading} />
          {refreshing && !loading && (
            <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-white/40">
              <Loader2 size={11} className="animate-spin" />
              refreshing
            </span>
          )}
        </div>
        <Link
          href="/dashboard/run"
          data-testid="sessions-new-task"
          className="inline-flex items-center gap-1.5 rounded-full bg-accent text-black h-9 px-4 text-[13px] font-medium hover:shadow-[0_0_40px_-8px_rgba(0,255,133,0.55)] transition-shadow"
        >
          New Task
          <ArrowRight size={13} />
        </Link>
      </div>

      {/* Filter row */}
      <div className="space-y-3">
        <div className="relative">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/35" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search sessions..."
            data-testid="sessions-search"
            className="pl-9 h-10 w-full bg-white/[0.03] border-white/[0.08]"
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {FILTERS.map((f) => {
            const active = filter === f.value;
            return (
              <button
                key={f.value}
                onClick={() => setFilter(f.value)}
                data-testid={`sessions-filter-${f.value}`}
                className={cn(
                  "rounded-full h-8 px-3.5 text-[11.5px] font-medium transition-colors",
                  active
                    ? "bg-accent text-black"
                    : "border border-white/[0.10] bg-white/[0.02] text-white/65 hover:text-white hover:border-white/20"
                )}
              >
                {f.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Body */}
      {error ? (
        <ErrorState message={error} onRetry={() => load("initial")} />
      ) : (
        <div
          className="rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl overflow-hidden"
          data-testid="sessions-table"
        >
          <div className="grid grid-cols-[1.8fr_120px_110px_110px_110px_24px] gap-3 px-5 py-3 border-b border-white/[0.06] font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">
            <div>Instruction</div>
            <div>Status</div>
            <div>Steps</div>
            <div>Duration</div>
            <div>Time</div>
            <div></div>
          </div>

          <div className="relative">
            {loading ? (
              <SkeletonRows />
            ) : filtered.length === 0 ? (
              sessions && sessions.length === 0 ? (
                <EmptyState />
              ) : (
                <NoMatchState />
              )
            ) : (
              <AnimatePresence initial={false}>
                {filtered.map((s, i) => (
                  <Row
                    key={s.id}
                    session={s}
                    index={i}
                    onClick={() => router.push(`/dashboard/sessions/${s.id}`)}
                  />
                ))}
              </AnimatePresence>
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
}

function CountBadge({ value, loading }: { value: number; loading: boolean }) {
  return (
    <span
      className="inline-flex items-center rounded-md border border-white/[0.10] bg-white/[0.03] px-2 h-6 font-mono text-[11px] text-white/55"
      data-testid="sessions-count"
    >
      {loading ? "…" : value}
    </span>
  );
}

function SkeletonRows() {
  return (
    <div>
      {Array.from({ length: 5 }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  );
}

function NoMatchState() {
  return (
    <div
      className="flex flex-col items-center justify-center text-center px-6 py-16"
      data-testid="sessions-no-match"
    >
      <div className="text-[13px] text-white/55">No sessions match your filters</div>
      <div className="mt-1 text-[12px] text-white/35">
        Try a different search term or filter
      </div>
    </div>
  );
}

function Row({
  session,
  index,
  onClick,
}: {
  session: ApiSession;
  index: number;
  onClick: () => void;
}) {
  const stepsCount = Array.isArray(session.steps) ? session.steps.length : 0;
  const duration =
    session.execution_time != null
      ? `${Number(session.execution_time).toFixed(2)}s`
      : "—";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{
        duration: 0.3,
        delay: Math.min(index * 0.04, 0.4),
        ease: [0.22, 1, 0.36, 1],
      }}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      data-testid={`session-row-${session.id}`}
      className="group grid grid-cols-[1.8fr_120px_110px_110px_110px_24px] gap-3 px-5 py-4 border-b border-white/[0.04] last:border-0 items-center cursor-pointer hover:bg-white/[0.02] transition-colors"
    >
      <div className="min-w-0">
        <div className="text-[13.5px] text-white truncate" title={session.instruction}>
          {truncate(session.instruction, 55)}
        </div>
        <div className="mt-1 font-mono text-[10.5px] text-white/35 truncate">
          {session.id}
        </div>
      </div>
      <div>
        <SessionStatusPill status={session.status} />
      </div>
      <div className="font-mono text-[12px] text-white/55">
        {stepsCount} {stepsCount === 1 ? "step" : "steps"}
      </div>
      <div className="font-mono text-[12px] text-white/55">{duration}</div>
      <div className="font-mono text-[11.5px] text-white/45">
        {formatRelativeTime(session.created_at)}
      </div>
      <div className="flex items-center justify-end">
        <ChevronRight
          size={14}
          className="text-white/30 opacity-0 group-hover:opacity-100 transition-opacity"
        />
      </div>
    </motion.div>
  );
}

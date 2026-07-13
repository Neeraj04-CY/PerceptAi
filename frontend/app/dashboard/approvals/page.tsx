"use client";

/** Approvals — reviewing work from a trusted employee. Each request shows
 * what the workforce wants to do and why it paused; deciding can also
 * TEACH: a correction typed here becomes organizational memory that every
 * future run recalls. Denials with a reason teach automatically. */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { cn, isAbortError } from "@/lib/utils";
import { ApiApproval, decideApproval, getApprovals } from "@/lib/api";

const TABS = ["pending", "approved", "denied", "all"] as const;

export default function ApprovalsPage() {
  const router = useRouter();
  const [tab, setTab] = useState<(typeof TABS)[number]>("pending");
  const [approvals, setApprovals] = useState<ApiApproval[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((signal?: AbortSignal) => {
    return getApprovals(tab, signal)
      .then(setApprovals)
      .catch((e) => {
        if (isAbortError(e)) return;
        if (String(e).includes("Unauthorized")) router.replace("/signin");
        else setError(e instanceof Error ? e.message : "Failed to load approvals");
      });
  }, [tab, router]);

  useEffect(() => {
    setApprovals(null);
    setError(null);
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return (
    <div className="mx-auto max-w-3xl">
      <header className="pt-6 pb-8">
        <h1 className="text-[24px] font-semibold tracking-tight text-white">Approvals</h1>
        <p className="mt-1 text-[13px] text-white/40">
          Where your workforce asks for judgment. A decision can also teach —
          corrections become memory every future operation recalls.
        </p>
      </header>

      <div className="flex items-center gap-2 pb-5">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
                  className={cn("rounded-full px-3.5 h-7 text-[12px] capitalize transition-colors",
                    tab === t ? "bg-white/[0.08] text-white" : "text-white/45 hover:text-white")}>
            {t}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-5 rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
          {error}
        </div>
      )}

      {approvals === null && !error ? (
        <div className="space-y-3 animate-pulse">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-24 rounded-2xl bg-white/[0.03]" />
          ))}
        </div>
      ) : (approvals ?? []).length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-[13.5px] text-white/40">
            {tab === "pending"
              ? "Nothing is waiting on your judgment."
              : `No ${tab === "all" ? "" : tab + " "}decisions on record yet.`}
          </p>
          {tab === "pending" && (
            <p className="mt-1.5 text-[12px] text-white/25 max-w-sm mx-auto">
              Requests appear here when a workspace policy asks a human before an
              action runs — nothing happens silently.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-3 pb-16">
          {(approvals ?? []).map((a) => (
            <ApprovalCard key={a.id} approval={a} onDecided={() => load()} />
          ))}
        </div>
      )}
    </div>
  );
}

function ApprovalCard({ approval, onDecided }: {
  approval: ApiApproval; onDecided: () => void;
}) {
  const [lesson, setLesson] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const pending = approval.status === "pending";

  const decide = async (decision: "approved" | "denied") => {
    setBusy(true);
    setFailed(null);
    try {
      await decideApproval(approval.id, decision, "", lesson.trim());
      onDecided();
    } catch (e) {
      setFailed(e instanceof Error ? e.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={cn("rounded-2xl border p-5",
      pending ? "border-amber-300/15 bg-amber-300/[0.02]" : "border-white/[0.06] bg-white/[0.01]")}>
      <div className="flex items-center justify-between gap-3">
        <span className={cn("font-mono text-[10px] uppercase tracking-[0.14em]",
          pending ? "text-amber-300/90"
            : approval.status === "approved" ? "text-accent/80" : "text-red-300/80")}>
          {approval.status} · {approval.capability}
        </span>
        <span className="font-mono text-[10px] text-white/30">{timeAgo(approval.created_at)}</span>
      </div>
      <p className="mt-2 text-[14px] leading-relaxed text-white/80">{approval.objective}</p>
      {approval.reason && (
        <p className="mt-1.5 text-[12.5px] text-white/40">Reason: {approval.reason}</p>
      )}

      {pending && (
        <>
          <input
            value={lesson}
            onChange={(e) => setLesson(e.target.value)}
            placeholder="Teach something with this decision (optional) — it becomes organizational memory"
            className="mt-4 h-10 w-full rounded-lg border border-white/[0.07] bg-white/[0.02] px-3 text-[12.5px] text-white placeholder:text-white/25 focus:outline-none focus:border-accent/30 transition-colors"
          />
          <div className="mt-3 flex items-center gap-2">
            <button onClick={() => decide("approved")} disabled={busy}
                    className="rounded-lg bg-accent/15 px-4 h-8 text-[12.5px] font-medium text-accent hover:bg-accent/25 transition-colors disabled:opacity-50">
              Approve
            </button>
            <button onClick={() => decide("denied")} disabled={busy}
                    className="rounded-lg bg-white/[0.04] px-4 h-8 text-[12.5px] text-white/60 hover:text-red-300 hover:bg-red-400/10 transition-colors disabled:opacity-50">
              Reject
            </button>
            {failed && <span className="text-[12px] text-red-300">{failed}</span>}
          </div>
        </>
      )}
    </section>
  );
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, (Date.now() - then) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

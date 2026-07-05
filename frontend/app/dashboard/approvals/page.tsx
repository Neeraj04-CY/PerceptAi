"use client";

/** Approvals: the human checkpoint. Approving grants the NEXT matching
 * dispatch in that workspace; denying refuses it. Every decision is
 * recorded in the audit trail. */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { ApiApproval, decideApproval, getApprovals } from "@/lib/api";

const TABS = ["pending", "approved", "denied", "consumed", "all"] as const;

export default function ApprovalsPage() {
  const router = useRouter();
  const [tab, setTab] = useState<(typeof TABS)[number]>("pending");
  const [approvals, setApprovals] = useState<ApiApproval[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback((signal?: AbortSignal) => {
    return getApprovals(tab, signal)
      .then(setApprovals)
      .catch((e) => {
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

  const decide = async (id: string, decision: "approved" | "denied") => {
    setBusy(id);
    try {
      await decideApproval(id, decision);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Decision failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[17px] font-medium text-white">Approvals</h1>
          <p className="text-[12px] text-white/40 mt-0.5">
            Capabilities gated by workspace policy wait here. Approving
            authorizes the next matching dispatch — nothing runs silently.
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-white/[0.07] bg-white/[0.02] p-1">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)}
                    className={cn("rounded-md px-2.5 h-6 font-mono text-[10px] uppercase tracking-wider transition-colors",
                                  tab === t ? "bg-white/[0.07] text-white" : "text-white/40 hover:text-white")}>
              {t}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
          {error}
        </div>
      )}

      {approvals === null && !error && (
        <div className="space-y-2 animate-pulse">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-16 rounded-xl bg-white/[0.04]" />
          ))}
        </div>
      )}

      {approvals !== null && approvals.length === 0 && (
        <div className="glass rounded-xl py-14 text-center">
          <ShieldCheck size={22} className="mx-auto text-white/20" />
          <p className="mt-3 text-[13px] text-white/45">
            No {tab === "all" ? "" : tab + " "}approvals.
          </p>
          <p className="mt-1 text-[11px] text-white/30">
            Configure which capabilities need approval per workspace in
            Organization → Workspaces.
          </p>
        </div>
      )}

      <div className="space-y-2">
        {(approvals ?? []).map((approval) => (
          <div key={approval.id} className="glass rounded-xl px-4 py-3 flex flex-wrap items-center gap-3">
            <StatusChip status={approval.status} />
            <span className="font-mono text-[11px] text-white/70">{approval.capability}</span>
            <span className="min-w-0 flex-1 truncate text-[13px] text-white/70" title={approval.objective}>
              {approval.objective || "—"}
            </span>
            <span className="font-mono text-[10px] text-white/25 shrink-0">
              {new Date(approval.created_at).toLocaleString()}
            </span>
            {approval.status === "pending" ? (
              <span className="flex gap-2 shrink-0">
                <button onClick={() => decide(approval.id, "approved")} disabled={busy === approval.id}
                        className="rounded-md bg-accent/15 px-2.5 h-7 font-mono text-[10px] uppercase tracking-wider text-accent hover:bg-accent/25 transition-colors disabled:opacity-50">
                  Approve
                </button>
                <button onClick={() => decide(approval.id, "denied")} disabled={busy === approval.id}
                        className="rounded-md bg-white/[0.04] px-2.5 h-7 font-mono text-[10px] uppercase tracking-wider text-white/50 hover:text-red-300 hover:bg-red-400/10 transition-colors disabled:opacity-50">
                  Deny
                </button>
              </span>
            ) : (
              approval.reason && (
                <span className="font-mono text-[10px] text-white/30 shrink-0" title={approval.reason}>
                  {approval.reason.slice(0, 40)}
                </span>
              )
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusChip({ status }: { status: string }) {
  const style =
    status === "approved" ? "text-accent border-accent/30" :
    status === "consumed" ? "text-sky-300 border-sky-300/30" :
    status === "denied" ? "text-red-400 border-red-400/30" :
    "text-amber-300 border-amber-300/30";
  return (
    <span className={cn("shrink-0 rounded border px-2 py-[2px] font-mono text-[9px] uppercase tracking-[0.14em]", style)}>
      {status}
    </span>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  ChevronLeft,
  Clock,
  CheckCircle2,
  Hash,
  Activity,
  Copy,
  Check,
  AlertTriangle,
  Lightbulb,
} from "lucide-react";
import { getSession, type ApiSession } from "@/lib/api";
import { remediationFor } from "@/lib/remediation";
import { SessionStatusPill } from "@/components/dashboard/sessions/session-status-pill";
import { MetricCard } from "./metric-card";
import { PerceptionCard } from "./perception-card";
import { ReasoningCard } from "./reasoning-card";
import { TrustTimeline } from "./trust-timeline";
import { ProofOfOutcome } from "./proof-of-outcome";
import { ReportCard } from "./report-card";
import { StepTimeline } from "./step-timeline";
import { RuntimeLogs } from "./runtime-logs";
import { CopyToast } from "./copy-toast";
import { DetailSkeleton } from "./skeleton";

export function DetailView({ id }: { id: string }) {
  const [session, setSession] = useState<ApiSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [toast, setToast] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const data = await getSession(id, controller.signal);
      setSession(data);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setError((err as Error).message || "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    return () => {
      abortRef.current?.abort();
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleCopy = async () => {
    if (!session) return;
    try {
      await navigator.clipboard.writeText(session.id);
    } catch {
      // Best effort — still surface the toast
    }
    setCopied(true);
    setToast(true);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => {
      setToast(false);
      setCopied(false);
    }, 2000);
  };

  return (
    <div className="space-y-6">
      {/* Back */}
      <Link
        href="/dashboard/operations"
        data-testid="back-to-sessions"
        className="inline-flex items-center gap-1 text-[12.5px] text-white/50 hover:text-white transition-colors -ml-1"
      >
        <ChevronLeft size={14} />
        Sessions
      </Link>

      {loading ? (
        <DetailSkeleton />
      ) : error || !session ? (
        <ErrorBlock message={error || "Session not found"} onRetry={load} />
      ) : (
        <Loaded session={session} copied={copied} onCopy={handleCopy} />
      )}

      <CopyToast visible={toast} />
    </div>
  );
}

function Loaded({
  session,
  copied,
  onCopy,
}: {
  session: ApiSession;
  copied: boolean;
  onCopy: () => void;
}) {
  const completedSteps = session.steps?.filter((s) => s.status === "completed").length ?? 0;
  const totalSteps = session.steps?.length ?? 0;
  const duration =
    session.execution_time != null ? `${Number(session.execution_time).toFixed(2)}s` : "—";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <h2
          className="text-[20px] md:text-[22px] font-semibold tracking-tight text-white leading-tight max-w-3xl"
          data-testid="detail-instruction"
        >
          {session.instruction}
        </h2>
        <div className="flex flex-col md:items-end gap-1.5 shrink-0">
          <SessionStatusPill status={session.status} />
          <span
            className="font-mono text-[11px] text-white/45"
            data-testid="detail-timestamp"
          >
            {formatTimestamp(session.created_at)}
          </span>
        </div>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard
          index={0}
          testId="metric-status"
          label="Status"
          icon={<Activity size={14} />}
          value={<SessionStatusPill status={session.status} />}
        />
        <MetricCard
          index={1}
          testId="metric-duration"
          label="Duration"
          icon={<Clock size={14} />}
          value={
            <span className="font-mono text-[18px] text-white tabular-nums">{duration}</span>
          }
        />
        <MetricCard
          index={2}
          testId="metric-steps"
          label="Steps"
          icon={<CheckCircle2 size={14} />}
          value={
            <span className="font-mono text-[18px] text-white tabular-nums">
              {completedSteps}
              <span className="text-white/30"> / {totalSteps}</span>
              <span className="ml-2 font-sans text-[11px] uppercase tracking-wider text-white/40">
                completed
              </span>
            </span>
          }
        />
        <MetricCard
          index={3}
          testId="metric-session-id"
          label="Session ID"
          icon={<Hash size={14} />}
          value={
            <code
              className="font-mono text-[13px] text-white truncate block"
              title={session.id}
            >
              {session.id.slice(0, 8)}
              <span className="text-white/30">…</span>
            </code>
          }
          trailing={
            <button
              onClick={onCopy}
              data-testid="copy-session-id"
              aria-label="Copy session ID"
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-white/[0.10] bg-white/[0.04] hover:bg-white/[0.08] text-white/65 transition-colors"
            >
              {copied ? (
                <Check size={12} className="text-accent" strokeWidth={3} />
              ) : (
                <Copy size={12} />
              )}
            </button>
          }
        />
      </div>

      {/* Proof of outcome — the executive answer: did it work, can I trust it,
          was it handled safely, and here's a copyable audit record. Leads
          everything, on every run (verified, unverified, or honestly failed). */}
      {session.status !== "running" && <ProofOfOutcome session={session} />}

      {/* What to do next — surfaced when the run didn't succeed */}
      {(session.status === "failed" || session.status === "unverified") && (
        <RemediationCard failureType={(session.result as { failure_type?: string } | undefined)?.failure_type} />
      )}

      {/* The deliverable detail — beneath the proof */}
      {session.result?.report && <ReportCard report={session.result.report} />}

      {/* How the agent saw */}
      {session.result?.metadata?.perception && (
        <PerceptionCard stats={session.result.metadata.perception} />
      )}

      {/* How the agent thought */}
      {session.result?.metadata?.reasoning && (
        <ReasoningCard reasoning={session.result.metadata.reasoning} />
      )}

      {/* What was governed — risks, approvals, and human interventions */}
      <TrustTimeline sessionId={session.id} />

      {/* Timeline */}
      <StepTimeline steps={session.steps || []} />

      {/* Logs */}
      <RuntimeLogs steps={session.steps || []} />
    </motion.div>
  );
}

function RemediationCard({ failureType }: { failureType?: string }) {
  const r = remediationFor(failureType);
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="rounded-xl border border-amber-400/20 bg-amber-400/[0.05] p-4"
      data-testid="remediation-card"
    >
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-400/10 text-amber-300 shrink-0">
          <Lightbulb size={16} />
        </span>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[14px] font-medium text-white">{r.title}</span>
            {failureType && (
              <span className="font-mono text-[9px] uppercase tracking-[0.12em] rounded px-1.5 py-0.5 border border-white/10 text-white/40">
                {failureType.replace(/_/g, " ")}
              </span>
            )}
          </div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-white/60">{r.hint}</p>
        </div>
      </div>
    </motion.div>
  );
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      className="rounded-xl border border-[#FF3B3B]/30 bg-[#FF3B3B]/[0.04] backdrop-blur-xl p-8 flex flex-col items-center text-center"
      data-testid="detail-error"
    >
      <span className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[#FF3B3B]/15 text-[#FF3B3B]">
        <AlertTriangle size={18} />
      </span>
      <div className="mt-4 text-[15px] text-white font-medium">Couldn&apos;t load session</div>
      <p className="mt-1.5 text-[12.5px] text-white/55 max-w-md leading-relaxed">{message}</p>
      <div className="mt-5 flex items-center gap-2">
        <Link
          href="/dashboard/operations"
          data-testid="error-back"
          className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.10] bg-white/[0.04] hover:bg-white/[0.08] px-3.5 h-9 text-[12.5px] text-white transition-colors"
        >
          <ChevronLeft size={13} />
          Back to sessions
        </Link>
        <button
          onClick={onRetry}
          data-testid="error-retry"
          className="inline-flex items-center gap-1.5 rounded-md bg-accent text-black px-3.5 h-9 text-[12.5px] font-medium hover:shadow-[0_0_30px_-8px_rgba(52,211,153,0.3)] transition-shadow"
        >
          Retry
        </button>
      </div>
    </div>
  );
}

function formatTimestamp(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

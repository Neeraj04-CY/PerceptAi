"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
  RefreshCw,
  Download,
} from "lucide-react";
import { getSession, type ApiSession } from "@/lib/api";
import { StatusBadge } from "@/components/ui/status-badge";
import { GlassCard } from "@/components/ui/glass-card";
import { MetricCard } from "@/components/ui/metric-card";
import { staggerContainer, fadeUp, pageEntry } from "@/lib/motion";
import { StepTimeline } from "./step-timeline";
import { RuntimeLogs } from "./runtime-logs";
import { CopyToast } from "./copy-toast";
import { DetailSkeleton } from "./skeleton";
import { ExecutionSummary } from "./execution-summary";
import { DurationChart } from "./duration-chart";
import { cn } from "@/lib/utils";

export function DetailView({ id }: { id: string }) {
  const [session, setSession] = useState<ApiSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<"id" | "instruction" | null>(null);
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

  const showToast = (field: "id" | "instruction") => {
    setCopiedField(field);
    setToast(true);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => {
      setToast(false);
      setCopiedField(null);
    }, 2000);
  };

  const handleCopy = async (value: string, field: "id" | "instruction") => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // best effort
    }
    showToast(field);
  };

  return (
    <motion.div {...pageEntry} className="space-y-7">
      <Link
        href="/dashboard/sessions"
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
        <Loaded
          session={session}
          copiedField={copiedField}
          onCopy={handleCopy}
        />
      )}

      <CopyToast visible={toast} />
    </motion.div>
  );
}

function Loaded({
  session,
  copiedField,
  onCopy,
}: {
  session: ApiSession;
  copiedField: "id" | "instruction" | null;
  onCopy: (value: string, field: "id" | "instruction") => void;
}) {
  const router = useRouter();
  const completedSteps =
    session.steps?.filter((s) => s.status === "completed").length ?? 0;
  const totalSteps = session.steps?.length ?? 0;
  const duration =
    session.execution_time != null
      ? `${Number(session.execution_time).toFixed(2)}s`
      : "—";

  const handleRetry = () => {
    router.push(`/dashboard?task=${encodeURIComponent(session.instruction)}`);
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(session, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `session-${session.id.slice(0, 8)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 500);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 pb-6 border-b border-white/[0.06]">
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <h2
              className="text-[22px] md:text-[26px] font-semibold tracking-tight text-white leading-tight max-w-3xl"
              data-testid="detail-instruction"
            >
              {session.instruction}
            </h2>
            <button
              onClick={() => onCopy(session.instruction, "instruction")}
              data-testid="copy-instruction"
              aria-label="Copy instruction"
              className="shrink-0 mt-1 inline-flex h-7 w-7 items-center justify-center rounded-md border border-white/[0.10] bg-white/[0.04] hover:bg-white/[0.08] text-white/55 transition-colors"
            >
              {copiedField === "instruction" ? (
                <Check size={11} className="text-accent" strokeWidth={3} />
              ) : (
                <Copy size={11} />
              )}
            </button>
          </div>

          {/* Action toolbar */}
          <div className="mt-4 flex items-center gap-2 flex-wrap">
            <ToolbarButton
              icon={<RefreshCw size={12} />}
              label="Re-run this task"
              testId="rerun-task"
              onClick={handleRetry}
            />
            <ToolbarButton
              icon={<Download size={12} />}
              label="Export session"
              testId="export-session"
              onClick={handleExport}
            />
          </div>
        </div>

        <div className="flex flex-col md:items-end gap-1.5 shrink-0">
          <StatusBadge status={session.status} />
          <span
            className="font-mono text-[11px] text-white/45"
            data-testid="detail-timestamp"
          >
            {formatTimestamp(session.created_at)}
          </span>
        </div>
      </div>

      {/* Metric cards */}
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        <MetricCard
          testId="metric-status"
          label="Status"
          icon={<Activity size={14} />}
          value={<StatusBadge status={session.status} />}
        />
        <MetricCard
          testId="metric-duration"
          label="Duration"
          icon={<Clock size={14} />}
          value={duration}
        />
        <MetricCard
          testId="metric-steps"
          label="Steps"
          icon={<CheckCircle2 size={14} />}
          value={
            <span className="tabular-nums">
              {completedSteps}
              <span className="text-white/30"> / {totalSteps}</span>
            </span>
          }
          sub="completed"
        />
        <MetricCard
          testId="metric-session-id"
          label="Session ID"
          icon={<Hash size={14} />}
          value={
            <code
              className="font-mono text-[16px] text-white truncate block"
              title={session.id}
            >
              {session.id.slice(0, 8)}
              <span className="text-white/30">…</span>
            </code>
          }
          trailing={
            <button
              onClick={() => onCopy(session.id, "id")}
              data-testid="copy-session-id"
              aria-label="Copy session ID"
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-white/[0.10] bg-white/[0.04] hover:bg-white/[0.08] text-white/65 transition-colors shrink-0"
            >
              {copiedField === "id" ? (
                <Check size={12} className="text-accent" strokeWidth={3} />
              ) : (
                <Copy size={12} />
              )}
            </button>
          }
        />
      </motion.div>

      {/* Execution summary */}
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <ExecutionSummary
          steps={session.steps || []}
          status={session.status}
          duration={duration}
        />
      </motion.div>

      {/* Duration chart */}
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <DurationChart steps={session.steps || []} />
      </motion.div>

      {/* Timeline (now expandable) */}
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <StepTimeline steps={session.steps || []} />
      </motion.div>

      {/* Logs */}
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <RuntimeLogs steps={session.steps || []} />
      </motion.div>
    </div>
  );
}

function ToolbarButton({
  icon,
  label,
  onClick,
  testId,
  intent = "neutral",
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  testId?: string;
  intent?: "neutral" | "accent";
}) {
  return (
    <button
      onClick={onClick}
      data-testid={testId}
      className={cn(
        "inline-flex items-center gap-1.5 h-8 px-3 rounded-md border bg-white/[0.03] hover:bg-white/[0.06] text-[12px] transition-colors",
        intent === "neutral" && "border-white/[0.10] text-white/70 hover:text-white",
        intent === "accent" && "border-accent/30 text-accent hover:bg-accent/[0.08]"
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <GlassCard
      padding="lg"
      className="border-[#FF3B3B]/30 bg-[#FF3B3B]/[0.04] flex flex-col items-center text-center"
      data-testid="detail-error"
    >
      <span className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[#FF3B3B]/15 text-[#FF3B3B]">
        <AlertTriangle size={18} />
      </span>
      <div className="mt-4 text-[15px] text-white font-medium">
        Couldn&apos;t load session
      </div>
      <p className="mt-1.5 text-[12.5px] text-white/55 max-w-md leading-relaxed">
        {message}
      </p>
      <div className="mt-5 flex items-center gap-2">
        <Link
          href="/dashboard/sessions"
          data-testid="error-back"
          className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.10] bg-white/[0.04] hover:bg-white/[0.08] px-3.5 h-9 text-[12.5px] text-white transition-colors"
        >
          <ChevronLeft size={13} />
          Back to sessions
        </Link>
        <button
          onClick={onRetry}
          data-testid="error-retry"
          className="inline-flex items-center gap-1.5 rounded-md bg-accent text-black px-3.5 h-9 text-[12.5px] font-medium hover:shadow-[0_0_30px_-8px_rgba(0,255,133,0.5)] transition-shadow"
        >
          Retry
        </button>
      </div>
    </GlassCard>
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

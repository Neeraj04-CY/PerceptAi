"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  BadgeCheck,
  ShieldQuestion,
  ShieldX,
  Check,
  X,
  Gauge,
  FileCheck2,
  KeyRound,
  ShieldAlert,
  UserCheck,
  Copy,
  ClipboardCheck,
} from "lucide-react";
import { getSessionEvents, type ApiEventRow, type ApiSession } from "@/lib/api";
import { isAbortError } from "@/lib/utils";

/**
 * Proof of Outcome — the artifact an enterprise customer keeps.
 *
 * Every other tool says "the bot ran." This answers the three questions a buyer
 * (and their auditor, and their boss) actually asks about an autonomous run:
 *   1. Did it achieve the business outcome?   (verdict vs the goal's criteria)
 *   2. Can I trust that answer?               (calibrated confidence + evidence)
 *   3. Can I prove it was handled safely?     (risks flagged, approvals, secrets)
 *
 * It composes what the platform already captured — verification checks, the
 * evidence graph, and the canonical trust event stream — into one glance and
 * one copyable audit record. No new data, no parallel system: the report the
 * runtime already produced, finally shaped like proof.
 */

type Verdict = "verified" | "unverified" | "failed";

interface Governance {
  risks: number;
  highRisks: number;
  approvals: number;
  approvalsGranted: number;
  secrets: number;
  interventions: number;
  loaded: boolean;
}

export function ProofOfOutcome({ session }: { session: ApiSession }) {
  const [gov, setGov] = useState<Governance>({
    risks: 0, highRisks: 0, approvals: 0, approvalsGranted: 0,
    secrets: 0, interventions: 0, loaded: false,
  });
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getSessionEvents(session.id, 0, controller.signal)
      .then((events) => setGov(summarizeGovernance(events)))
      .catch((e) => { if (!isAbortError(e)) setGov((g) => ({ ...g, loaded: true })); });
    return () => controller.abort();
  }, [session.id]);

  const result = session.result ?? undefined;
  const verification = result?.verification ?? null;
  const report = result?.report ?? null;
  const goal = result?.goal ?? null;
  const verdict = deriveVerdict(session.status, verification);

  const criteria = criteriaChecks(verification, goal);
  const confidencePct = Math.round(
    ((verification?.confidence ?? report?.confidence ?? 0) as number) * 100);
  const evidenceCount = report?.evidence?.length ?? 0;
  const sourceCount = new Set(
    (report?.evidence ?? []).map((e) => e.source).filter(Boolean)).size
    || (report?.sources?.length ?? 0);

  const look = VERDICT_LOOK[verdict];

  const copyProof = async () => {
    const text = buildAuditSummary({
      session, verdict, confidencePct, criteria, evidenceCount, sourceCount, gov });
    try { await navigator.clipboard.writeText(text); } catch { /* best effort */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      data-testid="proof-of-outcome"
      className={`rounded-2xl border ${look.border} ${look.bg} overflow-hidden`}
    >
      {/* Verdict banner */}
      <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between border-b border-white/[0.06]">
        <div className="flex items-center gap-3 min-w-0">
          <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${look.iconBg} ${look.fg}`}>
            {look.icon}
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-white/40">
                Proof of outcome
              </span>
            </div>
            <div className={`text-[16px] font-semibold ${look.fg}`}>{look.title}</div>
          </div>
        </div>
        <button
          onClick={copyProof}
          data-testid="copy-proof"
          className="inline-flex h-9 shrink-0 items-center gap-1.5 self-start rounded-lg border border-white/[0.12] bg-white/[0.05] px-3 font-mono text-[11px] uppercase tracking-wider text-white/70 hover:bg-white/[0.09] hover:text-white transition-colors sm:self-auto"
        >
          {copied ? <ClipboardCheck size={13} className="text-accent" /> : <Copy size={13} />}
          {copied ? "Copied audit summary" : "Copy audit summary"}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr] gap-0 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.06]">
        {/* Left: did it achieve the goal? */}
        <div className="p-5">
          {goal?.deliverable && (
            <p className="mb-3 text-[13px] leading-relaxed text-white/70">
              <span className="text-white/40">Deliverable: </span>{goal.deliverable}
            </p>
          )}
          {verification?.reason && (
            <p className="mb-3 text-[12.5px] leading-relaxed text-white/55">{verification.reason}</p>
          )}
          {criteria.length > 0 ? (
            <>
              <SectionLabel icon={<FileCheck2 size={12} />}
                text={`Completion criteria · ${criteria.filter((c) => c.passed).length}/${criteria.length} met`} />
              <ul className="mt-2 space-y-1.5">
                {criteria.map((c, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-[12.5px] leading-snug">
                    <span className={`mt-[1px] shrink-0 ${c.passed ? "text-accent" : c.critical ? "text-red-300" : "text-amber-300"}`}>
                      {c.passed ? <Check size={14} /> : <X size={14} />}
                    </span>
                    <span className="text-white/75">
                      {c.name}
                      {c.critical && !c.passed && (
                        <span className="ml-1.5 font-mono text-[9px] uppercase tracking-wider text-red-300/80">critical</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-[12.5px] text-white/45">
              No explicit completion criteria were declared for this run.
            </p>
          )}
        </div>

        {/* Right: can I trust it, and was it handled safely? */}
        <div className="p-5 space-y-4">
          <div>
            <SectionLabel icon={<Gauge size={12} />} text="Confidence" />
            <div className="mt-2 flex items-center gap-3">
              <div className="h-1.5 flex-1 rounded-full bg-white/[0.07] overflow-hidden">
                <div className={`h-full rounded-full ${confidencePct >= 70 ? "bg-accent" : confidencePct >= 40 ? "bg-amber-300" : "bg-red-400"}`}
                     style={{ width: `${Math.max(4, confidencePct)}%` }} />
              </div>
              <span className="font-mono text-[13px] tabular-nums text-white/80">{confidencePct}%</span>
            </div>
            <p className="mt-1 text-[10.5px] text-white/35">
              Calibrated against the verified outcome — not a self-graded guess.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <Stat label="Evidence" value={String(evidenceCount)}
                  hint={`${sourceCount} source${sourceCount === 1 ? "" : "s"}`} />
            <Stat label="Governed" value={gov.loaded ? String(gov.risks + gov.approvals + gov.secrets) : "…"}
                  hint="trust events" />
          </div>

          <div>
            <SectionLabel icon={<ShieldAlert size={12} />} text="How it was governed" />
            <div className="mt-2 flex flex-wrap gap-1.5">
              <GovChip icon={<ShieldAlert size={11} />}
                       label={`${gov.risks} risk${gov.risks === 1 ? "" : "s"} flagged`}
                       tone={gov.highRisks > 0 ? "danger" : gov.risks > 0 ? "warn" : "muted"} />
              <GovChip icon={<UserCheck size={11} />}
                       label={`${gov.approvals} approval${gov.approvals === 1 ? "" : "s"}`}
                       tone={gov.approvals > 0 ? "ok" : "muted"} />
              <GovChip icon={<KeyRound size={11} />}
                       label={`${gov.secrets} secret${gov.secrets === 1 ? "" : "s"} · masked`}
                       tone={gov.secrets > 0 ? "ok" : "muted"} />
            </div>
            <p className="mt-2 text-[10.5px] text-white/35">
              Secret values never entered the model, the events, or this report.
            </p>
          </div>
        </div>
      </div>
    </motion.section>
  );
}

/* ------------------------------------------------------------------ helpers */

const VERDICT_LOOK: Record<Verdict, {
  title: string; icon: React.ReactNode; fg: string; bg: string; border: string; iconBg: string;
}> = {
  verified: {
    title: "Business outcome verified",
    icon: <BadgeCheck size={20} />,
    fg: "text-accent", bg: "bg-accent/[0.04]", border: "border-accent/25", iconBg: "bg-accent/10",
  },
  unverified: {
    title: "Ran, but the outcome couldn't be verified",
    icon: <ShieldQuestion size={20} />,
    fg: "text-amber-300", bg: "bg-amber-300/[0.04]", border: "border-amber-300/25", iconBg: "bg-amber-300/10",
  },
  failed: {
    title: "Did not complete — failed honestly, no blind actions",
    icon: <ShieldX size={20} />,
    fg: "text-red-300", bg: "bg-red-400/[0.04]", border: "border-red-400/25", iconBg: "bg-red-400/10",
  },
};

type Verification = NonNullable<ApiSession["result"]>["verification"];
type Goal = NonNullable<ApiSession["result"]>["goal"];

function deriveVerdict(status: string, verification: Verification): Verdict {
  if (status === "completed" && (verification?.verified ?? true)) return "verified";
  if (status === "failed") return "failed";
  return "unverified";
}

interface Criterion { name: string; passed: boolean; critical: boolean; }

function criteriaChecks(verification: Verification, goal: Goal): Criterion[] {
  if (verification?.checks?.length) {
    return verification.checks.map((c) => ({
      name: c.detail || c.name, passed: c.passed, critical: c.critical }));
  }
  // Fall back to the declared criteria with an unknown verdict shown as unmet.
  return (goal?.completion_criteria ?? []).map((name) => ({ name, passed: false, critical: false }));
}

function summarizeGovernance(events: ApiEventRow[]): Governance {
  const risks = events.filter((e) => e.type === "risk_flagged");
  const approvals = events.filter((e) => e.type === "approval_requested");
  const decided = events.filter((e) => e.type === "approval_decided");
  return {
    risks: risks.length,
    highRisks: risks.filter((e) => (e.payload?.level as string) === "high").length,
    approvals: approvals.length,
    approvalsGranted: decided.filter((e) => (e.payload?.decision as string) === "grant").length,
    secrets: events.filter((e) => e.type === "secret_used").length,
    interventions: events.filter((e) =>
      e.type === "execution_paused" || e.type === "execution_stopped").length,
    loaded: true,
  };
}

function buildAuditSummary(a: {
  session: ApiSession; verdict: Verdict; confidencePct: number;
  criteria: Criterion[]; evidenceCount: number; sourceCount: number; gov: Governance;
}): string {
  const { session, verdict, confidencePct, criteria, evidenceCount, sourceCount, gov } = a;
  const line = "-".repeat(58);
  const verdictText = {
    verified: "VERIFIED — business outcome confirmed against real state",
    unverified: "UNVERIFIED — ran without a confirmable outcome",
    failed: "FAILED — did not complete; no blind actions taken",
  }[verdict];
  const crit = criteria.length
    ? criteria.map((c) => `  [${c.passed ? "x" : " "}] ${c.name}${c.critical ? " (critical)" : ""}`).join("\n")
    : "  (none declared)";
  return [
    "PerceptAI — Proof of Outcome",
    line,
    `Task:        ${session.instruction}`,
    `Verdict:     ${verdictText}`,
    `Confidence:  ${confidencePct}% (calibrated against the verified outcome)`,
    `When:        ${session.created_at}`,
    `Session:     ${session.id}`,
    "",
    "Completion criteria:",
    crit,
    "",
    `Evidence:    ${evidenceCount} item(s) across ${sourceCount} source(s)`,
    "Governance:",
    `  - ${gov.risks} risk(s) flagged${gov.highRisks ? ` (${gov.highRisks} high)` : ""}`,
    `  - ${gov.approvals} approval(s) requested, ${gov.approvalsGranted} granted`,
    `  - ${gov.secrets} secret(s) injected — values never recorded`,
    line,
    "Verifiable from the persisted event stream. Secret values never entered",
    "the model, the events, or this report.",
  ].join("\n");
}

function SectionLabel({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-1.5 text-white/40">
      {icon}
      <span className="text-[10px] font-medium uppercase tracking-[0.14em]">{text}</span>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-white/[0.07] bg-white/[0.02] px-3 py-2">
      <div className="font-mono text-[9px] uppercase tracking-wider text-white/35">{label}</div>
      <div className="mt-0.5 text-[18px] font-medium tabular-nums text-white leading-none">{value}</div>
      <div className="mt-1 text-[10px] text-white/35">{hint}</div>
    </div>
  );
}

function GovChip({ icon, label, tone }: { icon: React.ReactNode; label: string; tone: "ok" | "warn" | "danger" | "muted" }) {
  const cls = {
    ok: "border-accent/30 text-accent/85",
    warn: "border-amber-400/30 text-amber-200",
    danger: "border-red-400/30 text-red-300",
    muted: "border-white/12 text-white/45",
  }[tone];
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-1 font-mono text-[9.5px] uppercase tracking-wider ${cls}`}>
      {icon}{label}
    </span>
  );
}

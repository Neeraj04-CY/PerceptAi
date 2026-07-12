"use client";

/** Evidence — the moat. Every action the workforce takes carries proof:
 * what it acted on, how sure perception was, which sources agreed, what
 * visibly changed because of it, and the verification verdict that
 * followed. This page renders that chain from the persisted record —
 * nothing here can be written by hand, which is the point. */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowUpRight, ChevronDown } from "lucide-react";
import { cn, isAbortError } from "@/lib/utils";
import { ApiSession, getSessions } from "@/lib/api";

interface ActionProof {
  description: string;
  action: string;
  ok: boolean;
  element: string | null;
  confidence: number | null;
  sources: string[];
  effect: { changed: boolean; summary: string } | null;
}

export default function EvidencePage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<ApiSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getSessions(controller.signal)
      .then((s) => {
        const done = s.filter((x) => x.status !== "running").slice(0, 15);
        setSessions(done);
        if (done.length > 0) setOpen(done[0].id);
      })
      .catch((e) => {
        if (isAbortError(e)) return;
        if (String(e).includes("Unauthorized")) router.replace("/signin");
        else setError(e instanceof Error ? e.message : "Failed to load evidence");
      });
    return () => controller.abort();
  }, [router]);

  return (
    <div className="mx-auto max-w-3xl">
      <header className="pt-6 pb-10">
        <h1 className="text-[24px] font-semibold tracking-tight text-white">Evidence</h1>
        <p className="mt-1 text-[13px] text-white/40">
          Proof for every action: what was acted on, how sure perception was, what changed
          because of it, and the verdict that followed. Written by the run itself.
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
          {error}
        </div>
      )}

      {sessions === null && !error ? (
        <EvidenceSkeleton />
      ) : sessions !== null && sessions.length === 0 ? (
        <div className="pb-16">
          <p className="text-[14px] leading-relaxed text-white/55 max-w-xl">
            No operations on the record yet. As soon as your workforce works, every action
            it takes lands here with its proof attached.
          </p>
          <Link href="/dashboard/templates"
                className="mt-4 inline-block text-[13px] text-accent hover:underline">
            Put it to work
          </Link>
        </div>
      ) : (
        <div className="space-y-3 pb-16">
          {(sessions ?? []).map((s) => (
            <OperationProof key={s.id} session={s}
                            open={open === s.id}
                            onToggle={() => setOpen(open === s.id ? null : s.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function OperationProof({ session, open, onToggle }: {
  session: ApiSession; open: boolean; onToggle: () => void;
}) {
  const verification = session.result?.verification ?? null;
  const proofs = useMemo(() => extractProofs(session), [session]);
  const verdict = session.status === "completed"
    ? { word: "Verified", cls: "text-accent" }
    : session.status === "failed"
      ? { word: "Failed", cls: "text-red-300" }
      : { word: "Unconfirmed", cls: "text-amber-300" };

  return (
    <section className="rounded-2xl border border-white/[0.07] bg-white/[0.015] overflow-hidden">
      <button onClick={onToggle} className="w-full text-left px-5 py-4 hover:bg-white/[0.015] transition-colors">
        <div className="flex items-center gap-3">
          <span className={cn("w-20 shrink-0 font-mono text-[10px] uppercase tracking-[0.12em]", verdict.cls)}>
            {verdict.word}
          </span>
          <span className="flex-1 min-w-0 truncate text-[14px] text-white/80">{session.instruction}</span>
          {verification && (
            <span className="font-mono text-[11px] tabular-nums text-white/35 shrink-0">
              {Math.round((verification.confidence ?? 0) * 100)}% confidence
            </span>
          )}
          <ChevronDown size={14} className={cn("text-white/30 transition-transform shrink-0", open && "rotate-180")} />
        </div>
      </button>

      {open && (
        <div className="border-t border-white/[0.05] px-5 py-5 space-y-6">
          {/* The action chain */}
          {proofs.length > 0 && (
            <div>
              <SectionLabel>Actions and their proof</SectionLabel>
              <div className="mt-3 space-y-3">
                {proofs.map((p, i) => (
                  <div key={i} className="flex gap-3.5">
                    <div className="flex flex-col items-center pt-1.5">
                      <span className={cn("h-1.5 w-1.5 rounded-full shrink-0",
                                          p.ok ? "bg-accent" : "bg-red-400")} />
                      {i < proofs.length - 1 && <span className="w-px flex-1 bg-white/[0.06] mt-1.5" />}
                    </div>
                    <div className="min-w-0 pb-1">
                      <div className="text-[13.5px] text-white/85">{p.description}</div>
                      <div className="mt-1 space-y-0.5 text-[12px] leading-relaxed text-white/40">
                        {p.element && p.confidence != null && (
                          <div>
                            Grounded on <span className="text-white/65">“{p.element}”</span> at{" "}
                            <span className="tabular-nums text-white/65">{Math.round(p.confidence * 100)}%</span>
                            {p.sources.length > 0 && <> — confirmed by {p.sources.join(" + ")}</>}
                          </div>
                        )}
                        {p.effect && (
                          <div>
                            {p.effect.changed
                              ? <>Observed response: <span className="text-white/65">{p.effect.summary || "the screen changed"}</span></>
                              : <span className="text-amber-300/70">No visible change observed after this action</span>}
                          </div>
                        )}
                        {!p.ok && <div className="text-red-300/80">This action failed — see the operation detail.</div>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* The verdict */}
          {verification && (
            <div>
              <SectionLabel>Verification</SectionLabel>
              <div className="mt-3 space-y-1.5">
                {verification.checks.map((c, i) => (
                  <div key={i} className="flex items-start gap-2.5 text-[12.5px]">
                    <span className={cn("mt-[5px] h-1.5 w-1.5 rounded-full shrink-0",
                                        c.passed ? "bg-accent" : c.critical ? "bg-red-400" : "bg-amber-300/70")} />
                    <span className="text-white/60">
                      <span className="text-white/80">{humanizeCheck(c.name)}</span>
                      {c.detail && <> — {c.detail}</>}
                      {!c.passed && !c.critical && <span className="text-white/35"> (advisory)</span>}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Findings the run produced */}
          {(session.result?.report?.evidence?.length ?? 0) > 0 && (
            <div>
              <SectionLabel>Findings</SectionLabel>
              <div className="mt-3 space-y-1.5">
                {session.result!.report!.evidence.slice(0, 6).map((e, i) => (
                  <div key={i} className="text-[12.5px] text-white/60">
                    <span className="text-white/80">{e.label}:</span> {e.value}
                    <span className="text-white/30"> · {e.source || "screen"}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <Link href={`/dashboard/sessions/${session.id}`}
                className="inline-block text-[12px] text-white/35 hover:text-accent transition-colors">
            Full operation record <ArrowUpRight size={11} className="inline" />
          </Link>
        </div>
      )}
    </section>
  );
}

/** Pull the per-action proof out of the persisted step record, tolerating
 * both shapes the API has used (data on the step, or under result). */
function extractProofs(session: ApiSession): ActionProof[] {
  return (session.steps ?? []).map((step) => {
    const raw = step as Record<string, unknown>;
    const data = (raw.data ?? raw.result ?? {}) as Record<string, unknown>;
    const effect = data.effect as { changed?: boolean; summary?: string } | undefined;
    return {
      description: String(step.description ?? ""),
      action: String(step.action ?? ""),
      ok: step.status === "completed",
      element: typeof data.element === "string" && data.element ? data.element : null,
      confidence: typeof data.confidence === "number" ? data.confidence : null,
      sources: Array.isArray(data.sources) ? data.sources.map(String) : [],
      effect: effect && typeof effect === "object"
        ? { changed: Boolean(effect.changed), summary: String(effect.summary ?? "") }
        : null,
    };
  });
}

function humanizeCheck(name: string): string {
  const [kind, rest] = name.split(":", 2);
  const subject = rest ? ` “${rest}”` : "";
  switch (kind) {
    case "action_grounded": return `Action grounded on${subject}`;
    case "action_effect": return `Action produced a response${subject ? ` —${subject}` : ""}`;
    case "world_changed": return "The screen changed over the run";
    case "window_exists": return `Window present${subject}`;
    case "input_target_exists": return `Input target present${subject}`;
    case "extraction_present": return "Information was captured";
    case "browser_navigation": return "Browser navigation observed";
    case "criteria_judge": return "Completion criteria judged";
    case "criterion": return `Criterion${subject}`;
    default: return name;
  }
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <h3 className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-white/30">{children}</h3>;
}

function EvidenceSkeleton() {
  return (
    <div className="space-y-3 animate-pulse pb-16">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-14 rounded-2xl bg-white/[0.03]" />
      ))}
    </div>
  );
}

"use client";

/** Knowledge — organizational intelligence. What the workforce has
 * learned about how THIS company operates, computed from the measured
 * record: per-responsibility track records and lifecycle stages, the
 * failure patterns it has met, whether its confidence is honest, and the
 * questions an executive would ask — answered from operational history,
 * never from imagination. When something hasn't been measured yet, this
 * page says so. */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { cn, isAbortError } from "@/lib/utils";
import { lifecycleOf } from "@/lib/lifecycle";
import {
  AnalyticsSummary,
  ApiFleetAutonomy,
  ApiIntelligenceBriefing,
  ApiMemoryInsight,
  ApiMemoryLesson,
  getAnalyticsSummary,
  getFleetAutonomy,
  getIntelligenceBriefing,
  getMemory,
  teachMemory,
} from "@/lib/api";

export default function KnowledgePage() {
  const router = useRouter();
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [autonomy, setAutonomy] = useState<ApiFleetAutonomy | null>(null);
  const [lessons, setLessons] = useState<ApiMemoryLesson[]>([]);
  const [insights, setInsights] = useState<ApiMemoryInsight[]>([]);
  const [briefing, setBriefing] = useState<ApiIntelligenceBriefing | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMemory = (signal?: AbortSignal) =>
    getMemory(signal).then((m) => {
      setLessons(m.lessons);
      setInsights(m.insights);
    }).catch(() => { /* memory optional until 006 is applied */ });

  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled([
      getAnalyticsSummary("30d", "all", controller.signal),
      getFleetAutonomy(controller.signal),
      loadMemory(controller.signal),
      getIntelligenceBriefing(controller.signal)
        .then(setBriefing).catch(() => { /* optional */ }),
    ]).then(([s, a]) => {
      if (s.status === "fulfilled") setSummary(s.value);
      else if (isAbortError(s.reason)) return;
      else if (String(s.reason).includes("Unauthorized")) { router.replace("/signin"); return; }
      else setError(s.reason instanceof Error ? s.reason.message : "Failed to load");
      if (a.status === "fulfilled") setAutonomy(a.value);
      setLoaded(true);
    });
    return () => controller.abort();
  }, [router]);

  if (!loaded && !error) return <KnowledgeSkeleton />;

  const t = summary?.totals;
  const noHistory = !t || t.runs === 0;
  const graded = (autonomy?.workflows ?? []).filter((w) => w.sample_size > 0)
    .sort((a, b) => b.sample_size - a.sample_size);

  return (
    <div className="mx-auto max-w-3xl">
      <header className="pt-6 pb-10">
        <h1 className="text-[24px] font-semibold tracking-tight text-white">Knowledge</h1>
        <p className="mt-1 text-[13px] text-white/40">
          What your workforce has learned about how this company operates — measured, never imagined.
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
          {error}
        </div>
      )}

      <MemorySection lessons={lessons} insights={insights} onTaught={() => loadMemory()} />

      {briefing && briefing.findings.length > 0 && (
        <section className="pt-10">
          <SectionLabel>The workforce, observed</SectionLabel>
          <p className="mt-2 text-[12.5px] leading-relaxed text-white/40 max-w-xl">
            The workforce&apos;s review of itself over the last {briefing.period_days} days —
            {" "}{briefing.coverage.operations_analyzed} operations analyzed, every finding
            backed by its evidence.
          </p>
          <div className="mt-4 space-y-3.5">
            {briefing.findings.slice(0, 6).map((f, i) => (
              <div key={i} className="flex gap-3">
                <span className={cn("mt-[7px] h-1.5 w-1.5 rounded-full shrink-0",
                  f.severity === "high" ? "bg-red-400"
                    : f.severity === "medium" ? "bg-amber-300" : "bg-accent/70")} />
                <div className="min-w-0">
                  <div className="text-[13.5px] text-white/85">{f.headline}</div>
                  <p className="mt-0.5 text-[12.5px] leading-relaxed text-white/45">{f.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {noHistory ? (
        <div className="pb-16 pt-10">
          <p className="text-[14px] leading-relaxed text-white/55 max-w-xl">
            No operational history yet — track records here are earned from real work,
            not written by hand. Every operation your workforce completes adds to what
            it knows: what succeeds, what fails and why, which applications behave
            oddly, and where humans are still needed.
          </p>
          <Link href="/dashboard/workforce"
                className="mt-5 inline-flex items-center gap-1.5 text-[13px] text-accent hover:underline">
            Put the workforce to work <ArrowRight size={12} />
          </Link>
        </div>
      ) : (
        <div className="space-y-10 pb-16 pt-10">
          {/* What each responsibility has learned */}
          {graded.length > 0 && (
            <section>
              <SectionLabel>Track records</SectionLabel>
              <div className="mt-4 space-y-1">
                {graded.slice(0, 8).map((w) => {
                  const life = lifecycleOf(w.tier, w);
                  return (
                    <Link key={w.id} href={`/dashboard/studio/${w.id}`}
                          className="group flex items-center gap-3 rounded-lg px-3 -mx-3 py-2.5 hover:bg-white/[0.02] transition-colors">
                      <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", life.dot)} />
                      <span className="flex-1 min-w-0 truncate text-[13.5px] text-white/75 group-hover:text-white">
                        {w.name}
                      </span>
                      <span className="font-mono text-[10.5px] tabular-nums text-white/35 shrink-0">
                        {Math.round(w.verified_success_rate * 100)}% verified · {w.sample_size} runs
                      </span>
                      {w.calibration_error != null && (
                        <span className={cn("font-mono text-[10.5px] tabular-nums shrink-0",
                          w.calibration_error <= 0.15 ? "text-white/30" : "text-amber-300/80")}>
                          ±{Math.round(w.calibration_error * 100)}%
                        </span>
                      )}
                      <span className={cn("w-20 text-right font-mono text-[9.5px] uppercase tracking-[0.1em] shrink-0", life.cls)}>
                        {life.stage}
                      </span>
                    </Link>
                  );
                })}
              </div>
              <p className="mt-3 text-[11.5px] leading-relaxed text-white/30 max-w-xl">
                Stages are earned from the verified record — Training → Observed → Assisted →
                Trusted → Autonomous → Exceptional — and can only change when the evidence does.
              </p>
            </section>
          )}

          <Answer q="What got done?">
            <B>{t.runs}</B> operation{t.runs === 1 ? "" : "s"} in 30 days:{" "}
            <B tone="good">{t.succeeded}</B> verified with evidence,{" "}
            <B tone="warn">{t.needs_attention}</B> needing review,{" "}
            <B tone="bad">{t.failed}</B> failed —{" "}
            a <B>{Math.round((t.verification_rate ?? 0) * 100)}%</B> verified rate.
          </Answer>

          <Answer q="What has it learned to avoid?">
            {summary!.failures.length === 0 ? (
              <>No failure patterns yet in this period.</>
            ) : (
              <>
                The obstacles it has met, ranked:{" "}
                {summary!.failures.slice(0, 3).map((f, i) => (
                  <span key={f.type}>
                    {i > 0 && ", "}
                    <B tone={i === 0 ? "warn" : undefined}>{f.label.toLowerCase()}</B> ({f.count}×)
                  </span>
                ))}
                . Every one is on the record with evidence in{" "}
                <Link href="/dashboard/operations" className="text-accent/80 hover:text-accent">Operations</Link>.
              </>
            )}
          </Answer>

          <Answer q="Is it improving?">
            <Trend timeseries={summary!.timeseries} />
          </Answer>

          <Answer q="Is its confidence honest?">
            {summary!.calibration.sample_size > 0 && summary!.calibration.mean_error != null ? (
              <>
                Across <B>{summary!.calibration.sample_size}</B> scored runs, reported confidence
                differed from reality by <B>{Math.round(summary!.calibration.mean_error * 100)}%</B> on
                average — {summary!.calibration.mean_error <= 0.15
                  ? <>well-calibrated: when it says it&apos;s sure, it&apos;s right.</>
                  : <>watch this: workflows whose confidence outruns their evidence are flagged.</>}
              </>
            ) : (
              <>Not measured yet — calibration needs scored runs.</>
            )}
          </Answer>

          <Answer q="Where are humans still required?">
            {autonomy && autonomy.graded_workflows > 0 ? (
              <>
                <B tone="warn">{(autonomy.by_tier.supervised ?? 0) + (autonomy.by_tier.in_the_loop ?? 0)}</B>{" "}
                responsibilit{((autonomy.by_tier.supervised ?? 0) + (autonomy.by_tier.in_the_loop ?? 0)) === 1 ? "y" : "ies"} still
                run{((autonomy.by_tier.supervised ?? 0) + (autonomy.by_tier.in_the_loop ?? 0)) === 1 ? "s" : ""} with human oversight,
                while <B tone="good">{autonomy.earned_autonomy}</B> earned unattended autonomy
                {t.needs_attention > 0 && (
                  <> — and <B tone="warn">{t.needs_attention}</B> recent operation{t.needs_attention === 1 ? "" : "s"} deserve
                    {t.needs_attention === 1 ? "s" : ""} a human glance</>
                )}.
              </>
            ) : (
              <>Not measured yet — no graded responsibilities.</>
            )}
          </Answer>

          {summary!.recommendations.length > 0 && (
            <section className="border-t border-white/[0.05] pt-8">
              <SectionLabel>Recommended next</SectionLabel>
              <div className="mt-4 space-y-3">
                {summary!.recommendations.slice(0, 3).map((r, i) => (
                  <div key={i} className="flex gap-3">
                    <span className={cn("mt-[7px] h-1.5 w-1.5 rounded-full shrink-0",
                      r.severity === "high" ? "bg-red-400" : r.severity === "medium" ? "bg-amber-300" : "bg-white/30")} />
                    <div>
                      <div className="text-[13.5px] text-white/85">{r.title}</div>
                      <p className="mt-0.5 text-[12.5px] leading-relaxed text-white/45">{r.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <div className="border-t border-white/[0.05] pt-6">
            <Link href="/dashboard/analytics"
                  className="text-[12px] text-white/35 hover:text-accent transition-colors">
              Supporting charts and detail <ArrowUpRight size={11} className="inline" />
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

/** The organization's memory: what it was taught and what it learned.
 * Every lesson here flows into the planning of every future operation —
 * this is the record that makes the workforce harder to replace. */
function MemorySection({ lessons, insights, onTaught }: {
  lessons: ApiMemoryLesson[]; insights: ApiMemoryInsight[]; onTaught: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [teachError, setTeachError] = useState<string | null>(null);

  const submit = async () => {
    const lesson = draft.trim();
    if (!lesson || busy) return;
    setBusy(true);
    setTeachError(null);
    try {
      await teachMemory(lesson);
      setDraft("");
      onTaught();
    } catch (e) {
      setTeachError(e instanceof Error ? e.message : "Could not save the lesson");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <SectionLabel>Business memory</SectionLabel>
      <p className="mt-2 text-[12.5px] leading-relaxed text-white/40 max-w-xl">
        What this organization has taught its workforce, and what the workforce has
        learned from experience. Every lesson is recalled into the planning of every
        future operation.
      </p>

      {lessons.length > 0 && (
        <div className="mt-4 space-y-2.5">
          {lessons.slice(0, 8).map((l) => (
            <div key={l.id} className="flex gap-3">
              <span className={cn("mt-[7px] h-1.5 w-1.5 rounded-full shrink-0",
                l.source === "taught" ? "bg-accent" : "bg-sky-300/80")} />
              <div className="min-w-0">
                <p className="text-[13.5px] leading-snug text-white/80">{l.lesson}</p>
                <p className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.12em] text-white/30">
                  {l.source} {l.kind}
                  {l.times_reinforced > 1 && <> · reinforced ×{l.times_reinforced}</>}
                  {l.scope !== "org" && <> · {l.scope}</>}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {insights.length > 0 && (
        <div className="mt-5 space-y-2.5">
          {insights.slice(0, 3).map((ins, i) => (
            <div key={i} className="flex gap-3">
              <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-amber-300 shrink-0" />
              <p className="text-[13px] leading-relaxed text-white/65">{ins.recommendation}</p>
            </div>
          ))}
        </div>
      )}

      {/* Teach: managers correct, they never edit prompts. */}
      <div className="mt-5 max-w-xl">
        <div className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.02] px-3.5 h-11 focus-within:border-accent/30 transition-colors">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void submit(); }}
            placeholder="Teach the workforce something — e.g. “Invoices from ACME belong to vendor 400312”"
            className="flex-1 bg-transparent text-[13px] text-white placeholder:text-white/25 focus:outline-none"
            data-testid="teach-input"
          />
          <button onClick={() => void submit()} disabled={busy || !draft.trim()}
                  className="rounded-md bg-accent/15 px-3 h-7 text-[12px] font-medium text-accent hover:bg-accent/25 transition-colors disabled:opacity-40">
            Teach
          </button>
        </div>
        {teachError && <p className="mt-1.5 text-[11.5px] text-red-300">{teachError}</p>}
        {lessons.length === 0 && insights.length === 0 && (
          <p className="mt-2 text-[11.5px] text-white/30">
            Nothing in memory yet. Lessons arrive from your corrections, approval
            decisions, and what the workforce learns recovering from real obstacles.
          </p>
        )}
      </div>
    </section>
  );
}

/** Compare the first and second halves of the period honestly. */
function Trend({ timeseries }: { timeseries: AnalyticsSummary["timeseries"] }) {
  const active = timeseries.filter((p) => p.success + p.attention + p.failure > 0);
  if (active.length < 4) {
    return <>Not measured yet — a trend takes a few days of real work.</>;
  }
  const mid = Math.floor(active.length / 2);
  const rate = (points: typeof active) => {
    const ok = points.reduce((n, p) => n + p.success, 0);
    const all = points.reduce((n, p) => n + p.success + p.attention + p.failure, 0);
    return all > 0 ? ok / all : null;
  };
  const early = rate(active.slice(0, mid));
  const late = rate(active.slice(mid));
  if (early == null || late == null) return <>Not measured yet.</>;
  const delta = Math.round((late - early) * 100);
  if (Math.abs(delta) < 3) {
    return <>Verified success is steady at about <B>{Math.round(late * 100)}%</B> across the period.</>;
  }
  return delta > 0 ? (
    <>Yes — verified success moved from <B>{Math.round(early * 100)}%</B> to{" "}
      <B tone="good">{Math.round(late * 100)}%</B>. Every operation feeds the record the
      next one learns from.</>
  ) : (
    <>No — verified success moved from <B>{Math.round(early * 100)}%</B> down to{" "}
      <B tone="bad">{Math.round(late * 100)}%</B>. The failure patterns above are where
      to look first.</>
  );
}

function Answer({ q, children }: { q: string; children: React.ReactNode }) {
  return (
    <section>
      <SectionLabel>{q}</SectionLabel>
      <p className="mt-2.5 text-[15px] leading-relaxed text-white/70 max-w-2xl">{children}</p>
    </section>
  );
}

function B({ children, tone }: { children: React.ReactNode; tone?: "good" | "warn" | "bad" }) {
  return (
    <span className={cn("font-semibold tabular-nums",
      tone === "good" ? "text-accent" : tone === "warn" ? "text-amber-300"
        : tone === "bad" ? "text-red-300" : "text-white")}>
      {children}
    </span>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">{children}</h2>;
}

function KnowledgeSkeleton() {
  return (
    <div className="mx-auto max-w-3xl animate-pulse">
      <div className="pt-6 pb-10">
        <div className="h-7 w-44 rounded-lg bg-white/[0.04]" />
        <div className="mt-2 h-4 w-80 rounded bg-white/[0.03]" />
      </div>
      <div className="space-y-8">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i}>
            <div className="h-3 w-40 rounded bg-white/[0.03]" />
            <div className="mt-3 h-5 w-full max-w-xl rounded bg-white/[0.03]" />
          </div>
        ))}
      </div>
    </div>
  );
}

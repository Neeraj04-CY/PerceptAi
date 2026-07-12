"use client";

/** Answers — what an executive actually asks, answered in sentences from
 * measured data. Charts are supporting detail behind this page, not the
 * product. Every number here is computed from real runs; when there isn't
 * enough history to answer honestly, the answer says so. */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { cn, isAbortError } from "@/lib/utils";
import {
  AnalyticsSummary,
  ApiFleetAutonomy,
  getAnalyticsSummary,
  getFleetAutonomy,
} from "@/lib/api";

export default function AnswersPage() {
  const router = useRouter();
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [autonomy, setAutonomy] = useState<ApiFleetAutonomy | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled([
      getAnalyticsSummary("30d", "all", controller.signal),
      getFleetAutonomy(controller.signal),
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

  if (!loaded && !error) return <AnswersSkeleton />;

  const t = summary?.totals;
  const noHistory = !t || t.runs === 0;

  return (
    <div className="mx-auto max-w-3xl">
      <header className="pt-6 pb-10">
        <h1 className="text-[24px] font-semibold tracking-tight text-white">Answers</h1>
        <p className="mt-1 text-[13px] text-white/40">
          The last 30 days, answered from measured evidence — not dashboards.
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
          {error}
        </div>
      )}

      {noHistory ? (
        <div className="pb-16">
          <p className="text-[14px] leading-relaxed text-white/55 max-w-xl">
            There isn&apos;t enough history to answer questions honestly yet. Once your
            workforce has run real work, this page tells you what succeeded, what failed
            and why, what&apos;s improving, and which workflows have earned full autonomy.
          </p>
          <Link href="/dashboard/templates"
                className="mt-5 inline-flex items-center gap-1.5 text-[13px] text-accent hover:underline">
            Put it to work <ArrowRight size={12} />
          </Link>
        </div>
      ) : (
        <div className="space-y-10 pb-16">
          <Answer q="What got done?">
            Your workforce ran <B>{t.runs}</B> operation{t.runs === 1 ? "" : "s"}:{" "}
            <B tone="good">{t.succeeded}</B> finished with verified evidence,{" "}
            <B tone="warn">{t.needs_attention}</B> finished but couldn&apos;t be fully verified, and{" "}
            <B tone="bad">{t.failed}</B> failed.
            {" "}That is a <B>{Math.round((t.verification_rate ?? 0) * 100)}%</B> verified rate.
          </Answer>

          <Answer q="What failed, and why?">
            {summary!.failures.length === 0 ? (
              <>Nothing failed in this period.</>
            ) : (
              <>
                The leading causes:{" "}
                {summary!.failures.slice(0, 3).map((f, i) => (
                  <span key={f.type}>
                    {i > 0 && ", "}
                    <B tone={i === 0 ? "warn" : undefined}>{f.label.toLowerCase()}</B> ({f.count}×)
                  </span>
                ))}
                . Each failure is on the record with its evidence in{" "}
                <Link href="/dashboard/operations" className="text-accent/80 hover:text-accent">Operations</Link>.
              </>
            )}
          </Answer>

          <Answer q="Is it improving?">
            <Trend timeseries={summary!.timeseries} />
          </Answer>

          <Answer q="Which workflows earned full autonomy?">
            {autonomy && autonomy.earned_autonomy > 0 ? (
              <>
                <B tone="good">{autonomy.earned_autonomy}</B> of{" "}
                <B>{autonomy.graded_workflows}</B> graded workflows run unattended on verified
                track records:{" "}
                {autonomy.workflows.filter((w) => w.tier === "ready").slice(0, 4).map((w, i) => (
                  <span key={w.id}>
                    {i > 0 && ", "}
                    <Link href={`/dashboard/studio/${w.id}`} className="text-white hover:text-accent">
                      {w.name}
                    </Link>{" "}
                    ({Math.round(w.verified_success_rate * 100)}% over {w.sample_size} runs)
                  </span>
                ))}.
              </>
            ) : (
              <>
                None yet — autonomy is earned, not claimed. A workflow qualifies by
                accumulating verified successful runs with honest confidence.
                {autonomy && autonomy.graded_workflows > 0 && (
                  <> <B>{autonomy.graded_workflows}</B> are building their track record now.</>
                )}
              </>
            )}
          </Answer>

          <Answer q="Where are humans still required?">
            {autonomy ? (
              <>
                <B tone="warn">{(autonomy.by_tier.supervised ?? 0) + (autonomy.by_tier.in_the_loop ?? 0)}</B>{" "}
                workflow{((autonomy.by_tier.supervised ?? 0) + (autonomy.by_tier.in_the_loop ?? 0)) === 1 ? "" : "s"} still
                need supervision or in-the-loop review
                {t.needs_attention > 0 && (
                  <>, and <B tone="warn">{t.needs_attention}</B> recent operation{t.needs_attention === 1 ? "" : "s"} finished
                    without full verification and deserve{t.needs_attention === 1 ? "s" : ""} a human glance</>
                )}.
              </>
            ) : (
              <>No graded workflows yet.</>
            )}
          </Answer>

          <Answer q="Is its confidence honest?">
            {summary!.calibration.sample_size > 0 && summary!.calibration.mean_error != null ? (
              <>
                Across <B>{summary!.calibration.sample_size}</B> scored runs, reported confidence
                differed from reality by <B>{Math.round(summary!.calibration.mean_error * 100)}%</B> on
                average — {summary!.calibration.mean_error <= 0.15
                  ? <>well-calibrated: when it says it&apos;s sure, it&apos;s right.</>
                  : <>watch this: the platform flags workflows whose confidence outruns their evidence.</>}
              </>
            ) : (
              <>Not enough scored runs to measure calibration yet.</>
            )}
          </Answer>

          {summary!.recommendations.length > 0 && (
            <section className="border-t border-white/[0.05] pt-8">
              <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">
                What to do next
              </h2>
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

/** Compare the first and second halves of the period honestly. */
function Trend({ timeseries }: { timeseries: AnalyticsSummary["timeseries"] }) {
  const active = timeseries.filter((p) => p.success + p.attention + p.failure > 0);
  if (active.length < 4) {
    return <>Not enough history to call a trend yet — it takes a few days of real work.</>;
  }
  const mid = Math.floor(active.length / 2);
  const rate = (points: typeof active) => {
    const ok = points.reduce((n, p) => n + p.success, 0);
    const all = points.reduce((n, p) => n + p.success + p.attention + p.failure, 0);
    return all > 0 ? ok / all : null;
  };
  const early = rate(active.slice(0, mid));
  const late = rate(active.slice(mid));
  if (early == null || late == null) return <>Not enough history to call a trend yet.</>;
  const delta = Math.round((late - early) * 100);
  if (Math.abs(delta) < 3) {
    return <>Verified success is steady at about <B>{Math.round(late * 100)}%</B> across the period.</>;
  }
  return delta > 0 ? (
    <>Yes — verified success moved from <B>{Math.round(early * 100)}%</B> to{" "}
      <B tone="good">{Math.round(late * 100)}%</B> across the period. Every run feeds
      the record the next one learns from.</>
  ) : (
    <>No — verified success moved from <B>{Math.round(early * 100)}%</B> down to{" "}
      <B tone="bad">{Math.round(late * 100)}%</B>. The failure causes above are where
      to look first.</>
  );
}

function Answer({ q, children }: { q: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">{q}</h2>
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

function AnswersSkeleton() {
  return (
    <div className="mx-auto max-w-3xl animate-pulse">
      <div className="pt-6 pb-10">
        <div className="h-7 w-40 rounded-lg bg-white/[0.04]" />
        <div className="mt-2 h-4 w-72 rounded bg-white/[0.03]" />
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

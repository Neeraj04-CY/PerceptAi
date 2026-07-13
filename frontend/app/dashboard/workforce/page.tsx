"use client";

/** Workforce — the hero. Your AI employees, presented the way you'd read a
 * team page: who they are (department operators), what they're trusted
 * with, and what they've earned. Everything measured is real: trust comes
 * from verified success rates, autonomy from the evidence-backed verdicts.
 * A role with no hires yet says "Open role" — it never fakes a track
 * record. Workflows are attributed to an operator by the template they
 * were hired from; unmatched work rolls up to the General Operator. */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { cn, isAbortError } from "@/lib/utils";
import { lifecycleOf } from "@/lib/lifecycle";
import {
  ApiFleetAutonomy,
  ApiPack,
  ApiWorkflow,
  ApiWorkflowCard,
  getFleetAutonomy,
  getPacks,
  getWorkflows,
} from "@/lib/api";

interface Employee {
  id: string;
  title: string;        // "Finance Operator"
  tagline: string;
  capabilities: string[];   // template names this role can take on
  applications: string[];   // systems those capabilities touch
  workflows: Array<{ workflow: ApiWorkflow; card: ApiWorkflowCard | null }>;
}

const OPERATOR_TITLES: Record<string, string> = {
  finance: "Finance Operator",
  sales: "Sales Operator",
  procurement: "Procurement Operator",
  people: "HR & IT Operator",
  support: "Support Operator",
};

export default function WorkforcePage() {
  const router = useRouter();
  const [packs, setPacks] = useState<ApiPack[]>([]);
  const [workflows, setWorkflows] = useState<ApiWorkflow[] | null>(null);
  const [autonomy, setAutonomy] = useState<ApiFleetAutonomy | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled([
      getPacks(controller.signal),
      getWorkflows(controller.signal),
      getFleetAutonomy(controller.signal),
    ]).then(([p, w, a]) => {
      if (w.status === "rejected") {
        if (isAbortError(w.reason)) return;
        if (String(w.reason).includes("Unauthorized")) { router.replace("/signin"); return; }
        setError(w.reason instanceof Error ? w.reason.message : "Failed to load");
      } else setWorkflows(w.value);
      if (p.status === "fulfilled") setPacks(p.value);
      if (a.status === "fulfilled") setAutonomy(a.value);
    });
    return () => controller.abort();
  }, [router]);

  const employees = useMemo<Employee[]>(() => {
    if (workflows === null) return [];
    const cardOf = (id: string) => autonomy?.workflows.find((c) => c.id === id) ?? null;
    const templateNames = new Map<string, string>(); // template name -> pack id
    for (const pack of packs) {
      for (const t of pack.templates) templateNames.set(t.name.toLowerCase(), pack.id);
    }
    const byPack = new Map<string, Employee>();
    for (const pack of packs) {
      byPack.set(pack.id, {
        id: pack.id,
        title: OPERATOR_TITLES[pack.id] ?? `${pack.name} Operator`,
        tagline: pack.tagline,
        capabilities: pack.templates.map((t) => t.name),
        applications: [...new Set(pack.templates.flatMap((t) => t.apps ?? []))],
        workflows: [],
      });
    }
    const general: Employee = {
      id: "general", title: "General Operator",
      tagline: "Work briefed in your own words — outside the standing roles.",
      capabilities: [], applications: [], workflows: [],
    };
    for (const wf of workflows) {
      const packId = templateNames.get(wf.name.toLowerCase());
      const target = (packId && byPack.get(packId)) || general;
      target.workflows.push({ workflow: wf, card: cardOf(wf.id) });
    }
    const list = [...byPack.values()];
    if (general.workflows.length > 0) list.push(general);
    // Active employees first, then open roles.
    return list.sort((a, b) => b.workflows.length - a.workflows.length);
  }, [packs, workflows, autonomy]);

  const active = employees.filter((e) => e.workflows.length > 0);

  return (
    <div className="mx-auto max-w-3xl">
      <header className="pt-6 pb-10 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[24px] font-semibold tracking-tight text-white">Workforce</h1>
          <p className="mt-1 text-[13px] text-white/40">
            {active.length > 0
              ? <>Your AI employees — trust is measured, autonomy is earned.</>
              : <>Five operators, ready to hire. Trust is measured, autonomy is earned.</>}
          </p>
        </div>
        <Link href="/dashboard/templates"
              className="shrink-0 inline-flex items-center gap-2 rounded-lg bg-accent text-black px-4 h-9 text-[13px] font-medium hover:shadow-[0_0_32px_-8px_rgba(0,255,133,0.6)] transition-shadow">
          Hire <ArrowRight size={13} />
        </Link>
      </header>

      {error && (
        <div className="mb-6 rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
          {error}
        </div>
      )}

      {workflows === null && !error ? (
        <WorkforceSkeleton />
      ) : (
        <div className="space-y-4 pb-16">
          {employees.map((e) => <EmployeeCard key={e.id} employee={e} />)}
        </div>
      )}
    </div>
  );
}

function EmployeeCard({ employee }: { employee: Employee }) {
  const hired = employee.workflows.length > 0;
  const graded = employee.workflows.filter((w) => w.card && w.card.sample_size > 0);
  const totalRuns = graded.reduce((n, w) => n + (w.card?.sample_size ?? 0), 0);
  const trust = totalRuns > 0
    ? graded.reduce((n, w) => n + (w.card!.verified_success_rate * w.card!.sample_size), 0) / totalRuns
    : null;
  const earned = employee.workflows.filter((w) => w.card?.tier === "ready").length;

  return (
    <section className={cn(
      "rounded-2xl border p-6 transition-colors",
      hired ? "border-white/[0.08] bg-white/[0.015]" : "border-white/[0.05] bg-transparent")}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <h2 className={cn("text-[17px] font-semibold tracking-tight", hired ? "text-white" : "text-white/60")}>
              {employee.title}
            </h2>
            {!hired && (
              <span className="rounded-full border border-white/[0.1] px-2 py-[2px] font-mono text-[9px] uppercase tracking-[0.14em] text-white/35">
                open role
              </span>
            )}
          </div>
          <p className="mt-1 text-[12.5px] leading-relaxed text-white/40 max-w-lg">{employee.tagline}</p>
        </div>
        {hired ? (
          <div className="text-right shrink-0">
            {trust != null ? (
              <>
                <div className={cn("text-[22px] font-semibold tabular-nums leading-none",
                  trust >= 0.9 ? "text-accent" : trust >= 0.7 ? "text-amber-300" : "text-white/70")}>
                  {Math.round(trust * 100)}%
                </div>
                <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.14em] text-white/30">
                  verified · {totalRuns} runs
                </div>
              </>
            ) : (
              <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-white/30 pt-2">
                no measured runs yet
              </div>
            )}
          </div>
        ) : (
          <Link href="/dashboard/templates"
                className="shrink-0 inline-flex items-center gap-1.5 rounded-lg border border-white/[0.1] px-3.5 h-9 text-[12.5px] text-white/70 hover:text-white hover:border-white/25 transition-colors">
            Hire <ArrowRight size={12} />
          </Link>
        )}
      </div>

      {hired && (
        <div className="mt-5 space-y-1.5">
          {employee.workflows.slice(0, 4).map(({ workflow, card }) => {
            const life = lifecycleOf(card?.tier ?? null, card, workflow.status);
            return (
              <Link key={workflow.id} href={`/dashboard/studio/${workflow.id}`}
                    className="group flex items-center gap-3 rounded-lg px-3 -mx-3 py-2 hover:bg-white/[0.02] transition-colors">
                <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", life.dot)} />
                <span className="flex-1 min-w-0 truncate text-[13.5px] text-white/75 group-hover:text-white">
                  {workflow.name}
                </span>
                {card && card.sample_size > 0 && (
                  <span className="font-mono text-[10.5px] tabular-nums text-white/35 shrink-0">
                    {Math.round(card.verified_success_rate * 100)}% · {card.sample_size}
                  </span>
                )}
                <span className={cn("font-mono text-[9.5px] uppercase tracking-[0.1em] shrink-0", life.cls)}>
                  {life.stage}
                </span>
              </Link>
            );
          })}
          {earned > 0 && (
            <p className="pt-1.5 text-[11.5px] text-white/35">
              {earned} of {employee.workflows.length} responsibilities earned unattended autonomy.
            </p>
          )}
        </div>
      )}

      {!hired && employee.capabilities.length > 0 && (
        <div className="mt-4">
          <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-white/30">Can take on</div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-white/50">
            {employee.capabilities.join(" · ")}
          </p>
          {employee.applications.length > 0 && (
            <p className="mt-1.5 text-[11px] text-white/30">
              Works in {employee.applications.slice(0, 6).join(", ")}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function WorkforceSkeleton() {
  return (
    <div className="space-y-4 animate-pulse pb-16">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-36 rounded-2xl bg-white/[0.03]" />
      ))}
    </div>
  );
}

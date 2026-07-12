"use client";

/** Agent Studio — the enterprise workflow catalog. A workflow is a named,
 * versioned, parametrized instruction that compiles to the one runtime, so
 * authoring is text + variables, not a node canvas. The catalog groups the
 * proven workflows into department packs a buyer recognizes, framed by the
 * business value they remove. */

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowRight,
  CalendarClock,
  KeyRound,
  PenTool,
  Plus,
  Rocket,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { cn, isAbortError } from "@/lib/utils";
import { PageHeader } from "@/components/dashboard/page-header";
import {
  ApiPack,
  ApiTemplate,
  ApiWorkflow,
  createWorkflow,
  getPacks,
  getWorkflows,
} from "@/lib/api";

export default function StudioPage() {
  return (
    <Suspense fallback={<StudioSkeleton />}>
      <Studio />
    </Suspense>
  );
}

function Studio() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [workflows, setWorkflows] = useState<ApiWorkflow[] | null>(null);
  const [packs, setPacks] = useState<ApiPack[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled([
      getWorkflows(controller.signal),
      getPacks(controller.signal),
    ]).then(([w, p]) => {
      if (w.status === "fulfilled") setWorkflows(w.value);
      else if (isAbortError(w.reason)) { /* ignore */ }
      else if (String(w.reason).includes("Unauthorized")) router.replace("/signin");
      else setError(w.reason instanceof Error ? w.reason.message : "Failed to load workflows");
      if (p.status === "fulfilled") setPacks(p.value);
    });
    return () => controller.abort();
  }, [router]);

  // Deep link from onboarding: /dashboard/studio?template=<id>
  useEffect(() => {
    const templateId = searchParams.get("template");
    if (templateId && workflows !== null && !creating) {
      void startFrom(templateId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, workflows]);

  const startFrom = async (templateId: string | null) => {
    setCreating(templateId ?? "blank");
    try {
      const created = await createWorkflow(
        templateId
          ? { template_id: templateId, name: "", instruction: "" }
          : { name: "Untitled workflow", instruction: "", mode: "task" });
      router.push(`/dashboard/studio/${created.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create workflow");
      setCreating(null);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Studio"
        subtitle="Pick a workflow you already do by hand. Fill two fields. Run it — or schedule it."
        actions={
          <button onClick={() => startFrom(null)} disabled={creating !== null}
                  className="inline-flex h-9 items-center gap-2 rounded-full bg-accent px-4 text-[13px] font-medium text-black hover:shadow-[0_0_32px_-8px_rgba(0,255,133,0.6)] transition-shadow disabled:opacity-50">
            <Plus size={14} strokeWidth={2.4} /> New workflow
          </button>
        }
      />

      {error && (
        <div className="rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
          {error}
        </div>
      )}

      {workflows === null && !error ? (
        <StudioSkeleton />
      ) : (
        <>
          {/* Your library */}
          {workflows && workflows.length > 0 && (
            <section>
              <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
                Your workflows
              </h2>
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                          className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {workflows.map((workflow) => (
                  <Link key={workflow.id} href={`/dashboard/studio/${workflow.id}`}
                        className="glass group rounded-xl border border-transparent p-4 hover:border-accent/25 transition-colors">
                    <div className="flex items-center justify-between gap-2">
                      <span className={cn(
                        "rounded border px-1.5 py-[1px] font-mono text-[9px] uppercase tracking-wider",
                        workflow.status === "published"
                          ? "border-accent/25 text-accent/85"
                          : "border-white/15 text-white/40",
                      )}>
                        {workflow.status === "published" ? `v${workflow.version}` : workflow.status}
                      </span>
                      <span className="font-mono text-[9px] uppercase tracking-wider text-white/30">
                        {workflow.mode}
                      </span>
                    </div>
                    <div className="mt-2.5 flex items-center gap-2 text-[14px] text-white/90 group-hover:text-white">
                      <PenTool size={13} className="text-white/25 shrink-0" />
                      <span className="truncate">{workflow.name}</span>
                    </div>
                    <p className="mt-1 text-[11px] leading-relaxed text-white/40 line-clamp-2 min-h-[2.4em]">
                      {workflow.description || workflow.instruction || "No description yet."}
                    </p>
                    <div className="mt-3 flex items-center gap-3 font-mono text-[9px] uppercase tracking-wider text-white/25">
                      <span>{(workflow.variables || []).length} variable(s)</span>
                      {workflow.schedule?.enabled && (
                        <span className="flex items-center gap-1 text-accent/70">
                          <CalendarClock size={10} /> every {formatInterval(workflow.schedule.interval_minutes)}
                        </span>
                      )}
                    </div>
                  </Link>
                ))}
              </motion.div>
            </section>
          )}

          {/* Why this is different — the three claims a buyer must feel */}
          <DifferentiatorStrip />

          {/* The enterprise catalog, grouped by department pack */}
          <section className="space-y-6">
            <div className="flex items-baseline justify-between">
              <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
                {workflows && workflows.length > 0 ? "Workflow catalog" : "Start from a proven workflow"}
              </h2>
              <span className="font-mono text-[10px] text-white/25">
                {packs.reduce((n, p) => n + p.templates.length, 0)} workflows · {packs.length} packs
              </span>
            </div>
            {packs.map((pack) => (
              <Pack key={pack.id} pack={pack} creating={creating} onStart={startFrom} />
            ))}
          </section>
        </>
      )}
    </div>
  );
}

function DifferentiatorStrip() {
  const items = [
    { icon: <KeyRound size={14} />, title: "Credentials it can't leak",
      body: "Logs into apps with a vault secret the model never sees — the value never enters a prompt, event or report." },
    { icon: <ShieldCheck size={14} />, title: "Resistant to a hostile screen",
      body: "Reads whatever's on screen but obeys only your goal — a page telling it to exfiltrate data is flagged, not followed." },
    { icon: <Sparkles size={14} />, title: "Verified outcomes, not clicks",
      body: "Checks the real result — the invoice was posted, the record saved — instead of assuming a script ran." },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      {items.map((it) => (
        <div key={it.title} className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
          <div className="flex items-center gap-2 text-accent">
            {it.icon}
            <span className="text-[12.5px] font-medium text-white/90">{it.title}</span>
          </div>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-white/45">{it.body}</p>
        </div>
      ))}
    </div>
  );
}

function Pack({ pack, creating, onStart }: {
  pack: ApiPack; creating: string | null; onStart: (id: string) => void;
}) {
  if (pack.templates.length === 0) return null;
  const isStarter = pack.id === "starter";
  return (
    <div>
      <div className="mb-2.5 flex items-center gap-2.5">
        {isStarter && <Rocket size={14} className="text-accent" />}
        <h3 className="text-[14px] font-medium text-white">{pack.name}</h3>
        <span className="text-[12px] text-white/40">{pack.tagline}</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {pack.templates.map((t) => (
          <TemplateCard key={t.id} template={t} creating={creating} onStart={onStart} starter={isStarter} />
        ))}
      </div>
    </div>
  );
}

function TemplateCard({ template, creating, onStart, starter }: {
  template: ApiTemplate; creating: string | null; onStart: (id: string) => void; starter?: boolean;
}) {
  const busy = creating === template.id;
  return (
    <button onClick={() => onStart(template.id)} disabled={creating !== null}
            className={cn(
              "group flex h-full flex-col rounded-xl border p-4 text-left transition-colors disabled:opacity-60",
              starter
                ? "border-accent/25 bg-accent/[0.04] hover:border-accent/45"
                : "glass border-transparent hover:border-accent/25")}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-white/30">
          {template.category}
        </span>
        <div className="flex items-center gap-1.5">
          {template.flagship && !starter && (
            <span className="rounded border border-accent/30 px-1.5 py-[1px] font-mono text-[8px] uppercase tracking-wider text-accent/85">
              proven
            </span>
          )}
          <span className={cn("rounded border px-1.5 py-[1px] font-mono text-[9px] uppercase",
                              template.mode === "mission"
                                ? "border-accent/25 text-accent/80"
                                : "border-white/15 text-white/40")}>
            {template.mode}
          </span>
        </div>
      </div>

      <div className="mt-2 text-[14px] font-medium text-white/90 group-hover:text-white">
        {busy ? "Creating…" : template.name}
      </div>

      {/* the business framing a buyer reads first */}
      {template.value && (
        <p className="mt-1.5 text-[11.5px] leading-relaxed text-white/55">{template.value}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5">
        {(template.apps || []).slice(0, 4).map((app) => (
          <span key={app} className="rounded-md border border-white/[0.08] px-1.5 py-[1px] font-mono text-[9px] text-white/45">
            {app}
          </span>
        ))}
      </div>

      <div className="mt-auto pt-3 flex items-center justify-between">
        <span className="font-mono text-[9px] uppercase tracking-wider text-white/30">
          {template.time_saved && template.time_saved !== "-" ? `saves ${template.time_saved}` : "produces a report"}
        </span>
        <span className="flex items-center gap-1 font-mono text-[9px] uppercase tracking-wider text-white/35 group-hover:text-accent transition-colors">
          use <ArrowRight size={10} />
        </span>
      </div>
    </button>
  );
}

function formatInterval(minutes?: number): string {
  const m = minutes ?? 1440;
  if (m % 1440 === 0) return m === 1440 ? "day" : `${m / 1440}d`;
  if (m % 60 === 0) return m === 60 ? "hour" : `${m / 60}h`;
  return `${m}m`;
}

function StudioSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 animate-pulse">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-40 rounded-xl bg-white/[0.04]" />
      ))}
    </div>
  );
}

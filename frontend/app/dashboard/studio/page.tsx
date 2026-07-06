"use client";

/** Agent Studio: the workflow library. A workflow is a named, versioned,
 * parametrized instruction — it compiles to the one runtime, so authoring
 * is text + variables, not a node canvas. */

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { CalendarClock, FileText, PenTool, Plus } from "lucide-react";
import { cn, isAbortError } from "@/lib/utils";
import { PageHeader } from "@/components/dashboard/page-header";
import {
  ApiTemplate,
  ApiWorkflow,
  createWorkflow,
  getTemplates,
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
  const [templates, setTemplates] = useState<ApiTemplate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled([
      getWorkflows(controller.signal),
      getTemplates(controller.signal),
    ]).then(([w, t]) => {
      if (w.status === "fulfilled") setWorkflows(w.value);
      else if (isAbortError(w.reason)) { /* ignore */ }
      else if (String(w.reason).includes("Unauthorized")) router.replace("/signin");
      else setError(w.reason instanceof Error ? w.reason.message : "Failed to load workflows");
      if (t.status === "fulfilled") setTemplates(t.value);
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
        subtitle="Reusable automations: parametrized instructions, versioned and schedulable."
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
          {/* library */}
          {workflows && workflows.length > 0 && (
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
          )}

          {/* template gallery */}
          <section>
            <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
              {workflows && workflows.length > 0 ? "Start from a template" : "Templates — the fastest first workflow"}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {templates.map((template) => (
                <button key={template.id} onClick={() => startFrom(template.id)}
                        disabled={creating !== null}
                        className="glass group rounded-xl border border-transparent p-4 text-left hover:border-accent/25 transition-colors disabled:opacity-60">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-white/30">
                      {template.category}
                    </span>
                    <span className={cn("rounded border px-1.5 py-[1px] font-mono text-[9px] uppercase",
                                        template.mode === "mission"
                                          ? "border-accent/25 text-accent/80"
                                          : "border-white/15 text-white/40")}>
                      {template.mode}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-[13px] text-white/85">
                    <FileText size={13} className="text-white/30 shrink-0" />
                    {creating === template.id ? "Creating…" : template.name}
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-white/40 line-clamp-2">
                    {template.description}
                  </p>
                  <p className="mt-2 font-mono text-[9px] uppercase tracking-wider text-white/25">
                    produces: {template.outputs.slice(0, 2).join(" · ")}
                  </p>
                </button>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
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
        <div key={i} className="h-36 rounded-xl bg-white/[0.04]" />
      ))}
    </div>
  );
}

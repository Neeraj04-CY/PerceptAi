"use client";

/** Workflow editor: instruction + variables + policy + schedule, with
 * explicit draft → publish semantics. Running renders the variables and
 * hands the instruction to the Run page — same execution path as any run. */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Activity, ArrowLeft, CalendarClock, Play, Plus, Trash2, UploadCloud } from "lucide-react";
import { cn, isAbortError } from "@/lib/utils";
import {
  ApiRunner,
  ApiWorkflow,
  ApiWorkflowHealth,
  ApiWorkflowRun,
  ApiWorkflowSchedule,
  ApiWorkflowVariable,
  getRunners,
  getWorkflow,
  getWorkflowRuns,
  publishWorkflow,
  renderWorkflow,
  updateWorkflow,
} from "@/lib/api";

const SLOT = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g;

const INTERVALS = [
  { label: "hourly", minutes: 60 },
  { label: "every 6h", minutes: 360 },
  { label: "daily", minutes: 1440 },
  { label: "weekly", minutes: 10080 },
];

export default function WorkflowEditorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [workflow, setWorkflow] = useState<ApiWorkflow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [runOpen, setRunOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getWorkflow(params.id, controller.signal)
      .then(setWorkflow)
      .catch((e) => {
        if (isAbortError(e)) return;
        if (String(e).includes("Unauthorized")) router.replace("/signin");
        else setError(e instanceof Error ? e.message : "Failed to load workflow");
      });
    return () => controller.abort();
  }, [params.id, router]);

  const patch = useCallback((changes: Partial<ApiWorkflow>) => {
    setWorkflow((w) => (w ? { ...w, ...changes } : w));
    setDirty(true);
  }, []);

  const declared = useMemo(
    () => new Set((workflow?.variables ?? []).map((v) => v.name)),
    [workflow?.variables],
  );
  const undeclared = useMemo(() => {
    const found = new Set<string>();
    for (const match of (workflow?.instruction ?? "").matchAll(SLOT)) {
      if (!declared.has(match[1])) found.add(match[1]);
    }
    return Array.from(found);
  }, [workflow?.instruction, declared]);

  const save = async (): Promise<boolean> => {
    if (!workflow) return false;
    setSaving(true);
    setError(null);
    try {
      await updateWorkflow(workflow.id, {
        name: workflow.name,
        description: workflow.description,
        instruction: workflow.instruction,
        variables: workflow.variables,
        mode: workflow.mode,
        schedule: workflow.schedule ?? undefined,
      });
      setDirty(false);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      return false;
    } finally {
      setSaving(false);
    }
  };

  const publish = async () => {
    if (!workflow) return;
    if (dirty && !(await save())) return;
    setPublishing(true);
    setError(null);
    try {
      const result = await publishWorkflow(workflow.id);
      setWorkflow((w) => (w ? { ...w, version: result.version, status: "published" } : w));
      setNotice(`Published v${result.version}`);
      setTimeout(() => setNotice(null), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPublishing(false);
    }
  };

  if (error && !workflow) {
    return (
      <div className="rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
        {error}
      </div>
    );
  }
  if (!workflow) {
    return <div className="h-96 rounded-xl bg-white/[0.04] animate-pulse" />;
  }

  return (
    <div className="space-y-4">
      {/* header */}
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/dashboard/studio"
              className="rounded-md p-1.5 text-white/40 hover:text-white hover:bg-white/[0.04] transition-colors">
          <ArrowLeft size={15} />
        </Link>
        <input
          value={workflow.name}
          onChange={(e) => patch({ name: e.target.value })}
          className="min-w-0 flex-1 bg-transparent text-[16px] font-medium text-white focus:outline-none border-b border-transparent focus:border-white/15 pb-0.5"
          placeholder="Workflow name"
          aria-label="Workflow name"
        />
        <span className={cn("rounded border px-2 py-[2px] font-mono text-[9px] uppercase tracking-wider",
                            workflow.status === "published"
                              ? "border-accent/25 text-accent/85" : "border-white/15 text-white/40")}>
          {workflow.status === "published" ? `published · v${workflow.version}` : workflow.status}
        </span>
        <div className="flex items-center gap-2">
          <button onClick={save} disabled={!dirty || saving}
                  className={cn("h-8 rounded-md px-3 font-mono text-[11px] uppercase tracking-wider transition-colors",
                                dirty ? "bg-white/[0.06] text-white hover:bg-white/[0.1]"
                                      : "bg-white/[0.02] text-white/30")}>
            {saving ? "Saving…" : dirty ? "Save draft" : "Saved"}
          </button>
          <button onClick={publish} disabled={publishing}
                  className="inline-flex h-8 items-center gap-1.5 rounded-md bg-white/[0.06] px-3 font-mono text-[11px] uppercase tracking-wider text-white hover:bg-white/[0.1] transition-colors disabled:opacity-50">
            <UploadCloud size={12} /> {publishing ? "Publishing…" : "Publish"}
          </button>
          <button onClick={() => setRunOpen(true)}
                  className="inline-flex h-8 items-center gap-1.5 rounded-full bg-accent px-4 text-[12px] font-medium text-black hover:shadow-[0_0_28px_-8px_rgba(0,255,133,0.6)] transition-shadow">
            <Play size={12} strokeWidth={2.6} fill="currentColor" /> Run
          </button>
        </div>
      </div>

      {notice && (
        <div className="rounded-lg border border-accent/25 bg-accent/[0.05] px-3 py-2 font-mono text-[11px] text-accent">
          {notice}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-400/20 bg-red-400/[0.04] px-3 py-2 text-[12px] text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1.6fr_1fr] gap-4 items-start">
        {/* left: definition */}
        <div className="space-y-4">
          <section className="glass rounded-xl p-4">
            <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
              Instruction — use {"{{variable}}"} slots
            </label>
            <textarea
              value={workflow.instruction}
              onChange={(e) => patch({ instruction: e.target.value })}
              rows={5}
              className="w-full resize-y rounded-lg border border-white/[0.07] bg-black/30 p-3 font-mono text-[13px] leading-relaxed text-white/90 focus:outline-none focus:border-accent/35"
              placeholder="Open {{app_name}} and …"
            />
            {undeclared.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="font-mono text-[10px] text-amber-300/90">
                  undeclared: {undeclared.join(", ")}
                </span>
                <button
                  onClick={() => patch({
                    variables: [
                      ...(workflow.variables || []),
                      ...undeclared.map((name) => ({ name, label: name, type: "text", default: "", required: true })),
                    ],
                  })}
                  className="rounded border border-amber-300/25 px-2 py-[2px] font-mono text-[10px] uppercase tracking-wider text-amber-300 hover:bg-amber-300/10"
                >
                  declare
                </button>
              </div>
            )}
            <textarea
              value={workflow.description}
              onChange={(e) => patch({ description: e.target.value })}
              rows={2}
              className="mt-3 w-full resize-none rounded-lg border border-white/[0.05] bg-transparent p-3 text-[12px] text-white/60 focus:outline-none focus:border-white/15"
              placeholder="What this workflow is for (shown in the library)…"
            />
          </section>

          <VariablesEditor
            variables={workflow.variables || []}
            onChange={(variables) => patch({ variables })}
          />
        </div>

        {/* right: execution config */}
        <div className="space-y-4">
          <section className="glass rounded-xl p-4">
            <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
              Execution
            </h2>
            <div className="flex items-center gap-1 rounded-lg border border-white/[0.07] bg-white/[0.02] p-1 w-fit">
              {(["task", "mission"] as const).map((m) => (
                <button key={m} onClick={() => patch({ mode: m })}
                        className={cn("rounded-md px-3 h-7 font-mono text-[11px] uppercase tracking-[0.14em] transition-colors",
                                      workflow.mode === m ? "bg-accent/15 text-accent" : "text-white/45 hover:text-white")}>
                  {m}
                </button>
              ))}
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-white/35">
              {workflow.mode === "task"
                ? "One agent session with live reasoning — best for a single application outcome."
                : "The executive decomposes across specialists and returns one evidence-grounded report."}
            </p>
          </section>

          <section className="glass rounded-xl p-4">
            <h2 className="mb-2 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
              <CalendarClock size={12} /> Schedule
            </h2>
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={workflow.schedule?.enabled ?? false}
                onChange={(e) => patch({
                  schedule: {
                    ...(workflow.schedule || { interval_minutes: 1440 }),
                    enabled: e.target.checked,
                    next_run_at: e.target.checked ? new Date().toISOString() : undefined,
                  },
                })}
                className="h-3.5 w-3.5 accent-[#00ff85]"
              />
              <span className="text-[12px] text-white/70">Run on a schedule</span>
            </label>
            {workflow.schedule?.enabled && (
              <>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {INTERVALS.map((interval) => (
                    <button key={interval.minutes}
                            onClick={() => patch({
                              schedule: { ...workflow.schedule, enabled: true, interval_minutes: interval.minutes },
                            })}
                            className={cn("rounded-full border px-3 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors",
                                          (workflow.schedule?.interval_minutes ?? 1440) === interval.minutes
                                            ? "border-accent/35 text-accent bg-accent/[0.07]"
                                            : "border-white/10 text-white/40 hover:text-white")}>
                      {interval.label}
                    </button>
                  ))}
                </div>
                <ScheduleTargetPicker
                  schedule={workflow.schedule}
                  onChange={(schedule) => patch({ schedule })}
                />
                <OnFailureEditor
                  schedule={workflow.schedule}
                  onChange={(schedule) => patch({ schedule })}
                />
              </>
            )}
            <p className="mt-2.5 text-[10px] leading-relaxed text-white/30">
              Scheduled runs use variable defaults and reach you only through
              the Attention inbox (and the workspace webhook, if set). “This
              machine” runs on the API host and requires ENABLE_SCHEDULER
              there. Mission workflows run on demand only.
            </p>
          </section>

          <RunHistory workflowId={workflow.id} />

          {(workflow.versions?.length ?? 0) > 0 && (
            <section className="glass rounded-xl p-4">
              <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
                Versions
              </h2>
              <div className="space-y-1">
                {workflow.versions!.map((version) => (
                  <div key={version.version} className="flex items-center justify-between text-[11px]">
                    <span className="font-mono text-white/60">v{version.version}</span>
                    <span className="font-mono text-[10px] text-white/30">
                      {new Date(version.published_at).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>

      {runOpen && (
        <RunModal
          workflow={workflow}
          dirty={dirty}
          onSave={save}
          onClose={() => setRunOpen(false)}
        />
      )}
    </div>
  );
}

/* ------------------------------------------- unattended operations config */

function ScheduleTargetPicker({ schedule, onChange }: {
  schedule: ApiWorkflowSchedule;
  onChange: (s: ApiWorkflowSchedule) => void;
}) {
  const [runners, setRunners] = useState<ApiRunner[] | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    getRunners(controller.signal).then(setRunners).catch(() => setRunners([]));
    return () => controller.abort();
  }, []);

  const kind = schedule.target?.kind ?? "this_machine";
  const setTarget = (target: ApiWorkflowSchedule["target"]) =>
    onChange({ ...schedule, target });

  return (
    <div className="mt-3.5">
      <span className="mb-1.5 block font-mono text-[9px] uppercase tracking-[0.18em] text-white/30">
        Runs on
      </span>
      <div className="flex flex-wrap gap-1.5">
        <Chip active={kind === "any_available"}
              onClick={() => setTarget({ kind: "any_available" })}>
          any available runner
        </Chip>
        <Chip active={kind === "runner"}
              onClick={() => setTarget({ kind: "runner", runner_id: schedule.target?.runner_id ?? runners?.[0]?.id })}>
          a specific runner
        </Chip>
        <Chip active={kind === "this_machine"}
              onClick={() => setTarget({ kind: "this_machine" })}>
          this machine
        </Chip>
      </div>
      {kind === "runner" && (
        <select
          value={schedule.target?.runner_id ?? ""}
          onChange={(e) => setTarget({ kind: "runner", runner_id: e.target.value })}
          className="mt-2 h-8 w-full rounded-md border border-white/[0.08] bg-black/40 px-2 font-mono text-[11px] text-white/80 focus:outline-none focus:border-accent/35"
          aria-label="Pinned runner"
        >
          <option value="" disabled>{runners === null ? "Loading runners…" : runners.length === 0 ? "No runners registered" : "Choose a runner"}</option>
          {(runners ?? []).map((r) => (
            <option key={r.id} value={r.id}>
              {r.name} — {r.status}
            </option>
          ))}
        </select>
      )}
      {kind === "any_available" && runners !== null &&
        !runners.some((r) => r.status !== "offline") && (
        <p className="mt-1.5 font-mono text-[10px] text-amber-300/80">
          no runner is online right now — runs will wait in the queue
        </p>
      )}
    </div>
  );
}

function OnFailureEditor({ schedule, onChange }: {
  schedule: ApiWorkflowSchedule;
  onChange: (s: ApiWorkflowSchedule) => void;
}) {
  const retries = schedule.on_failure?.retries ?? 0;
  const notify = schedule.on_failure?.notify ?? true;
  const set = (patch: Partial<NonNullable<ApiWorkflowSchedule["on_failure"]>>) =>
    onChange({ ...schedule, on_failure: { retries, notify, ...patch } });

  return (
    <div className="mt-3.5">
      <span className="mb-1.5 block font-mono text-[9px] uppercase tracking-[0.18em] text-white/30">
        If a run fails
      </span>
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-[10px] text-white/40">retry</span>
        {[0, 1, 2, 3].map((n) => (
          <Chip key={n} active={retries === n} onClick={() => set({ retries: n })}>
            {n === 0 ? "never" : `${n}×`}
          </Chip>
        ))}
      </div>
      <label className="mt-2 flex items-center gap-2 cursor-pointer">
        <input type="checkbox" checked={notify}
               onChange={(e) => set({ notify: e.target.checked })}
               className="h-3.5 w-3.5 accent-[#00ff85]" />
        <span className="text-[11px] text-white/55">
          Notify when it finally fails (Attention inbox + workspace webhook)
        </span>
      </label>
    </div>
  );
}

function Chip({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button onClick={onClick}
            className={cn("rounded-full border px-3 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors",
                          active ? "border-accent/35 text-accent bg-accent/[0.07]"
                                 : "border-white/10 text-white/40 hover:text-white")}>
      {children}
    </button>
  );
}

/* -------------------------------------------------------- run history */

function RunHistory({ workflowId }: { workflowId: string }) {
  const [runs, setRuns] = useState<ApiWorkflowRun[] | null>(null);
  const [health, setHealth] = useState<ApiWorkflowHealth | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getWorkflowRuns(workflowId, 20, controller.signal)
      .then((r) => { setRuns(r.runs); setHealth(r.health); })
      .catch((e) => { if (!isAbortError(e)) setUnavailable(true); });
    return () => controller.abort();
  }, [workflowId]);

  if (unavailable || runs === null) return null; // silent until it has facts
  if (runs.length === 0) return null;            // no history yet — nothing to say

  const statusTone: Record<string, string> = {
    completed: "bg-accent", failed: "bg-red-400", unverified: "bg-amber-300",
    running: "bg-sky-300", queued: "bg-white/40", claimed: "bg-white/40",
  };

  return (
    <section className="glass rounded-xl p-4" data-testid="workflow-health">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
          <Activity size={12} /> Runs
        </h2>
        {health && health.total > 0 && (
          <span className={cn("font-mono text-[11px] tabular-nums",
                              (health.success_rate ?? 0) >= 0.9 ? "text-accent"
                                : (health.success_rate ?? 0) >= 0.6 ? "text-amber-300" : "text-red-300")}>
            {Math.round((health.success_rate ?? 0) * 100)}% success · {health.total} runs
          </span>
        )}
      </div>
      <div className="space-y-1">
        {runs.slice(0, 8).map((run) => (
          <Link key={run.id} href={`/dashboard/sessions/${run.id}`}
                className="flex items-center gap-2 rounded-md px-1.5 py-1 hover:bg-white/[0.03] transition-colors">
            <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", statusTone[run.status] ?? "bg-white/40")} />
            <span className="font-mono text-[11px] text-white/60">{run.status}</span>
            {run.retry_of && (
              <span className="rounded border border-white/15 px-1 font-mono text-[9px] uppercase tracking-wider text-white/40">
                retry {run.retry_count ?? ""}
              </span>
            )}
            {run.origin === "schedule" && !run.retry_of && (
              <span className="rounded border border-white/15 px-1 font-mono text-[9px] uppercase tracking-wider text-white/40">
                scheduled
              </span>
            )}
            <span className="ml-auto font-mono text-[10px] text-white/30 tabular-nums shrink-0">
              {new Date(run.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}

/* ---------------------------------------------------------- variables */

function VariablesEditor({ variables, onChange }: {
  variables: ApiWorkflowVariable[];
  onChange: (v: ApiWorkflowVariable[]) => void;
}) {
  const update = (i: number, changes: Partial<ApiWorkflowVariable>) =>
    onChange(variables.map((v, j) => (j === i ? { ...v, ...changes } : v)));
  return (
    <section className="glass rounded-xl p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">Variables</h2>
        <button
          onClick={() => onChange([...variables, { name: `var_${variables.length + 1}`, label: "", type: "text", default: "", required: false }])}
          className="inline-flex items-center gap-1 rounded-md px-2 h-6 font-mono text-[10px] uppercase tracking-wider text-white/40 hover:text-accent hover:bg-white/[0.03] transition-colors">
          <Plus size={11} /> Add
        </button>
      </div>
      {variables.length === 0 ? (
        <p className="text-[12px] text-white/35">
          No variables — add {"{{slots}}"} to the instruction to parametrize it.
        </p>
      ) : (
        <div className="space-y-2">
          <div className="grid grid-cols-[1fr_1fr_1fr_auto_auto] gap-2 px-1 font-mono text-[9px] uppercase tracking-wider text-white/25">
            <span>name</span><span>label</span><span>default</span><span>req</span><span />
          </div>
          {variables.map((variable, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto_auto] items-center gap-2">
              <input value={variable.name}
                     onChange={(e) => update(i, { name: e.target.value.replace(/[^a-zA-Z0-9_]/g, "_") })}
                     className="h-8 rounded-md border border-white/[0.07] bg-black/30 px-2 font-mono text-[12px] text-accent/90 focus:outline-none focus:border-accent/35"
                     aria-label={`Variable ${i + 1} name`} />
              <input value={variable.label || ""}
                     onChange={(e) => update(i, { label: e.target.value })}
                     placeholder={variable.name}
                     className="h-8 rounded-md border border-white/[0.07] bg-transparent px-2 text-[12px] text-white/75 focus:outline-none focus:border-white/20"
                     aria-label={`Variable ${i + 1} label`} />
              <input value={variable.default || ""}
                     onChange={(e) => update(i, { default: e.target.value })}
                     placeholder="—"
                     className="h-8 rounded-md border border-white/[0.07] bg-transparent px-2 text-[12px] text-white/75 focus:outline-none focus:border-white/20"
                     aria-label={`Variable ${i + 1} default`} />
              <input type="checkbox" checked={variable.required ?? false}
                     onChange={(e) => update(i, { required: e.target.checked })}
                     className="h-3.5 w-3.5 accent-[#00ff85]"
                     aria-label={`Variable ${i + 1} required`} />
              <button onClick={() => onChange(variables.filter((_, j) => j !== i))}
                      className="rounded-md p-1.5 text-white/25 hover:text-red-300 hover:bg-red-400/10 transition-colors"
                      aria-label={`Remove variable ${i + 1}`}>
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/* --------------------------------------------------------------- run */

function RunModal({ workflow, dirty, onSave, onClose }: {
  workflow: ApiWorkflow;
  dirty: boolean;
  onSave: () => Promise<boolean>;
  onClose: () => void;
}) {
  const router = useRouter();
  const [values, setValues] = useState<Record<string, string>>(
    () => Object.fromEntries((workflow.variables || []).map((v) => [v.name, v.default || ""])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      if (dirty && !(await onSave())) throw new Error("Save failed");
      const rendered = await renderWorkflow(workflow.id, values);
      window.localStorage.setItem("perceptai_pending_run", JSON.stringify({
        instruction: rendered.instruction,
        mode: rendered.mode,
      }));
      router.push("/dashboard/run");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not prepare the run");
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
         role="dialog" aria-modal="true" aria-label={`Run ${workflow.name}`}
         onClick={onClose}>
      <div className="glass-strong w-full max-w-md rounded-xl p-5"
           onClick={(e) => e.stopPropagation()}>
        <h2 className="text-[14px] font-medium text-white">Run “{workflow.name}”</h2>
        <p className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-white/35">
          {workflow.mode} · fills the Run page with the rendered instruction
        </p>
        <div className="mt-4 space-y-3">
          {(workflow.variables || []).length === 0 && (
            <p className="text-[12px] text-white/45">No variables to fill.</p>
          )}
          {(workflow.variables || []).map((variable) => (
            <div key={variable.name}>
              <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-white/40">
                {variable.label || variable.name}
                {variable.required && <span className="text-accent"> *</span>}
              </label>
              <input
                value={values[variable.name] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [variable.name]: e.target.value }))}
                placeholder={variable.description || variable.default || ""}
                className="h-9 w-full rounded-md border border-white/[0.08] bg-black/30 px-3 text-[13px] text-white focus:outline-none focus:border-accent/35"
              />
            </div>
          ))}
        </div>
        {error && <p className="mt-3 text-[12px] text-red-300">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose}
                  className="h-8 rounded-md px-3 font-mono text-[11px] uppercase tracking-wider text-white/45 hover:text-white hover:bg-white/[0.04] transition-colors">
            Cancel
          </button>
          <button onClick={run} disabled={busy}
                  className="inline-flex h-8 items-center gap-1.5 rounded-full bg-accent px-4 text-[12px] font-medium text-black disabled:opacity-50">
            <Play size={12} strokeWidth={2.6} fill="currentColor" />
            {busy ? "Preparing…" : "Continue to Run"}
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion } from "framer-motion";
import { TaskInput } from "@/components/dashboard/run/task-input";
import { ExecutionTimeline } from "@/components/dashboard/run/execution-timeline";
import { TerminalLogs } from "@/components/dashboard/run/terminal-logs";
import { ScreenPreview } from "@/components/dashboard/run/screen-preview";
import { SessionInfo, type SessionMeta } from "@/components/dashboard/run/session-info";
import { WorldModelPanel, type WorldSnapshot } from "@/components/dashboard/run/world-model";
import {
  ReasoningPanel,
  applyReasoningEvent,
  emptyReasoning,
  type ReasoningStream,
} from "@/components/dashboard/run/reasoning-panel";
import { MissionLive, type MissionWireEvent } from "@/components/dashboard/run/mission-live";
import { type TimelineStep, type LogLine } from "@/components/dashboard/run/mock-data";
import { streamPost } from "@/lib/stream";
import { cn } from "@/lib/utils";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const API_V1 = `${API_BASE}/api/v1`;

type ApiKeyCreateResponse = {
  id: string;
  key_prefix: string;
  name: string;
  full_key: string;
};

type RunMode = "task" | "mission";

export default function RunTaskPage() {
  const [mode, setMode] = useState<RunMode>("task");
  const [steps, setSteps] = useState<TimelineStep[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [worlds, setWorlds] = useState<WorldSnapshot[]>([]);
  const [reasoning, setReasoning] = useState<ReasoningStream>(emptyReasoning());
  const [missionEvents, setMissionEvents] = useState<MissionWireEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [meta, setMeta] = useState<SessionMeta>(makeInitialMeta());
  const [initialTask, setInitialTask] = useState<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);
  const runStartRef = useRef<number | null>(null);

  // Handoff from Studio: a rendered workflow lands here prefilled.
  useEffect(() => {
    const raw = window.localStorage.getItem("perceptai_pending_run");
    if (!raw) return;
    window.localStorage.removeItem("perceptai_pending_run");
    try {
      const pending = JSON.parse(raw) as { instruction?: string; mode?: RunMode };
      if (pending.instruction) setInitialTask(pending.instruction);
      if (pending.mode === "mission" || pending.mode === "task") setMode(pending.mode);
    } catch {
      // ignore malformed handoff
    }
  }, []);

  const resetState = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setSteps([]);
    setActiveIndex(-1);
    setLogs([]);
    setWorlds([]);
    setReasoning(emptyReasoning());
    setMissionEvents([]);
  }, []);

  const prepareRun = useCallback(async (): Promise<string | null> => {
    resetState();
    runStartRef.current = Date.now();
    setRunning(true);
    setMeta({ ...makeInitialMeta(), id: "connecting...", status: "running", startedAt: formatTime(new Date()) });

    const token = getToken();
    if (!token) {
      setRunning(false);
      setLogs([{ ts: formatTime(new Date()), level: "err", msg: "Missing auth token. Please sign in." }]);
      setMeta((m) => ({ ...m, status: "failed" }));
      return null;
    }
    try {
      const apiKey = await ensureApiKey(token);
      setMeta((m) => ({ ...m, apiKey: maskKey(apiKey) }));
      return apiKey;
    } catch (err) {
      setRunning(false);
      setLogs([{ ts: "—", level: "err", msg: err instanceof Error ? err.message : "API key creation failed" }]);
      setMeta((m) => ({ ...m, status: "failed" }));
      return null;
    }
  }, [resetState]);

  const runMission = useCallback(async (instruction: string) => {
    const apiKey = await prepareRun();
    if (!apiKey) return;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamPost("/missions/stream", { instruction }, apiKey, (event) => {
        if (event.type === "mission_id") {
          setMeta((m) => ({ ...m, id: String(event.mission_id) }));
          return;
        }
        setMissionEvents((prev) => [...prev, event as MissionWireEvent]);
        if (event.type === "mission_completed") {
          const status = String((event.data as Record<string, unknown> | undefined)?.status || "completed");
          setRunning(false);
          setMeta((m) => ({
            ...m,
            status: status === "failed" ? "failed" : "completed",
          }));
        }
      }, controller.signal);
      setRunning(false);
    } catch (err) {
      setRunning(false);
      setMissionEvents((prev) => [...prev, {
        type: "error",
        message: err instanceof Error ? err.message : "Connection failed",
      }]);
      setMeta((m) => ({ ...m, status: "failed" }));
    }
  }, [prepareRun]);

  const runTask = useCallback(async (task: string) => {
    const apiKey = await prepareRun();
    if (!apiKey) return;

    setLogs([{ ts: formatTime(new Date()), level: "info", msg: "Connecting to PerceptAI runtime..." }]);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamPost("/execute/stream", { instruction: task }, apiKey, (event: any) => {
        switch (event.type) {
          case "session_id":
            setMeta((m) => ({ ...m, id: event.session_id }));
            break;

          case "session_start":
            setLogs((prev) => [...prev, {
              ts: formatTime(new Date()),
              level: "info",
              msg: `Task: "${event.instruction}"`,
            }]);
            break;

          case "plan":
            setSteps(event.steps.map((s: any, i: number) => ({
              id: `step-${i}`,
              action: prettifyAction(s.action),
              description: s.description,
              duration: "—",
              status: "pending" as const,
              tag: actionTag(s.action),
            })));
            setMeta((m) => ({ ...m, stepsTotal: event.steps.length }));
            setLogs((prev) => [...prev, {
              ts: formatTime(new Date()),
              level: "info",
              msg: `Planning ${event.steps.length} steps...`,
            }]);
            break;

          case "step_start":
            setSteps((prev) => prev.map((s, i) =>
              i === event.step_number - 1 ? { ...s, status: "running" as const } : s
            ));
            setActiveIndex(event.step_number - 1);
            setLogs((prev) => [...prev, {
              ts: formatTime(new Date()),
              level: "info",
              msg: `Executing: ${event.description} [${event.action}]`,
            }]);
            break;

          case "step_complete":
            setSteps((prev) => {
              const updated = [...prev];
              const idx = event.step.step_number - 1;
              if (updated[idx]) {
                updated[idx] = {
                  ...updated[idx],
                  status: event.step.status as any,
                  duration: `${event.step.duration}s`,
                };
              } else {
                updated.push({
                  id: `step-${idx}`,
                  action: prettifyAction(event.step.action),
                  description: event.step.description,
                  duration: `${event.step.duration}s`,
                  status: event.step.status as any,
                  tag: actionTag(event.step.action),
                });
              }
              return updated;
            });
            setMeta((m) => ({ ...m, stepsCompleted: m.stepsCompleted + 1 }));
            setLogs((prev) => {
              const next: LogLine[] = [...prev, {
                ts: formatTime(new Date()),
                level: event.step.status === "completed" ? "ok" : "err",
                msg: `${event.step.status === "completed" ? "✓" : "✗"} ${event.step.description}`,
              }];
              if (event.step.result?.extracted) {
                next.push({
                  ts: formatTime(new Date()),
                  level: "ok",
                  msg: `Extracted: ${String(event.step.result.extracted).slice(0, 100)}`,
                });
              }
              return next;
            });
            break;

          case "replan":
            setLogs((prev) => [...prev, {
              ts: formatTime(new Date()), level: "info", msg: `↻ ${event.message}`,
            }]);
            break;

          case "world":
            setWorlds((prev) => [
              ...prev.slice(-63),
              { ...(event as WorldSnapshot), receivedAt: Date.now() },
            ]);
            break;

          case "reasoning":
            setReasoning((prev) => applyReasoningEvent(prev, event));
            break;

          case "log":
            setLogs((prev) => [...prev, {
              ts: formatTime(new Date()), level: "info", msg: event.message,
            }]);
            break;

          case "complete":
            setRunning(false);
            setMeta((m) => ({
              ...m,
              status: event.status === "completed" ? "completed" : "failed",
              duration: `${event.execution_time}s`,
              stepsTotal: event.total_steps,
            }));
            setLogs((prev) => {
              const next = [...prev, {
                ts: formatTime(new Date()),
                level: "ok" as const,
                msg: `━━ ${event.status} · ${event.execution_time}s · ${event.total_steps} steps ━━`,
              }];
              if (event.summary) {
                next.push({
                  ts: formatTime(new Date()),
                  level: "ok" as const,
                  msg: `Result: ${event.summary}`,
                });
              }
              return next;
            });
            break;

          case "error":
            setRunning(false);
            setLogs((prev) => [...prev, {
              ts: formatTime(new Date()), level: "err", msg: event.message,
            }]);
            setMeta((m) => ({ ...m, status: "failed" }));
            break;
        }
      }, controller.signal);
      setRunning(false);
    } catch (err) {
      setRunning(false);
      setLogs((prev) => [...prev, {
        ts: "—", level: "err", msg: err instanceof Error ? err.message : "Connection failed",
      }]);
      setMeta((m) => ({ ...m, status: "failed" }));
    }
  }, [prepareRun]);

  const handleRun = useCallback((instruction: string) => {
    if (mode === "mission") void runMission(instruction);
    else void runTask(instruction);
  }, [mode, runMission, runTask]);

  const handleStop = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setRunning(false);
    setMeta((m) => ({ ...m, status: "failed" }));
    setSteps((prev) =>
      prev.map((s) => (s.status === "running" ? { ...s, status: "failed" } : s))
    );
    setLogs((prev) => [...prev, { ts: "—", level: "err", msg: "run aborted by user" }]);
  };

  // Live duration ticker
  useEffect(() => {
    if (!running) return;
    const start = runStartRef.current || Date.now();
    const id = setInterval(() => {
      setMeta((m) => ({
        ...m,
        duration: ((Date.now() - start) / 1000).toFixed(1) + "s",
      }));
    }, 100);
    return () => clearInterval(id);
  }, [running]);

  const timelineVisible = steps.length > 0;
  const activeStep = activeIndex >= 0 ? steps[activeIndex] : undefined;
  const missionVisible = mode === "mission" && (missionEvents.length > 0 || running);

  return (
    <div className="space-y-5">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="space-y-3"
      >
        {/* mode switch: a task is one runtime session; a mission fans out to specialists */}
        <div className="flex items-center gap-1 rounded-lg border border-white/[0.07] bg-white/[0.02] p-1 w-fit"
             role="tablist" aria-label="Run mode">
          {(["task", "mission"] as const).map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              disabled={running}
              onClick={() => setMode(m)}
              className={cn(
                "rounded-md px-3 h-7 font-mono text-[11px] uppercase tracking-[0.14em] transition-colors",
                mode === m ? "bg-accent/15 text-accent" : "text-white/45 hover:text-white",
                running && "opacity-50 cursor-not-allowed",
              )}
            >
              {m}
            </button>
          ))}
          <span className="px-2 text-[11px] text-white/30 hidden sm:inline">
            {mode === "task"
              ? "one agent, one screen, live reasoning"
              : "executive + specialists, evidence graph, grounded report"}
          </span>
        </div>
        <TaskInput running={running} onRun={handleRun} onStop={handleStop}
                   apiKeyValue={meta.apiKey} initialTask={initialTask} />
      </motion.div>

      {missionVisible ? (
        <MissionLive events={missionEvents} running={running} />
      ) : (
        <>
          <ExecutionTimeline steps={steps} activeIndex={activeIndex} visible={timelineVisible} />
          <ReasoningPanel stream={reasoning} />
          <WorldModelPanel snapshots={worlds} />
        </>
      )}

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.15 }}
        className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr_0.9fr] gap-4"
      >
        <TerminalLogs logs={logs} running={running && mode === "task"} />
        <ScreenPreview
          active={running && mode === "task"}
          stepLabel={activeStep?.action}
          timestamp={running ? "live · " + meta.duration : undefined}
        />
        <SessionInfo meta={meta} />
      </motion.div>
    </div>
  );
}

function makeInitialMeta(): SessionMeta {
  return {
    id: "run_idle",
    status: "queued",
    duration: "—",
    stepsTotal: 0,
    stepsCompleted: 0,
    apiKey: "—",
    plan: "local runtime",
    region: "this machine",
    startedAt: "—",
  };
}

function formatTime(d: Date) {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

async function ensureApiKey(token: string): Promise<string> {
  if (typeof window === "undefined") return "";
  const cached = window.localStorage.getItem("perceptai_api_key");
  if (cached) return cached;

  const res = await fetch(`${API_V1}/keys`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ name: "Dashboard run key" }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Key create failed (${res.status})`);
  }

  const data = (await res.json()) as ApiKeyCreateResponse;
  window.localStorage.setItem("perceptai_api_key", data.full_key);
  return data.full_key;
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("perceptai_token");
}

function maskKey(key: string) {
  if (!key) return "sk_••••";
  return `${key.slice(0, 8)}••••${key.slice(-4)}`;
}

function actionTag(action: string) {
  const normalized = action.toLowerCase();
  if (normalized.includes("open")) return "APP";
  if (normalized.includes("navigate")) return "NAV";
  if (normalized.includes("click") || normalized.includes("type") || normalized.includes("press")) return "ACTION";
  if (normalized.includes("wait")) return "WAIT";
  return "RUN";
}

function prettifyAction(action: string) {
  return action
    .replace(/_/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

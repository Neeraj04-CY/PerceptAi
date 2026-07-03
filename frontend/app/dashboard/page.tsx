"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion } from "framer-motion";
import { TaskInput } from "@/components/dashboard/run/task-input";
import { ExecutionTimeline } from "@/components/dashboard/run/execution-timeline";
import { TerminalLogs } from "@/components/dashboard/run/terminal-logs";
import { ScreenPreview } from "@/components/dashboard/run/screen-preview";
import { SessionInfo, type SessionMeta } from "@/components/dashboard/run/session-info";
import { type TimelineStep, type LogLine } from "@/components/dashboard/run/mock-data";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const API_V1 = `${API_BASE}/api/v1`;

type ApiExecuteStep = {
  step_number: number;
  description: string;
  action: string;
  status: "completed" | "failed" | "running" | "pending";
  duration?: number;
  timestamp?: string;
  result?: { success?: boolean; [key: string]: unknown } | null;
};

type ApiExecuteResponse = {
  session_id: string;
  status: "completed" | "failed" | "running";
  instruction: string;
  steps: ApiExecuteStep[];
  execution_time?: number | null;
  error?: string | null;
  created_at: string;
};

type UiStep = TimelineStep & { label: string; actionCode: string; timestamp?: string };

type ApiKeyCreateResponse = {
  id: string;
  key_prefix: string;
  name: string;
  full_key: string;
};

export default function RunTaskPage() {
  const [steps, setSteps] = useState<TimelineStep[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [running, setRunning] = useState(false);
  const [meta, setMeta] = useState<SessionMeta>(makeInitialMeta());
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const runStartRef = useRef<number | null>(null);

  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };

  const resetState = () => {
    clearTimers();
    abortRef.current?.abort();
    abortRef.current = null;
    setSteps([]);
    setActiveIndex(-1);
    setLogs([]);
  };

  const handleRun = useCallback(async (task: string) => {
    resetState();
    const startedAt = new Date();
    runStartRef.current = Date.now();
    setRunning(true);
    setSteps([]);
    setActiveIndex(-1);
    setLogs([]);
    setMeta({
      id: "connecting...",
      status: "running",
      duration: "0.0s",
      stepsTotal: 0,
      stepsCompleted: 0,
      apiKey: "—",
      plan: "FREE",
      region: "railway · global",
      startedAt: formatTime(startedAt),
    });

    const token = getToken();
    if (!token) {
      setRunning(false);
      setLogs([{
        ts: formatTime(new Date()),
        level: "err",
        msg: "Missing auth token. Please sign in.",
      }]);
      setMeta((m) => ({ ...m, status: "failed" }));
      return;
    }

    let apiKey = "";
    try {
      apiKey = await ensureApiKey(token);
    } catch (err) {
      const message = err instanceof Error ? err.message : "API key creation failed";
      setRunning(false);
      setLogs([{ ts: "—", level: "err", msg: message }]);
      setMeta((m) => ({ ...m, status: "failed" }));
      return;
    }

    setMeta((m) => ({ ...m, apiKey: maskKey(apiKey) }));
    setLogs([{
      ts: formatTime(new Date()),
      level: "info",
      msg: "Connecting to PerceptAI runtime...",
    }]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(`${API_V1}/execute/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey,
        },
        body: JSON.stringify({ instruction: task }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("No response stream available");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let plannedSteps: TimelineStep[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          let event: any;
          try {
            event = JSON.parse(raw);
          } catch {
            continue;
          }

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
              plannedSteps = event.steps.map((s: any, i: number) => ({
                id: `step-${i}`,
                action: prettifyAction(s.action),
                description: s.description,
                duration: "—",
                status: "pending" as const,
                tag: actionTag(s.action),
              }));
              setSteps(plannedSteps);
              setMeta((m) => ({ ...m, stepsTotal: event.steps.length }));
              setLogs((prev) => [...prev, {
                ts: formatTime(new Date()),
                level: "info",
                msg: `Planning ${event.steps.length} steps...`,
              }]);
              break;

            case "step_start":
              setSteps((prev) => prev.map((s, i) =>
                i === event.step_number - 1
                  ? { ...s, status: "running" as const }
                  : s
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
              setMeta((m) => ({
                ...m,
                stepsCompleted: m.stepsCompleted + 1,
              }));
              setLogs((prev) => [...prev, {
                ts: formatTime(new Date()),
                level: event.step.status === "completed" ? "ok" : "err",
                msg: `${event.step.status === "completed" ? "✓" : "✗"} ${event.step.description}`,
              }]);

              if (event.step.result?.extracted) {
                setLogs((prev) => [...prev, {
                  ts: formatTime(new Date()),
                  level: "ok",
                  msg: `Extracted: ${String(event.step.result.extracted).slice(0, 100)}`,
                }]);
              }
              break;

            case "replan":
              setLogs((prev) => [...prev, {
                ts: formatTime(new Date()),
                level: "info",
                msg: `↻ ${event.message}`,
              }]);
              break;

            case "log":
              setLogs((prev) => [...prev, {
                ts: formatTime(new Date()),
                level: "info",
                msg: event.message,
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
              setLogs((prev) => [...prev, {
                ts: formatTime(new Date()),
                level: "ok",
                msg: `━━ ${event.status} · ${event.execution_time}s · ${event.total_steps} steps ━━`,
              }]);
              break;

            case "error":
              setRunning(false);
              setLogs((prev) => [...prev, {
                ts: formatTime(new Date()),
                level: "err",
                msg: event.message,
              }]);
              setMeta((m) => ({ ...m, status: "failed" }));
              break;
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Connection failed";
      setRunning(false);
      setLogs((prev) => [...prev, { ts: "—", level: "err", msg: message }]);
      setMeta((m) => ({ ...m, status: "failed" }));
    }
  }, []);

  const handleStop = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    clearTimers();
    setRunning(false);
    setMeta((m) => ({ ...m, status: "failed" }));
    setSteps((prev) =>
      prev.map((s) => (s.status === "running" ? { ...s, status: "failed" } : s))
    );
    setLogs((prev) => [
      ...prev,
      { ts: "—", level: "err", msg: "run aborted by user" },
    ]);
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

  useEffect(() => () => clearTimers(), []);

  const timelineVisible = steps.length > 0;
  const activeStep = activeIndex >= 0 ? steps[activeIndex] : undefined;

  return (
    <div className="space-y-5">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      >
        <TaskInput running={running} onRun={handleRun} onStop={handleStop} apiKeyValue={meta.apiKey} />
      </motion.div>

      <ExecutionTimeline steps={steps} activeIndex={activeIndex} visible={timelineVisible} />

      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.15 }}
        className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr_0.9fr] gap-4"
      >
        <TerminalLogs logs={logs} running={running} />
        <ScreenPreview
          active={running}
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
    plan: "Pro · 1M perception calls / mo",
    region: "us-west-2 · edge",
    startedAt: "—",
  };
}

function formatTime(d: Date) {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

async function executeTask(
  instruction: string,
  apiKey: string,
  signal: AbortSignal
): Promise<ApiExecuteResponse> {
  const res = await fetch(`${API_V1}/execute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify({ instruction }),
    signal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Execute failed (${res.status})`);
  }

  return (await res.json()) as ApiExecuteResponse;
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

function stepsFromResponse(steps: ApiExecuteStep[]): UiStep[] {
  return steps.map((step) => {
    const label = prettifyAction(step.action);
    return {
      id: `s${step.step_number}`,
      label,
      actionCode: step.action,
      action: label,
      description: step.description,
      duration: step.duration != null ? `${step.duration.toFixed(2)}s` : "—",
      status: "pending",
      tag: actionTag(step.action),
      timestamp: step.timestamp,
    };
  });
}

function buildLogsFromSteps(steps: UiStep[], startedAt: Date, executionLabel: string): LogLine[] {
  const startTs = formatTime(startedAt);
  const logs: LogLine[] = [
    { ts: startTs, level: "info", msg: "PerceptAI runtime connected" },
    { ts: startTs, level: "info", msg: `Planning ${steps.length} steps...` },
  ];

  steps.forEach((step) => {
    const ts = step.timestamp ? formatTime(new Date(step.timestamp)) : formatTime(new Date());
    logs.push({
      ts,
      level: "info",
      msg: `Executing: ${step.label} [${step.actionCode}]`,
    });
    logs.push({
      ts,
      level: step.status === "failed" ? "err" : "ok",
      msg: `${step.status === "failed" ? "✗" : "✓"} ${step.label} ${step.status === "failed" ? "failed" : "completed"}`,
    });
  });

  logs.push({
    ts: formatTime(new Date()),
    level: "ok",
    msg: `━━ Execution complete · ${executionLabel}s · ${steps.length} steps ━━`,
  });

  return logs;
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

"use client";

import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { PageHeader } from "@/components/ui/page-header";
import { TaskInput } from "@/components/dashboard/run/task-input";
import { ExecutionTimeline } from "@/components/dashboard/run/execution-timeline";
import { TerminalLogs } from "@/components/dashboard/run/terminal-logs";
import { ScreenPreview } from "@/components/dashboard/run/screen-preview";
import { SessionInfo, type SessionMeta } from "@/components/dashboard/run/session-info";
import {
  initialSteps,
  baseLogs,
  stepLogs,
  type TimelineStep,
  type LogLine,
} from "@/components/dashboard/run/mock-data";
import { pageEntry } from "@/lib/motion";

const STEP_DURATIONS = [620, 1180, 1080, 280, 940, 1320, 320]; // ms per step

export default function RunTaskPage() {
  return (
    <Suspense fallback={null}>
      <RunTaskInner />
    </Suspense>
  );
}

function RunTaskInner() {
  const searchParams = useSearchParams();
  const prefillTask = searchParams.get("task") || undefined;

  const [steps, setSteps] = useState<TimelineStep[]>(initialSteps);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [running, setRunning] = useState(false);
  const [meta, setMeta] = useState<SessionMeta>(makeInitialMeta());
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };

  const resetState = () => {
    clearTimers();
    setSteps(initialSteps.map((s) => ({ ...s, status: "pending" })));
    setActiveIndex(-1);
    setLogs([]);
  };

  const handleRun = useCallback((task: string, keyId: string) => {
    resetState();
    const startedAt = new Date();
    setRunning(true);
    setMeta({
      id: `run_${Math.random().toString(36).slice(2, 10)}${Math.random().toString(36).slice(2, 6)}`,
      status: "running",
      duration: "0.0s",
      stepsTotal: initialSteps.length,
      stepsCompleted: 0,
      apiKey: keyMap[keyId] || keyMap.k1,
      plan: "Pro · 1M perception calls / mo",
      region: "us-west-2 · edge",
      startedAt: formatTime(startedAt),
    });

    setLogs(baseLogs);

    let cumulative = 0;
    initialSteps.forEach((step, idx) => {
      // start step
      const startTimer = setTimeout(() => {
        setActiveIndex(idx);
        setSteps((prev) =>
          prev.map((s, i) => (i === idx ? { ...s, status: "running" } : s))
        );
        setLogs((prev) => [...prev, ...(stepLogs[step.id] || [])]);
      }, cumulative);
      timers.current.push(startTimer);

      cumulative += STEP_DURATIONS[idx];

      // complete step
      const completeTimer = setTimeout(() => {
        setSteps((prev) =>
          prev.map((s, i) => (i === idx ? { ...s, status: "completed" } : s))
        );
        setMeta((m) => ({ ...m, stepsCompleted: idx + 1 }));
      }, cumulative);
      timers.current.push(completeTimer);
    });

    // finalize
    const doneTimer = setTimeout(() => {
      setRunning(false);
      const elapsed = (cumulative / 1000).toFixed(2) + "s";
      setMeta((m) => ({ ...m, status: "completed", duration: elapsed }));
      setActiveIndex(initialSteps.length - 1);
    }, cumulative + 60);
    timers.current.push(doneTimer);
  }, []);

  const handleStop = () => {
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
    const start = Date.now();
    const id = setInterval(() => {
      setMeta((m) => ({ ...m, duration: ((Date.now() - start) / 1000).toFixed(1) + "s" }));
    }, 100);
    return () => clearInterval(id);
  }, [running]);

  useEffect(() => () => clearTimers(), []);

  const timelineVisible = running || activeIndex >= 0;
  const activeStep = activeIndex >= 0 ? steps[activeIndex] : undefined;

  return (
    <motion.div {...pageEntry} className="space-y-7">
      <PageHeader
        eyebrow="Runtime"
        title="Run Task"
        description="Spin up a perception-driven agent run in seconds. Watch every step replay live."
      />

      <div className="space-y-5">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      >
        <TaskInput running={running} onRun={handleRun} onStop={handleStop} initialTask={prefillTask} />
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
    </motion.div>
  );
}

const keyMap: Record<string, string> = {
  k1: "sk_live_••••f2a1",
  k2: "sk_test_••••88c4",
  k3: "sk_test_••••0091",
};

function makeInitialMeta(): SessionMeta {
  return {
    id: "run_idle",
    status: "queued",
    duration: "—",
    stepsTotal: initialSteps.length,
    stepsCompleted: 0,
    apiKey: "sk_live_••••f2a1",
    plan: "Pro · 1M perception calls / mo",
    region: "us-west-2 · edge",
    startedAt: "—",
  };
}

function formatTime(d: Date) {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

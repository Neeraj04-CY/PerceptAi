"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Clock, Plus, CalendarClock, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import {
  readScheduledTasks,
  writeScheduledTasks,
  computeNextRun,
  type ScheduledTask,
} from "@/lib/scheduled-tasks";
import { ScheduleModal } from "./schedule-modal";
import { ScheduledTaskCard } from "./task-card";
import { pageEntry } from "@/lib/motion";

export function ScheduledView() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [open, setOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  // Hydrate from localStorage
  useEffect(() => {
    const initial = readScheduledTasks();
    // Recompute nextRun on hydration so stale timestamps don't show "5 days ago"
    const refreshed = initial.map((t) => {
      if (!t.enabled || t.schedule === "custom") return t;
      const next = computeNextRun(t);
      return { ...t, nextRun: next ? next.toISOString() : t.nextRun };
    });
    setTasks(refreshed);
    setHydrated(true);
  }, []);

  // Persist
  useEffect(() => {
    if (!hydrated) return;
    writeScheduledTasks(tasks);
  }, [tasks, hydrated]);

  const handleCreate = (task: ScheduledTask) => {
    setTasks((prev) => [task, ...prev]);
  };

  const handleToggle = (id: string, enabled: boolean) => {
    setTasks((prev) =>
      prev.map((t) => {
        if (t.id !== id) return t;
        const updated = { ...t, enabled };
        if (enabled && t.schedule !== "custom") {
          const next = computeNextRun(updated);
          updated.nextRun = next ? next.toISOString() : null;
        }
        return updated;
      })
    );
  };

  const handleDelete = (id: string) => {
    setTasks((prev) => prev.filter((t) => t.id !== id));
  };

  const activeCount = useMemo(() => tasks.filter((t) => t.enabled).length, [tasks]);

  return (
    <motion.div {...pageEntry} className="space-y-7">
      <PageHeader
        eyebrow="Automation"
        title={
          <span className="flex items-center gap-3 flex-wrap">
            Scheduled Tasks
            <span
              className="inline-flex items-center rounded-md border border-white/[0.10] bg-white/[0.03] px-2 h-6 font-mono text-[11px] text-white/55"
              data-testid="scheduled-count"
            >
              {hydrated ? tasks.length : "…"}
              {activeCount > 0 && (
                <>
                  <span className="mx-1.5 text-white/25">·</span>
                  <span className="text-accent">{activeCount} active</span>
                </>
              )}
            </span>
          </span>
        }
        description="Automate recurring agent runs. Triggers fire from the PerceptAI runtime on your schedule."
        action={
          <Button
            variant="primary"
            size="md"
            onClick={() => setOpen(true)}
            data-testid="schedule-task-btn"
            className="gap-1.5"
          >
            <Plus size={14} strokeWidth={2.5} />
            Schedule Task
          </Button>
        }
      />

      {hydrated && tasks.length === 0 ? (
        <EmptyState
          icon={<Clock size={26} strokeWidth={1.4} />}
          title="No scheduled tasks yet"
          description="Automate recurring workflows — run any task on a schedule."
          minHeight={400}
          action={
            <Button
              variant="primary"
              size="md"
              onClick={() => setOpen(true)}
              data-testid="empty-schedule-first"
              className="gap-1.5"
            >
              Schedule your first task
              <ArrowRight size={13} />
            </Button>
          }
          testId="scheduled-empty"
        />
      ) : (
        <div className="space-y-3" data-testid="scheduled-list">
          <AnimatePresence initial={false} mode="popLayout">
            {tasks.map((task, i) => (
              <ScheduledTaskCard
                key={task.id}
                task={task}
                index={i}
                onToggle={handleToggle}
                onDelete={handleDelete}
              />
            ))}
          </AnimatePresence>

          {tasks.length > 0 && (
            <div className="mt-6 flex items-center gap-2.5 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
              <CalendarClock size={14} className="text-accent shrink-0" />
              <div className="text-[12px] text-white/55 leading-relaxed">
                Schedules are currently persisted to your browser. Server-side
                scheduling and webhook delivery roll out next quarter — your tasks
                will migrate automatically when it ships.
              </div>
            </div>
          )}
        </div>
      )}

      <ScheduleModal
        open={open}
        onOpenChange={setOpen}
        onCreate={handleCreate}
      />
    </motion.div>
  );
}

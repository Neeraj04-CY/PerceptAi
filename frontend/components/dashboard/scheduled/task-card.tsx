"use client";

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { Play, Trash2 } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { GlassCard } from "@/components/ui/glass-card";
import { cn } from "@/lib/utils";
import {
  formatScheduleLabel,
  formatRunRelative,
  type ScheduledTask,
} from "@/lib/scheduled-tasks";

interface Props {
  task: ScheduledTask;
  index: number;
  onToggle: (id: string, next: boolean) => void;
  onDelete: (id: string) => void;
}

export function ScheduledTaskCard({ task, index, onToggle, onDelete }: Props) {
  const router = useRouter();

  const handleRunNow = () => {
    router.push(`/dashboard?task=${encodeURIComponent(task.instruction)}`);
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: 16 }}
      transition={{
        duration: 0.35,
        delay: Math.min(index * 0.05, 0.4),
        ease: [0.22, 1, 0.36, 1],
      }}
      data-testid={`scheduled-task-${task.id}`}
    >
      <GlassCard
        padding="none"
        className={cn(
          "transition-colors duration-300 hover:bg-white/[0.04] group",
          !task.enabled && "opacity-65"
        )}
      >
        <div className="grid grid-cols-1 lg:grid-cols-[1.7fr_1.3fr_auto] gap-4 lg:gap-6 items-center p-5">
          {/* Left: name + instruction */}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  task.enabled ? "bg-accent" : "bg-white/25"
                )}
              />
              <h3 className="text-[15px] font-semibold tracking-tight text-white truncate">
                {task.name}
              </h3>
            </div>
            <p
              className="mt-1 text-[13px] text-white/55 truncate"
              title={task.instruction}
            >
              {truncate(task.instruction, 60)}
            </p>
            <div className="mt-2 flex items-center gap-2 font-mono text-[10px] text-white/35">
              <span>{task.id}</span>
              <span>·</span>
              <span>{task.runCount} runs</span>
            </div>
          </div>

          {/* Middle: schedule meta */}
          <div className="space-y-1.5 min-w-0">
            <div>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.10] bg-white/[0.03] px-2.5 py-1 font-mono text-[10.5px] uppercase tracking-[0.16em] text-white/75">
                {formatScheduleLabel(task)}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11.5px]">
              <MetaRow label="Next" value={formatRunRelative(task.nextRun)} accent={task.enabled} />
              <MetaRow label="Last" value={formatRunRelative(task.lastRun)} />
            </div>
          </div>

          {/* Right: controls */}
          <div className="flex items-center gap-2 justify-end">
            <Switch
              checked={task.enabled}
              onChange={(next) => onToggle(task.id, next)}
              ariaLabel={task.enabled ? "Disable task" : "Enable task"}
              data-testid={`toggle-${task.id}`}
            />
            <IconButton
              label="Run now"
              testId={`run-now-${task.id}`}
              onClick={handleRunNow}
              intent="accent"
            >
              <Play size={13} strokeWidth={2.4} fill="currentColor" />
            </IconButton>
            <IconButton
              label="Delete"
              testId={`delete-${task.id}`}
              onClick={() => onDelete(task.id)}
              intent="danger"
            >
              <Trash2 size={13} strokeWidth={2} />
            </IconButton>
          </div>
        </div>
      </GlassCard>
    </motion.div>
  );
}

function MetaRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/35">
        {label}
      </span>
      <span
        className={cn(
          "truncate",
          accent ? "text-white/85" : "text-white/55"
        )}
      >
        {value}
      </span>
    </div>
  );
}

function IconButton({
  children,
  onClick,
  label,
  intent = "neutral",
  testId,
}: {
  children: React.ReactNode;
  onClick: () => void;
  label: string;
  intent?: "neutral" | "accent" | "danger";
  testId?: string;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      data-testid={testId}
      className={cn(
        "h-8 w-8 inline-flex items-center justify-center rounded-md border bg-white/[0.03] transition-colors",
        intent === "neutral" && "border-white/[0.08] text-white/65 hover:text-white hover:bg-white/[0.06]",
        intent === "accent" && "border-white/[0.08] text-white/75 hover:text-accent hover:border-accent/40 hover:bg-accent/[0.05]",
        intent === "danger" && "border-white/[0.08] text-white/65 hover:text-[#FF3B3B] hover:border-[#FF3B3B]/40 hover:bg-[#FF3B3B]/[0.06]"
      )}
    >
      {children}
    </button>
  );
}

function truncate(value: string, max: number): string {
  if (!value) return "";
  if (value.length <= max) return value;
  return value.slice(0, max).trimEnd() + "…";
}

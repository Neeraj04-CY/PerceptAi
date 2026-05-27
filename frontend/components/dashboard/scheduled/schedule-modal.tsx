"use client";

import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogBody,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  DAY_KEYS,
  computeNextRun,
  makeTaskId,
  type ScheduledTask,
  type ScheduleType,
} from "@/lib/scheduled-tasks";

const SCHEDULE_OPTIONS: { value: ScheduleType; label: string }[] = [
  { value: "hourly", label: "Hourly" },
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "custom", label: "Custom" },
];

const DAY_LABEL: Record<string, string> = {
  mon: "Mon",
  tue: "Tue",
  wed: "Wed",
  thu: "Thu",
  fri: "Fri",
  sat: "Sat",
  sun: "Sun",
};

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (task: ScheduledTask) => void;
}

export function ScheduleModal({ open, onOpenChange, onCreate }: Props) {
  const [name, setName] = useState("");
  const [instruction, setInstruction] = useState("");
  const [schedule, setSchedule] = useState<ScheduleType>("daily");
  const [time, setTime] = useState("09:00");
  const [days, setDays] = useState<string[]>(["mon", "wed", "fri"]);
  const [cron, setCron] = useState("0 9 * * *");
  const textRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!open) {
      // small reset delay so closing animation runs first
      const t = setTimeout(() => {
        setName("");
        setInstruction("");
        setSchedule("daily");
        setTime("09:00");
        setDays(["mon", "wed", "fri"]);
        setCron("0 9 * * *");
      }, 220);
      return () => clearTimeout(t);
    }
  }, [open]);

  useEffect(() => {
    if (!textRef.current) return;
    textRef.current.style.height = "auto";
    textRef.current.style.height = `${Math.min(textRef.current.scrollHeight, 180)}px`;
  }, [instruction, open]);

  const toggleDay = (d: string) => {
    setDays((prev) =>
      prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]
    );
  };

  const canSubmit =
    name.trim().length > 0 &&
    instruction.trim().length > 0 &&
    (schedule !== "weekly" || days.length > 0) &&
    (schedule !== "custom" || cron.trim().length > 0);

  const submit = () => {
    if (!canSubmit) return;
    const base: ScheduledTask = {
      id: makeTaskId(),
      name: name.trim(),
      instruction: instruction.trim(),
      schedule,
      time,
      days: schedule === "weekly" ? days : [],
      cron: schedule === "custom" ? cron.trim() : undefined,
      enabled: true,
      lastRun: null,
      nextRun: null,
      runCount: 0,
      createdAt: new Date().toISOString(),
    };
    const next = computeNextRun(base);
    base.nextRun = next ? next.toISOString() : null;
    onCreate(base);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="lg">
      <DialogHeader>
        <DialogTitle>Schedule New Task</DialogTitle>
        <DialogDescription>
          Automate any agent run on a schedule. Triggers fire from the
          PerceptAI runtime — your machine doesn&apos;t need to be online.
        </DialogDescription>
      </DialogHeader>

      <DialogBody>
        <div className="space-y-5">
          {/* Name */}
          <div>
            <Label>Task name</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Morning news digest"
              data-testid="schedule-name"
              className="mt-2"
              autoFocus
            />
          </div>

          {/* Instruction */}
          <div>
            <Label>Instruction</Label>
            <textarea
              ref={textRef}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Open Chrome, go to news.ycombinator.com, extract top 5 stories"
              data-testid="schedule-instruction"
              rows={2}
              className={cn(
                "mt-2 w-full resize-none rounded-lg border border-white/[0.08] bg-white/[0.02] px-3.5 py-2.5 text-[13.5px] leading-relaxed text-white placeholder:text-white/30",
                "focus:outline-none focus:border-accent/40 focus:bg-white/[0.03] focus:ring-1 focus:ring-accent/20 transition-all duration-200"
              )}
            />
          </div>

          {/* Schedule type */}
          <div>
            <Label>Schedule</Label>
            <div className="mt-2 grid grid-cols-4 gap-2">
              {SCHEDULE_OPTIONS.map((opt) => {
                const active = schedule === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setSchedule(opt.value)}
                    data-testid={`schedule-type-${opt.value}`}
                    className={cn(
                      "h-10 rounded-lg border text-[12.5px] transition-colors",
                      active
                        ? "border-accent/40 bg-accent/10 text-accent"
                        : "border-white/[0.08] bg-white/[0.02] text-white/65 hover:border-white/20"
                    )}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Time (daily / weekly / hourly minutes) */}
          {schedule !== "custom" && (
            <div className="grid grid-cols-[1fr_auto] gap-3 items-end">
              <div>
                <Label>
                  {schedule === "hourly" ? "Minute (HH:MM, hour ignored)" : "Time"}
                </Label>
                <Input
                  type="time"
                  value={time}
                  onChange={(e) => setTime(e.target.value)}
                  data-testid="schedule-time"
                  className="mt-2"
                />
              </div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/35 pb-3">
                {timezoneLabel()}
              </div>
            </div>
          )}

          {/* Days (weekly) */}
          {schedule === "weekly" && (
            <div>
              <Label>Days</Label>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {DAY_KEYS.map((d) => {
                  const active = days.includes(d);
                  return (
                    <button
                      key={d}
                      type="button"
                      onClick={() => toggleDay(d)}
                      data-testid={`schedule-day-${d}`}
                      className={cn(
                        "h-8 px-3 rounded-full border text-[11.5px] font-medium transition-colors",
                        active
                          ? "bg-accent text-black border-accent"
                          : "border-white/[0.10] bg-white/[0.02] text-white/65 hover:text-white hover:border-white/20"
                      )}
                    >
                      {DAY_LABEL[d]}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Cron (custom) */}
          {schedule === "custom" && (
            <div>
              <Label>Cron expression</Label>
              <Input
                value={cron}
                onChange={(e) => setCron(e.target.value)}
                placeholder="0 9 * * *"
                data-testid="schedule-cron"
                className="mt-2 font-mono"
              />
              <p className="mt-2 font-mono text-[10.5px] text-white/40">
                Standard 5-field cron · evaluated in your local timezone
              </p>
            </div>
          )}
        </div>
      </DialogBody>

      <DialogFooter>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onOpenChange(false)}
          data-testid="cancel-schedule"
        >
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={submit}
          data-testid="confirm-schedule"
          className={cn(!canSubmit && "opacity-50 pointer-events-none")}
        >
          Schedule Task
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
      {children}
    </label>
  );
}

function timezoneLabel(): string {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return tz.replace("_", " ");
  } catch {
    return "local";
  }
}

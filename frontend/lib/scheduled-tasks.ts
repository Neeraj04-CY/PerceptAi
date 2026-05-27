export type ScheduleType = "hourly" | "daily" | "weekly" | "custom";

export interface ScheduledTask {
  id: string;
  name: string;
  instruction: string;
  schedule: ScheduleType;
  time: string; // "HH:MM"
  days: string[]; // ["mon","tue", ...]
  cron?: string;
  enabled: boolean;
  lastRun: string | null;
  nextRun: string | null;
  runCount: number;
  createdAt: string;
}

const STORAGE_KEY = "perceptai_scheduled_tasks";

export function readScheduledTasks(): ScheduledTask[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as ScheduledTask[]) : [];
  } catch {
    return [];
  }
}

export function writeScheduledTasks(tasks: ScheduledTask[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
  } catch {
    // ignore quota / private mode
  }
}

export const DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
export type DayKey = (typeof DAY_KEYS)[number];

const DAY_TO_INDEX: Record<DayKey, number> = {
  // JS getDay(): Sun=0..Sat=6
  sun: 0,
  mon: 1,
  tue: 2,
  wed: 3,
  thu: 4,
  fri: 5,
  sat: 6,
};

export function computeNextRun(task: ScheduledTask, from: Date = new Date()): Date | null {
  const [hh, mm] = (task.time || "09:00").split(":").map((n) => parseInt(n, 10));
  if (Number.isNaN(hh) || Number.isNaN(mm)) return null;

  if (task.schedule === "hourly") {
    const next = new Date(from);
    next.setMinutes(mm, 0, 0);
    if (next.getTime() <= from.getTime()) next.setHours(next.getHours() + 1);
    return next;
  }

  if (task.schedule === "daily") {
    const next = new Date(from);
    next.setHours(hh, mm, 0, 0);
    if (next.getTime() <= from.getTime()) next.setDate(next.getDate() + 1);
    return next;
  }

  if (task.schedule === "weekly") {
    if (!task.days.length) return null;
    const targets = task.days
      .map((d) => DAY_TO_INDEX[d as DayKey])
      .filter((n) => typeof n === "number");
    if (!targets.length) return null;

    for (let i = 0; i < 8; i++) {
      const candidate = new Date(from);
      candidate.setDate(from.getDate() + i);
      candidate.setHours(hh, mm, 0, 0);
      if (
        targets.includes(candidate.getDay()) &&
        candidate.getTime() > from.getTime()
      ) {
        return candidate;
      }
    }
    return null;
  }

  return null; // custom — handled separately
}

const DAY_LABEL: Record<DayKey, string> = {
  mon: "Mon",
  tue: "Tue",
  wed: "Wed",
  thu: "Thu",
  fri: "Fri",
  sat: "Sat",
  sun: "Sun",
};

export function formatScheduleLabel(task: ScheduledTask): string {
  if (task.schedule === "hourly") {
    return `Hourly at :${task.time.split(":")[1] || "00"}`;
  }
  if (task.schedule === "daily") {
    return `Daily at ${task.time}`;
  }
  if (task.schedule === "weekly") {
    if (!task.days.length) return "Weekly";
    const ordered = (Object.keys(DAY_LABEL) as DayKey[]).filter((d) =>
      task.days.includes(d)
    );
    return `Weekly · ${ordered.map((d) => DAY_LABEL[d]).join("/")} at ${task.time}`;
  }
  if (task.schedule === "custom") {
    return task.cron ? `Custom · ${task.cron}` : "Custom";
  }
  return "—";
}

export function formatRunRelative(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const diffMs = d.getTime() - Date.now();
  const absMin = Math.round(Math.abs(diffMs) / 60_000);
  if (absMin < 1) return diffMs >= 0 ? "in a moment" : "just now";
  if (absMin < 60) {
    const txt = `${absMin} min`;
    return diffMs >= 0 ? `in ${txt}` : `${txt} ago`;
  }
  const absHr = Math.round(absMin / 60);
  if (absHr < 24) {
    const txt = `${absHr} hr`;
    return diffMs >= 0 ? `in ${txt}` : `${txt} ago`;
  }
  // Today/Tomorrow/Yesterday handling
  const now = new Date();
  const candidate = new Date(d);
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();
  const tomorrow = new Date(now);
  tomorrow.setDate(now.getDate() + 1);
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (sameDay(candidate, now)) return diffMs >= 0 ? `Today at ${time}` : `Today, ${time}`;
  if (sameDay(candidate, tomorrow)) return `Tomorrow at ${time}`;
  if (sameDay(candidate, yesterday)) return `Yesterday at ${time}`;
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function makeTaskId(): string {
  return (
    "sch_" +
    Math.random().toString(36).slice(2, 10) +
    Math.random().toString(36).slice(2, 6)
  );
}

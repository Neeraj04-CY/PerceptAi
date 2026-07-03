export type StepStatus = "pending" | "running" | "completed" | "failed";

export interface TimelineStep {
  id: string;
  action: string;
  description: string;
  duration: string; // e.g. "0.42s"
  status: StepStatus;
  tag?: string;
}

export interface LogLine {
  ts: string;
  level: "info" | "ok" | "warn" | "err";
  msg: string;
}

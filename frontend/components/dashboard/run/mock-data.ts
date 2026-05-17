export type StepStatus = "pending" | "running" | "completed" | "failed";

export interface TimelineStep {
  id: string;
  action: string;
  description: string;
  duration: string; // e.g. "0.42s"
  status: StepStatus;
  tag?: string;
}

export const initialSteps: TimelineStep[] = [
  {
    id: "s1",
    action: "Launching Chrome",
    description: "Headless browser session on edge-region us-west-2",
    duration: "0.62s",
    status: "pending",
    tag: "BROWSER",
  },
  {
    id: "s2",
    action: "Detecting UI elements",
    description: "Parsed 142 DOM nodes · 23 interactive surfaces",
    duration: "0.41s",
    status: "pending",
    tag: "VISION",
  },
  {
    id: "s3",
    action: "Building action plan",
    description: "Composed 6-step trajectory · grounded against perception graph",
    duration: "0.88s",
    status: "pending",
    tag: "PLAN",
  },
  {
    id: "s4",
    action: "Clicking search field",
    description: "Element: input[name=q] · confidence 0.97",
    duration: "0.18s",
    status: "pending",
    tag: "ACTION",
  },
  {
    id: "s5",
    action: "Typing instruction",
    description: '"latest AI infrastructure news december 2025"',
    duration: "0.72s",
    status: "pending",
    tag: "ACTION",
  },
  {
    id: "s6",
    action: "Validating response",
    description: "Cross-checked 3 sources · semantic score 0.91",
    duration: "1.04s",
    status: "pending",
    tag: "VERIFY",
  },
  {
    id: "s7",
    action: "Task completed",
    description: "Summary generated · 412 tokens · saved to session",
    duration: "0.09s",
    status: "pending",
    tag: "DONE",
  },
];

export interface LogLine {
  ts: string;
  level: "info" | "ok" | "warn" | "err";
  msg: string;
}

export const baseLogs: LogLine[] = [
  { ts: "00:00.000", level: "info", msg: "percept.runtime · boot · region=us-west-2" },
  { ts: "00:00.014", level: "info", msg: "auth: api_key sk_live_••••f2a1 · scope=run:write" },
];

export const stepLogs: Record<string, LogLine[]> = {
  s1: [
    { ts: "00:00.142", level: "info", msg: "→ launching chromium · v131.0.6778.85" },
    { ts: "00:00.612", level: "ok", msg: "✓ session attached · pid=4821 · viewport=1440×900" },
  ],
  s2: [
    { ts: "00:00.741", level: "info", msg: "vision.capture frame#0001 · 1.2MB · 38ms" },
    { ts: "00:01.018", level: "info", msg: "embed → 768d · 142 nodes graphed" },
    { ts: "00:01.140", level: "ok", msg: "✓ 23 interactive surfaces detected" },
  ],
  s3: [
    { ts: "00:01.290", level: "info", msg: "planner: composing trajectory" },
    { ts: "00:01.812", level: "info", msg: "grounded 6 actions against perception graph" },
    { ts: "00:02.018", level: "ok", msg: "✓ plan accepted · est.cost 0.0008¢" },
  ],
  s4: [
    { ts: "00:02.105", level: "info", msg: "action.click target=input[name=q] conf=0.97" },
    { ts: "00:02.198", level: "ok", msg: "✓ focused" },
  ],
  s5: [
    { ts: "00:02.310", level: "info", msg: "action.type · 47 chars · human pacing" },
    { ts: "00:02.946", level: "ok", msg: "✓ input committed" },
  ],
  s6: [
    { ts: "00:03.118", level: "info", msg: "verify: cross-source check (n=3)" },
    { ts: "00:03.741", level: "warn", msg: "source 2 latency 412ms · acceptable" },
    { ts: "00:04.119", level: "ok", msg: "✓ semantic score 0.91" },
  ],
  s7: [
    { ts: "00:04.182", level: "info", msg: "summarize · 412 tokens · model=percept-r1" },
    { ts: "00:04.210", level: "ok", msg: "✓ run.commit · trace persisted" },
  ],
};

export interface ApiSessionStep {
  step_number: number;
  description: string;
  action: string;
  status: "completed" | "failed";
  result?: { success: boolean; [key: string]: unknown };
  timestamp: string;
  duration: number;
  [key: string]: unknown;
}

export interface ApiEvidence {
  kind: string;
  label: string;
  value: string;
  source: string;
  confidence: number;
  collected_at?: string;
}

export interface ApiTaskReport {
  executive_summary: string;
  key_findings: string[];
  evidence: ApiEvidence[];
  confidence: number;
  sources: string[];
  artifacts: Array<{ kind: string; path: string; description: string }>;
  next_actions: string[];
}

export interface ApiPerceptionStats {
  snapshots: number;
  providers: Record<
    string,
    { calls: number; failures: number; observations: number; avg_latency_ms: number }
  >;
  final_confidence?: number;
  final_elements?: number;
  final_windows?: number;
}

/** Replayable reasoning record from TaskResult.metadata.reasoning. */
export interface ApiReasoningSummary {
  strategy: string;
  cycles: number;
  decisions: Record<string, number>;
  decision_changes: number;
  final_progress: {
    completion: number;
    confidence: number;
    objectives_met: number;
    objectives_total: number;
    risk: number;
    remaining_work: string;
  };
  final_uncertainty: number;
  uncertainty_signals: Array<{ kind: string; detail: string; severity: number }>;
  beliefs: Array<{
    statement: string;
    kind: string;
    subject: string;
    confidence: number;
    supports: number;
    contradictions: number;
  }>;
  hypotheses: { created: number; confirmed: number; rejected: number; open: number };
  trajectory: Array<{
    cycle: number;
    decision: string;
    reason: string;
    uncertainty: number;
    progress: number;
    queue: number;
  }>;
  confidence_history: Array<{
    cycle: number;
    world_confidence: number;
    uncertainty: number;
    progress: number;
  }>;
}

export interface ApiTaskResult {
  status: string;
  summary?: string;
  report?: ApiTaskReport | null;
  metadata?: {
    perception?: ApiPerceptionStats;
    reasoning?: ApiReasoningSummary;
    [key: string]: unknown;
  } | null;
  goal?: {
    intent: string;
    deliverable: string;
    output_format: string;
    objectives: string[];
    completion_criteria: string[];
  } | null;
  verification?: {
    verified: boolean;
    confidence: number;
    reason: string;
    checks: Array<{ name: string; passed: boolean; critical: boolean; detail: string }>;
  } | null;
  [key: string]: unknown;
}

export interface ApiSession {
  id: string;
  instruction: string;
  status: "completed" | "unverified" | "failed" | "running";
  execution_time: number | null;
  steps: ApiSessionStep[];
  result?: ApiTaskResult | null;
  created_at: string;
}

export interface DashboardStats {
  total_sessions: number;
  successful_sessions: number;
  failed_sessions: number;
  total_executions_this_month: number;
  executions_limit: number;
  recent_sessions: Array<{
    id: string;
    instruction: string;
    status: string;
    execution_time: number | null;
    steps_count: number;
    created_at: string;
  }>;
  plan: string;
}

export interface UsageStats {
  month: string;
  executions_used: number;
  executions_limit: number;
  plan: string;
  percentage_used: number;
}

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "https://perceptai-production.up.railway.app").replace(/\/$/, "");
const API_V1 = `${API_BASE}/api/v1`;
const FULL_KEY_STORAGE_PREFIX = "perceptai_full_key_";
const ACTIVE_KEY_STORAGE_KEY = "perceptai_active_key";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("perceptai_token");
}

export async function getFullKey(): Promise<string> {
  if (typeof window === "undefined") return "";

  const active = window.localStorage.getItem(ACTIVE_KEY_STORAGE_KEY);
  if (active && active.startsWith("pk_")) return active;

  for (let i = 0; i < window.localStorage.length; i += 1) {
    const k = window.localStorage.key(i);
    if (k?.startsWith(FULL_KEY_STORAGE_PREFIX)) {
      const val = window.localStorage.getItem(k);
      if (val) return val;
    }
  }

  return "";
}

type AuthResponse = {
  access_token: string;
  token_type?: string;
  [key: string]: unknown;
};

async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${API_V1}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "omit",
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Request failed (${res.status})`);
  }

  return (await res.json()) as T;
}

async function getJsonAuth<T>(path: string, signal?: AbortSignal): Promise<T> {
  const token = getToken();
  if (!token) {
    throw new Error("Unauthorized");
  }

  const res = await fetch(`${API_V1}${path}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
    signal,
  });

  if (res.status === 401 || res.status === 403) {
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Request failed (${res.status})`);
  }

  return (await res.json()) as T;
}

export async function signIn(email: string, password: string): Promise<AuthResponse> {
  return postJson<AuthResponse>("/auth/signin", { email, password });
}

export async function signUp(email: string, password: string): Promise<AuthResponse> {
  return postJson<AuthResponse>("/auth/signup", { email, password });
}

export async function getSessions(signal?: AbortSignal): Promise<ApiSession[]> {
  const token = getToken();
  const res = await fetch(`${API_V1}/dashboard/sessions`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    cache: "no-store",
    signal,
  });

  if (!res.ok) {
    throw new Error(`Failed to load sessions (${res.status})`);
  }

  const data = (await res.json()) as ApiSession[] | { sessions: ApiSession[] };
  return Array.isArray(data) ? data : data.sessions || [];
}

export async function getSession(
  id: string,
  signal?: AbortSignal
): Promise<ApiSession> {
  const token = getToken();
  const res = await fetch(
    `${API_V1}/dashboard/sessions/${encodeURIComponent(id)}`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      cache: "no-store",
      signal,
    }
  );

  if (!res.ok) {
    throw new Error(`Failed to load session (${res.status})`);
  }

  return (await res.json()) as ApiSession;
}

export async function getDashboardStats(signal?: AbortSignal): Promise<DashboardStats> {
  return getJsonAuth<DashboardStats>("/dashboard/stats", signal);
}

export async function getUsage(signal?: AbortSignal): Promise<UsageStats> {
  return getJsonAuth<UsageStats>("/dashboard/usage", signal);
}

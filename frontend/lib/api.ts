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

export interface ApiSession {
  id: string;
  instruction: string;
  status: "completed" | "failed" | "running";
  execution_time: number | null;
  steps: ApiSessionStep[];
  created_at: string;
}

const API_BASE = "https://perceptai-production.up.railway.app/api/v1";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("perceptai_token");
}

export async function getSessions(signal?: AbortSignal): Promise<ApiSession[]> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/dashboard/sessions`, {
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
    `${API_BASE}/dashboard/sessions/${encodeURIComponent(id)}`,
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

export interface ApiStats {
  total_sessions?: number;
  successful_sessions?: number;
  failed_sessions?: number;
  success_rate?: number;
  avg_duration?: number;
  total_executions_this_month?: number;
  executions_limit?: number;
  monthly_usage?: number;
  monthly_limit?: number;
  plan?: string;
  recent_sessions?: ApiSession[];
  [key: string]: unknown;
}

export async function getStats(signal?: AbortSignal): Promise<ApiStats> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/dashboard/stats`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    cache: "no-store",
    signal,
  });

  if (!res.ok) {
    throw new Error(`Failed to load stats (${res.status})`);
  }

  return (await res.json()) as ApiStats;
}

export interface ApiUsage {
  month?: string;
  executions_used?: number;
  executions_limit?: number;
  plan?: string;
  percentage_used?: number;
  [key: string]: unknown;
}

export async function getUsage(signal?: AbortSignal): Promise<ApiUsage> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/dashboard/usage`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    cache: "no-store",
    signal,
  });

  if (!res.ok) {
    throw new Error(`Failed to load usage (${res.status})`);
  }

  return (await res.json()) as ApiUsage;
}

export interface ApiSessionStep {
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

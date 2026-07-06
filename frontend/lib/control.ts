/** Execution control client (trust layer). Pause/resume/stop a live run and
 * settle approval requests. Auth mirrors the streaming surface (X-API-Key);
 * the execution id is the `session_id` the stream reports. */

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const API_V1 = `${API_BASE}/api/v1`;

export type ControlAction = "pause" | "resume" | "stop";
export type ApprovalDecision = "grant" | "deny";

async function post(path: string, body: Record<string, unknown>, apiKey: string) {
  const res = await fetch(`${API_V1}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Control error ${res.status}`);
  }
  return res.json().catch(() => ({}));
}

export function sendControl(sessionId: string, action: ControlAction, apiKey: string) {
  return post(`/executions/${sessionId}/control`, { action }, apiKey);
}

export function decideApproval(
  sessionId: string,
  requestId: string,
  decision: ApprovalDecision,
  apiKey: string,
  reason = ""
) {
  return post(`/executions/${sessionId}/approvals/${requestId}`, { decision, reason }, apiKey);
}

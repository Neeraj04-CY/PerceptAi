/** POST-based SSE reader shared by the run surfaces. Parses `data:` lines
 * into JSON events and hands each to the callback; transport errors and
 * malformed lines never throw into React state. */

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const API_V1 = `${API_BASE}/api/v1`;

async function readSse(
  response: Response,
  onEvent: (event: Record<string, unknown> & { type: string }) => void
): Promise<void> {
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `API error: ${response.status}`);
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response stream available");

  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;
      try {
        const event = JSON.parse(raw);
        if (event && typeof event.type === "string") onEvent(event);
      } catch {
        // partial or malformed frame — skip
      }
    }
  }
}

export async function streamPost(
  path: string,
  body: Record<string, unknown>,
  apiKey: string,
  onEvent: (event: Record<string, unknown> & { type: string }) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(`${API_V1}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify(body),
    signal,
  });
  await readSse(response, onEvent);
}

/** JWT GET SSE — the live relay for a remote runner's execution. Same event
 * shapes as streamPost, so it drives the same cockpit. */
export async function streamGet(
  path: string,
  token: string,
  onEvent: (event: Record<string, unknown> & { type: string }) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(`${API_V1}${path}`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
    signal,
  });
  await readSse(response, onEvent);
}

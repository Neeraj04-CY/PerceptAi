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

/* ------------------------------- API keys ------------------------------- */

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface NewApiKey extends ApiKey {
  full_key: string;
}

export const getKeys = (signal?: AbortSignal) =>
  getJsonAuth<ApiKey[]>("/keys", signal);
export const createKey = (name: string) =>
  sendJsonAuth<NewApiKey>("POST", "/keys", { name });
export const revokeKey = (id: string) =>
  sendJsonAuth<{ message: string }>("DELETE", `/keys/${encodeURIComponent(id)}`);

/* ---------------------- Analytics V2 (unified summary) ------------------- */

export type AnalyticsRangeKey = "7d" | "30d" | "90d";
export type AnalyticsKind = "all" | "task" | "mission";

export interface AnalyticsTotals {
  runs: number;
  tasks: number;
  missions: number;
  succeeded: number;
  needs_attention: number;
  failed: number;
  success_rate: number;
  verification_rate: number;
}

export interface AnalyticsTimePoint {
  date: string;
  success: number;
  attention: number;
  failure: number;
}

export interface AnalyticsLatency {
  p50_s: number | null;
  p95_s: number | null;
  avg_s: number | null;
  series: Array<{ date: string; p50: number | null }>;
}

export interface AnalyticsCalibration {
  buckets: Array<{ lo: number; hi: number; n: number; actual_success: number | null }>;
  mean_error: number | null;
  verification_accuracy: number | null;
  sample_size: number;
}

export interface AnalyticsFailure {
  type: string;
  label: string;
  count: number;
}

export interface AnalyticsMissionsBlock {
  count: number;
  reassignments: number;
  duplicates_cancelled: number;
  avg_orders: number;
  cost_total: number;
  specialist_utilization: Record<string, number>;
}

export interface AnalyticsRecommendation {
  severity: "high" | "medium" | "info";
  title: string;
  detail: string;
  metric: string;
}

export interface AnalyticsSummary {
  range: { days: number; start: string; end: string };
  kind: AnalyticsKind;
  totals: AnalyticsTotals;
  timeseries: AnalyticsTimePoint[];
  latency: AnalyticsLatency;
  calibration: AnalyticsCalibration;
  failures: AnalyticsFailure[];
  cost: {
    executions_used: number;
    executions_limit: number;
    percentage_used: number;
    mission_cost_total: number;
  };
  missions: AnalyticsMissionsBlock | null;
  recommendations: AnalyticsRecommendation[];
}

export const getAnalyticsSummary = (
  range: AnalyticsRangeKey,
  kind: AnalyticsKind,
  signal?: AbortSignal,
) => getJsonAuth<AnalyticsSummary>(`/analytics/summary?range=${range}&kind=${kind}`, signal);

/* ------------------------------------------------------------------ */
/* Platform (Chapter Ω): orgs, missions, workflows, approvals, health  */
/* ------------------------------------------------------------------ */

async function sendJsonAuth<T>(
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: Record<string, unknown>
): Promise<T> {
  const token = getToken();
  if (!token) throw new Error("Unauthorized");
  const res = await fetch(`${API_V1}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  if (res.status === 401 || res.status === 403) throw new Error("Unauthorized");
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export interface ApiOrg {
  id: string;
  name: string;
  slug: string;
  plan_id: string;
  is_personal: boolean;
  role: string;
  created_at?: string;
}

export interface ApiWorkspace {
  id: string;
  org_id: string;
  name: string;
  slug: string;
  description: string;
  environment: string;
  policy: {
    approval_capabilities?: string[];
    allowed_capabilities?: string[] | null;
    max_cost_per_mission?: number | null;
  } | null;
  notify_webhook_url?: string | null; // the signing secret is write-only, never returned
  egress_policy?: { mode?: string; redact?: string[]; custom_patterns?: string[] } | null;
  created_at?: string;
}

export interface ApiOrgDetail extends ApiOrg {
  plan: { id: string; name: string; monthly_executions: number; limits: Record<string, number> };
  member_count: number;
  workspaces: ApiWorkspace[];
}

export interface ApiMember {
  user_id: string;
  email: string;
  role: string;
  joined_at?: string;
}

export interface ApiSecretMeta {
  id: string;
  name: string;
  workspace_id: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ApiAuditEntry {
  id: number;
  org_id: string;
  workspace_id: string | null;
  actor_id: string | null;
  actor_email: string;
  action: string;
  target: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface OrgUsage {
  month: string;
  executions_used: number;
  executions_limit: number;
  plan: string;
  workforce_limits: Record<string, number>;
  percentage_used: number;
}

export interface ApiMissionMetrics {
  orders_total: number;
  orders_completed: number;
  orders_failed: number;
  orders_cancelled: number;
  orders_skipped: number;
  reassignments: number;
  duplicates_cancelled: number;
  peak_parallelism: number;
  cycles: number;
  cost_total: number;
  evidence_count: number;
  conflicts_open: number;
  specialist_utilization: Record<string, number>;
}

export interface ApiWorkOrder {
  id: string;
  objective: string;
  capability: string;
  status: string;
  status_reason: string;
  assigned_to: string;
  attempts: number;
  depends_on: string[];
  requires: string[];
  produces: string[];
  priority: number;
}

export interface ApiWorkResult {
  order_id: string;
  specialist: string;
  status: string;
  summary: string;
  outputs: Record<string, string>;
  evidence: ApiEvidence[];
  confidence: number;
  duration_s: number;
  cost: number;
  error: string;
}

export interface ApiMissionResult {
  mission_id: string;
  instruction: string;
  status: string;
  report?: ApiTaskReport | null;
  orders: ApiWorkOrder[];
  work: ApiWorkResult[];
  metrics: ApiMissionMetrics;
  duration_s: number;
  errors: string[];
  confidence: number;
  metadata?: {
    evidence_graph?: { claims: number; entities: number; sources: number; avg_confidence: number };
    conflicts?: Array<{ entity: string; attribute: string; values: Array<{ value: string; sources: string[] }> }>;
    specialists?: Array<{ name: string; capabilities: string[]; active: number; completed: number; failed: number; healthy: boolean }>;
    [key: string]: unknown;
  } | null;
}

export interface ApiMission {
  id: string;
  instruction: string;
  status: "pending" | "running" | "completed" | "partial" | "failed" | "cancelled";
  result?: ApiMissionResult | null;
  metrics?: ApiMissionMetrics | null;
  error?: string | null;
  duration_s: number | null;
  workspace_id?: string | null;
  workflow_id?: string | null;
  created_at: string;
  completed_at?: string | null;
}

export interface ApiEventRow {
  seq: number;
  type: string;
  task_id: string;
  ts: string | null;
  payload: Record<string, unknown>;
}

export interface ApiApproval {
  id: string;
  org_id: string;
  workspace_id: string | null;
  mission_id: string | null;
  capability: string;
  objective: string;
  status: "pending" | "approved" | "denied" | "consumed";
  requested_by: string | null;
  decided_by: string | null;
  reason: string;
  created_at: string;
  decided_at?: string | null;
}

// Unattended operations (Sprint 8): where a scheduled run executes and what
// happens when it fails — data on the workflow schedule, enforced by the plane.
export interface ApiWorkflowTarget {
  kind: "this_machine" | "runner" | "any_available";
  runner_id?: string;
}

export interface ApiWorkflowSchedule {
  enabled?: boolean;
  interval_minutes?: number;
  next_run_at?: string;
  last_run_at?: string;
  target?: ApiWorkflowTarget;
  on_failure?: { retries?: number; notify?: boolean };
}

export interface ApiWorkflowVariable {
  name: string;
  label?: string;
  type?: string;
  default?: string;
  required?: boolean;
  description?: string;
}

export interface ApiWorkflow {
  id: string;
  org_id?: string;
  workspace_id: string | null;
  name: string;
  description: string;
  instruction: string;
  variables: ApiWorkflowVariable[];
  mode: "task" | "mission";
  policy: Record<string, unknown>;
  status: "draft" | "published" | "archived";
  version: number;
  schedule: ApiWorkflowSchedule | null;
  created_at?: string;
  updated_at?: string;
  versions?: Array<{ version: number; published_by: string; published_at: string }>;
}

export interface ApiTemplate {
  id: string;
  name: string;
  category: string;
  mode: "task" | "mission";
  description: string;
  instruction: string;
  variables: ApiWorkflowVariable[];
  outputs: string[];
  // Enterprise catalog metadata (Chapter XI).
  pack?: string;
  flagship?: boolean;
  value?: string;
  apps?: string[];
  time_saved?: string;
}

export interface ApiPack {
  id: string;
  name: string;
  tagline: string;
  templates: ApiTemplate[];
}

export interface ApiCapabilities {
  available: boolean;
  reason?: string;
  specialists: Array<{
    name: string;
    capabilities: string[];
    description: string;
    cost: number;
    latency_s: number;
    confidence: number;
    resources: string[];
    provider: string;
    version: string;
    healthy: boolean;
  }>;
  capabilities: string[];
  plugin_count?: number;
}

export interface PlatformHealth {
  status: string;
  database: boolean;
  engine: boolean;
  engine_reason: string;
  execution_host: boolean;
  scheduler: boolean;
  environment: string;
}

// Organizations
export const getOrgs = (signal?: AbortSignal) => getJsonAuth<ApiOrg[]>("/orgs", signal);
export const getOrgDetail = (orgId: string, signal?: AbortSignal) =>
  getJsonAuth<ApiOrgDetail>(`/orgs/${orgId}`, signal);
export const createOrg = (name: string) => sendJsonAuth<ApiOrg>("POST", "/orgs", { name });
export const getMembers = (orgId: string, signal?: AbortSignal) =>
  getJsonAuth<ApiMember[]>(`/orgs/${orgId}/members`, signal);
export const addMember = (orgId: string, email: string, role: string) =>
  sendJsonAuth<ApiMember>("POST", `/orgs/${orgId}/members`, { email, role });
export const updateMemberRole = (orgId: string, userId: string, role: string) =>
  sendJsonAuth<{ user_id: string; role: string }>("PATCH", `/orgs/${orgId}/members/${userId}`, { role });
export const removeMember = (orgId: string, userId: string) =>
  sendJsonAuth<{ removed: string }>("DELETE", `/orgs/${orgId}/members/${userId}`);
export const createWorkspace = (orgId: string, name: string, description = "", environment = "production") =>
  sendJsonAuth<ApiWorkspace>("POST", `/orgs/${orgId}/workspaces`, { name, description, environment });
export const updateWorkspacePolicy = (orgId: string, workspaceId: string, policy: Record<string, unknown>) =>
  sendJsonAuth<ApiWorkspace>("PATCH", `/orgs/${orgId}/workspaces/${workspaceId}`, { policy });
export const getSecrets = (orgId: string, signal?: AbortSignal) =>
  getJsonAuth<ApiSecretMeta[]>(`/orgs/${orgId}/secrets`, signal);
export const createSecret = (orgId: string, name: string, value: string, workspaceId?: string) =>
  sendJsonAuth<ApiSecretMeta>("POST", `/orgs/${orgId}/secrets`, {
    name, value, workspace_id: workspaceId ?? null,
  });
export const deleteSecret = (orgId: string, secretId: string) =>
  sendJsonAuth<{ deleted: string }>("DELETE", `/orgs/${orgId}/secrets/${secretId}`);
export const getAudit = (orgId: string, limit = 100, signal?: AbortSignal) =>
  getJsonAuth<ApiAuditEntry[]>(`/orgs/${orgId}/audit?limit=${limit}`, signal);
export const getOrgUsage = (orgId: string, signal?: AbortSignal) =>
  getJsonAuth<OrgUsage>(`/orgs/${orgId}/usage`, signal);

// Missions
export const getMissions = (limit = 25, signal?: AbortSignal) =>
  getJsonAuth<ApiMission[]>(`/missions?limit=${limit}`, signal);
export const getMission = (id: string, signal?: AbortSignal) =>
  getJsonAuth<ApiMission>(`/missions/${encodeURIComponent(id)}`, signal);
export const getMissionEvents = (id: string, afterSeq = 0, signal?: AbortSignal) =>
  getJsonAuth<ApiEventRow[]>(`/missions/${encodeURIComponent(id)}/events?after_seq=${afterSeq}`, signal);
export const getSessionEvents = (id: string, afterSeq = 0, signal?: AbortSignal) =>
  getJsonAuth<ApiEventRow[]>(`/platform/sessions/${encodeURIComponent(id)}/events?after_seq=${afterSeq}`, signal);

// Approvals
export const getApprovals = (status = "pending", signal?: AbortSignal) =>
  getJsonAuth<ApiApproval[]>(`/approvals?status=${status}`, signal);
export const decideApproval = (id: string, decision: "approved" | "denied", reason = "", lesson = "") =>
  sendJsonAuth<{ id: string; status: string }>("POST", `/approvals/${id}/decide`, { decision, reason, lesson });

// Workflows (Agent Studio)
export const getWorkflows = (signal?: AbortSignal) => getJsonAuth<ApiWorkflow[]>("/workflows", signal);
export const getWorkflow = (id: string, signal?: AbortSignal) =>
  getJsonAuth<ApiWorkflow>(`/workflows/${encodeURIComponent(id)}`, signal);
export const createWorkflow = (body: Partial<ApiWorkflow> & { template_id?: string }) =>
  sendJsonAuth<ApiWorkflow>("POST", "/workflows", body as Record<string, unknown>);
export const updateWorkflow = (id: string, patch: Partial<ApiWorkflow>) =>
  sendJsonAuth<ApiWorkflow>("PATCH", `/workflows/${encodeURIComponent(id)}`, patch as Record<string, unknown>);
export const publishWorkflow = (id: string) =>
  sendJsonAuth<{ id: string; version: number; status: string }>("POST", `/workflows/${encodeURIComponent(id)}/publish`);
export const renderWorkflow = (id: string, values: Record<string, string>) =>
  sendJsonAuth<{ instruction: string; mode: "task" | "mission"; workflow_id: string; workspace_id: string | null }>(
    "POST", `/workflows/${encodeURIComponent(id)}/render`, { values });

// Platform
export const getTemplates = (signal?: AbortSignal) => {
  return fetch(`${API_V1}/platform/templates`, { cache: "no-store", signal })
    .then((r) => {
      if (!r.ok) throw new Error(`Failed to load templates (${r.status})`);
      return r.json() as Promise<ApiTemplate[]>;
    });
};
export const getPacks = (signal?: AbortSignal) => {
  return fetch(`${API_V1}/platform/packs`, { cache: "no-store", signal })
    .then((r) => {
      if (!r.ok) throw new Error(`Failed to load packs (${r.status})`);
      return r.json() as Promise<ApiPack[]>;
    });
};
export const getCapabilities = (signal?: AbortSignal) =>
  getJsonAuth<ApiCapabilities>("/platform/capabilities", signal);
export const getPlatformHealth = (signal?: AbortSignal) => {
  return fetch(`${API_V1}/platform/health`, { cache: "no-store", signal })
    .then((r) => {
      if (!r.ok) throw new Error(`Health check failed (${r.status})`);
      return r.json() as Promise<PlatformHealth>;
    });
};

// Runners (distributed execution)
// Session truth (Chapter IX): a live runner that cannot drive its desktop is
// neither online nor offline — it is in a specific, self-explaining state.
export type RunnerStatus =
  | "online" | "offline" | "busy"
  | "locked" | "logged_out" | "screen_unavailable"
  | "permission_denied" | "network_unavailable" | "unknown";

export interface RunnerReadiness {
  state?: string;
  detail?: string;
  fix?: string;
  can_execute?: boolean;
}

export interface ApiRunner {
  id: string;
  name: string;
  token_prefix: string;
  workspace_id: string | null;
  capabilities: Record<string, unknown>;
  current_session_id: string | null;
  last_heartbeat_at: string | null;
  status: RunnerStatus;
  readiness?: RunnerReadiness;
  created_at: string;
}

export interface NewRunner {
  runner: ApiRunner;
  token: string;        // shown once
  signing_key: string;  // shown once
}

export const getRunners = (signal?: AbortSignal) =>
  getJsonAuth<ApiRunner[]>("/runners", signal);
export const registerRunner = (name: string) =>
  sendJsonAuth<NewRunner>("POST", "/runners", { name });
export const dispatchRemoteRun = (instruction: string, runnerId?: string) =>
  sendJsonAuth<{ session_id: string; status: string }>("POST", "/runners/dispatch", {
    instruction, runner_id: runnerId ?? null,
  });

// Attention (unattended operations) — what needs a human right now
export interface ApiAttentionItem {
  id: string;
  org_id: string;
  workspace_id: string | null;
  kind: "run_failed" | "dead_letter" | "approval_pending" | "no_runner" | "schedule_blocked";
  ref: string;
  title: string;
  detail: Record<string, unknown>;
  session_id: string | null;
  workflow_id: string | null;
  status: "open" | "acked";
  created_at: string;
  acked_by?: string | null;
  acked_at?: string | null;
}

export const getAttention = (status: "open" | "acked" = "open", signal?: AbortSignal) =>
  getJsonAuth<ApiAttentionItem[]>(`/attention?status=${status}`, signal);
export const ackAttention = (id: string) =>
  sendJsonAuth<{ ok: boolean }>("POST", `/attention/${encodeURIComponent(id)}/ack`);

// Workflow run history + health
export interface ApiWorkflowRun {
  id: string;
  status: string;
  origin: string | null;
  error: string | null;
  execution_time: number | null;
  created_at: string;
  completed_at: string | null;
  retry_of: string | null;
  retry_count: number | null;
  runner_id: string | null;
}

export interface ApiWorkflowHealth {
  total: number;
  completed: number;
  failed: number;
  unverified: number;
  success_rate: number | null;
}

// Workflow Assurance (Chapter XIII) — the measured, VERIFIED reliability of a
// workflow, and the evidence-backed autonomy verdict it has earned.
export type AutonomyTier = "ready" | "supervised" | "in_the_loop" | "insufficient";
export interface ApiAutonomyVerdict {
  tier: AutonomyTier;
  headline: string;
  reason: string;
  next: string;
}
export interface ApiWorkflowAssurance {
  sample_size: number;
  verified_success_rate: number;
  completed: number;
  unverified: number;
  failed: number;
  calibration_error: number | null;
  calibration_samples: number;
  avg_duration_s: number | null;
  failure_taxonomy: Array<{ type: string; count: number }>;
  autonomy: ApiAutonomyVerdict;
}

export const getWorkflowRuns = (id: string, limit = 50, signal?: AbortSignal) =>
  getJsonAuth<{ runs: ApiWorkflowRun[]; health: ApiWorkflowHealth; assurance: ApiWorkflowAssurance }>(
    `/workflows/${encodeURIComponent(id)}/runs?limit=${limit}`, signal);

// Fleet autonomy posture (Chapter XIV) — the command center's trust pillar:
// how much of the autonomous workforce has earned self-operation, rolled up
// across every published workflow's verified assurance.
export interface ApiWorkflowCard {
  id: string;
  name: string;
  tier: AutonomyTier;
  verified_success_rate: number;
  sample_size: number;
  calibration_error: number | null;
}
export interface ApiFleetAutonomy {
  total_workflows: number;
  graded_workflows: number;
  by_tier: Record<AutonomyTier, number>;
  earned_autonomy: number;
  total_runs: number;
  fleet_verified_success_rate: number | null;
  confident_liars: ApiWorkflowCard[];
  workflows: ApiWorkflowCard[];
}
export const getFleetAutonomy = (signal?: AbortSignal) =>
  getJsonAuth<ApiFleetAutonomy>("/workflows/autonomy", signal);

// Workspace notification webhook (secret returned once, then write-only)
export const setWorkspaceWebhook = (orgId: string, workspaceId: string, url: string | null) =>
  sendJsonAuth<{ url: string | null; secret: string | null }>(
    "PUT", `/orgs/${orgId}/workspaces/${workspaceId}/webhook`, { url });

// Data-egress policy (Chapter IX) — what may leave this workspace's machines.
export type EgressMode = "allow" | "redact" | "local_only" | "deny";
export interface EgressPolicy {
  mode: EgressMode;
  redact: string[];
  custom_patterns: string[];
}
export const setWorkspaceEgress = (
  orgId: string, workspaceId: string, body: { mode: EgressMode; redact?: string[]; custom_patterns?: string[] },
) => sendJsonAuth<EgressPolicy>("PUT", `/orgs/${orgId}/workspaces/${workspaceId}/egress`, body);

// Learning consent (Chapter IX foundation) — what PerceptAI may learn.
export interface LearningPolicy {
  tiers: Record<string, boolean>;
  anonymization: string;
  derivative_data: string;
  knowledge_owner: string;
  policy_version: string;
}
export interface LearningInfo {
  policy: LearningPolicy;
  tiers: Record<string, { grants: string; benefit: string; shares_outside_workspace: string }>;
  policy_version: string;
  history: Array<{ tier: string; granted: boolean; actor_email: string; created_at: string; policy_version: string }>;
}
export const getWorkspaceLearning = (orgId: string, workspaceId: string, signal?: AbortSignal) =>
  getJsonAuth<LearningInfo>(`/orgs/${orgId}/workspaces/${workspaceId}/learning`, signal);
export const setWorkspaceLearning = (
  orgId: string, workspaceId: string, body: { tiers: Record<string, boolean>; anonymization?: string },
) => sendJsonAuth<{ policy: LearningPolicy; changes: unknown[] }>(
  "PUT", `/orgs/${orgId}/workspaces/${workspaceId}/learning`, body);

// Business Memory (Milestone C2) — organizational intelligence that compounds.
export interface ApiMemoryLesson {
  id: string;
  kind: "correction" | "recovery" | "quirk" | "policy" | "preference" | "optimization";
  scope: string;
  subject: string;
  lesson: string;
  source: "taught" | "observed";
  taught_by?: string | null;
  evidence: Array<Record<string, string>>;
  confidence: number;
  times_reinforced: number;
  last_reinforced_at: string;
  created_at: string;
}
export interface ApiMemoryInsight {
  kind: string;
  capability: string;
  workspace_id: string | null;
  consecutive_approvals: number;
  recommendation: string;
}
export const getMemory = (signal?: AbortSignal) =>
  getJsonAuth<{ lessons: ApiMemoryLesson[]; insights: ApiMemoryInsight[] }>("/memory", signal);
export const teachMemory = (lesson: string, subject = "general",
                            kind = "correction", scope = "org") =>
  sendJsonAuth<ApiMemoryLesson>("POST", "/memory/teach", { lesson, subject, kind, scope });
export const forgetMemory = (id: string) =>
  sendJsonAuth<{ archived: string }>("DELETE", `/memory/${encodeURIComponent(id)}`);

// Workforce Intelligence (Milestone C3) — the workforce's self-review,
// computed live from measured rows. Findings carry their evidence.
export interface ApiIntelligenceFinding {
  kind: "strength" | "struggle" | "automation_opportunity" | "intervention"
      | "approval_friction" | "policy_candidate";
  severity: "high" | "medium" | "info";
  headline: string;
  detail: string;
  evidence: Record<string, unknown>;
}
export interface ApiIntelligenceBriefing {
  period_days: number;
  coverage: { operations_analyzed: number; sufficient: boolean; note: string };
  findings: ApiIntelligenceFinding[];
}
export const getIntelligenceBriefing = (signal?: AbortSignal) =>
  getJsonAuth<ApiIntelligenceBriefing>("/intelligence/briefing", signal);

// Organizational Graph (Milestone D) — discoveries from measured
// relationships: evidence, confidence, departments, impact, one action.
export interface ApiDiscovery {
  kind: "duplicated_work" | "systemic_obstacle" | "learning_transfer" | "redundant_approvals";
  severity: "high" | "medium" | "info";
  headline: string;
  detail: string;
  evidence: Record<string, unknown>;
  confidence: number;
  affected_departments: string[];
  business_impact: string;
  recommended_action: string;
}
export interface ApiDiscoveries {
  period_days: number;
  coverage: { sufficient: boolean; note: string };
  discoveries: ApiDiscovery[];
}
export const getDiscoveries = (signal?: AbortSignal) =>
  getJsonAuth<ApiDiscoveries>("/intelligence/discoveries", signal);

// The Organizational Record (Phase 3) — grounded search + one timeline.
export interface ApiSearchHit {
  type: "lesson" | "workflow" | "operation" | "approval" | "attention" | "audit";
  id: string;
  title: string;
  snippet: string;
  status: string;
  when: string | null;
  relevance: number;
  ref: { page: string; id?: string };
}
export const searchOrg = (q: string, signal?: AbortSignal) =>
  getJsonAuth<{ query: string; hits: ApiSearchHit[]; sources_skipped: string[]; note: string }>(
    `/search?q=${encodeURIComponent(q)}`, signal);
export const getTimeline = (limit = 50, signal?: AbortSignal) =>
  getJsonAuth<{ entries: Array<Omit<ApiSearchHit, "snippet" | "relevance">>; sources_skipped: string[]; note: string }>(
    `/timeline?limit=${limit}`, signal);

-- Sprint 4: Distributed Execution (the Runner).
-- Additive migration — existing tables and rows keep working untouched.
-- Run after 002_platform.sql. The control plane dispatches SIGNED work to
-- thin runners that execute through the ONE runtime; this migration adds the
-- runner registry and turns `sessions` into the work queue (reuse over a new
-- table — one source of truth for an execution). Each statement lives in
-- exactly one file.

-- ------------------------------------------------------------- runners
-- One row per registered runner (a machine that executes work). Identity is
-- a hashed token (SHA-256, like api_keys); status is derived from heartbeat
-- and current claim. Capabilities let the control plane route work (desktop
-- available, OS, engine version, tags) without the engine ever changing.
CREATE TABLE runners (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL,  -- optional pin
  name TEXT NOT NULL,
  token_hash TEXT UNIQUE NOT NULL,          -- SHA-256 of the runner token (rk_*)
  token_prefix TEXT NOT NULL,               -- display only
  status TEXT DEFAULT 'offline',            -- offline | online | busy
  capabilities JSONB DEFAULT '{}',          -- {desktop, os, engine_version, tags:[]}
  current_session_id UUID,                  -- the session it is executing, or null
  last_heartbeat_at TIMESTAMPTZ,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX runners_org ON runners (org_id, status, last_heartbeat_at DESC);

-- ------------------------------------------- sessions become the work queue
-- A remotely-dispatched session is created with status='queued'; a runner
-- claims it (status='claimed' -> 'running') under a heartbeat-renewed lease.
-- Local (API-host) execution is unchanged: it never sets these columns and
-- never uses the 'queued'/'claimed' statuses. Remote is purely additive.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS runner_id UUID REFERENCES runners(id) ON DELETE SET NULL;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS claim_expires_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS sessions_queue ON sessions (org_id, status, created_at)
  WHERE status = 'queued';

-- ---------------------------------------------- atomic claim (race-safe)
-- Thousands of runners long-poll concurrently; two must never claim the same
-- session. FOR UPDATE SKIP LOCKED picks exactly one queued row per caller and
-- leaves the rest for other runners. Returns the claimed session, or nothing.
CREATE OR REPLACE FUNCTION claim_next_session(
  p_runner_id UUID,
  p_org_id UUID,
  p_workspace_id UUID,     -- runner's workspace pin, or NULL for org-wide
  p_lease_seconds INT
) RETURNS SETOF sessions AS $$
  UPDATE sessions s
  SET status = 'claimed',
      runner_id = p_runner_id,
      claim_expires_at = NOW() + make_interval(secs => p_lease_seconds)
  WHERE s.id = (
    SELECT id FROM sessions
    WHERE status = 'queued'
      AND org_id = p_org_id
      AND (p_workspace_id IS NULL OR workspace_id = p_workspace_id OR workspace_id IS NULL)
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
  )
  RETURNING s.*;
$$ LANGUAGE sql;

-- ----------------------------------------- reclaim expired leases (dead runners)
-- A runner that dies mid-run stops renewing its lease. This returns its
-- session to the queue so another runner can pick it up — honest recovery,
-- never a silently stuck run. Callable on a cadence by the control plane.
CREATE OR REPLACE FUNCTION reclaim_expired_sessions() RETURNS SETOF sessions AS $$
  UPDATE sessions s
  SET status = 'queued', runner_id = NULL, claim_expires_at = NULL
  WHERE s.status IN ('claimed', 'running')
    AND s.claim_expires_at IS NOT NULL
    AND s.claim_expires_at < NOW()
  RETURNING s.*;
$$ LANGUAGE sql;

-- ------------------------------------------------- durable execution control
-- The restart-surviving version of Sprint 3's in-process control channel.
-- For a REMOTE execution the operator's pause/resume/stop and approval
-- decisions land here; the runner's RemoteControlChannel reads them over the
-- network. Local (API-host) execution still uses the in-process channel and
-- never touches this table — the same control API serves both, transparently.
CREATE TABLE execution_control (
  session_id UUID PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
  state TEXT DEFAULT 'running',          -- running | paused | stopping
  approval_request JSONB,                -- the pending ApprovalRequest, or null
  approval_decision JSONB,               -- {request_id, decision, decided_by, reason}
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------------ RLS
-- The API talks through the service role; RLS stays on as defense in depth.
ALTER TABLE runners ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_control ENABLE ROW LEVEL SECURITY;

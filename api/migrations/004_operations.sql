-- Sprint 8: Unattended Operations (lights-out production automation).
-- Additive migration — run after 003_runners.sql. Scheduled workflow runs go
-- through the ONE work queue (sessions) to a declared execution target, under
-- a declared failure policy, and reach a human only through the Attention
-- surface. No new execution path anywhere: the queue, the claim function and
-- the runner protocol are the Sprint 4 ones, extended with data.

-- --------------------------------------------- sessions: dispatch metadata
-- workflow_id links a run back to the workflow that produced it (health,
-- failure policy). origin says who created the run ('user' | 'schedule').
-- retry_of/retry_count are the honest lineage of a policy retry: a retry is
-- a NEW session linked to the failed one — history is never rewritten.
-- target_runner_id pins a queued session to one runner ("the finance VM");
-- NULL means any eligible runner may claim it.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS workflow_id UUID REFERENCES workflows(id) ON DELETE SET NULL;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS origin TEXT DEFAULT 'user';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS retry_of UUID REFERENCES sessions(id) ON DELETE SET NULL;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS retry_count INT DEFAULT 0;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS target_runner_id UUID REFERENCES runners(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS sessions_workflow ON sessions (workflow_id, created_at DESC)
  WHERE workflow_id IS NOT NULL;

-- ------------------------------------------------ claim honors runner pins
-- Supersedes the 003 definition (same contract, one new filter): a session
-- pinned to a specific runner is only ever handed to that runner; unpinned
-- work is claimable by any eligible runner, exactly as before.
CREATE OR REPLACE FUNCTION claim_next_session(
  p_runner_id UUID,
  p_org_id UUID,
  p_workspace_id UUID,     -- runner's workspace pin, or NULL for org-wide
  p_lease_seconds INT
) RETURNS SETOF sessions AS $$
  UPDATE sessions s
  SET status = 'claimed',
      runner_id = p_runner_id,
      claim_expires_at = NOW() + make_interval(secs => p_lease_seconds),
      attempts = attempts + 1          -- each claim counts, so retries are bounded
  WHERE s.id = (
    SELECT id FROM sessions
    WHERE status = 'queued'
      AND org_id = p_org_id
      AND (p_workspace_id IS NULL OR workspace_id = p_workspace_id OR workspace_id IS NULL)
      AND (target_runner_id IS NULL OR target_runner_id = p_runner_id)
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
  )
  RETURNING s.*;
$$ LANGUAGE sql;

-- ------------------------------------------------------- attention surface
-- "What needs a human right now" — the unattended-operations inbox. Fed only
-- from facts the plane already persists (terminal failures, dead-letters,
-- pending approvals, unreachable targets); acked by an operator. One OPEN
-- item per (org, kind, ref) so a repeating condition never floods the inbox.
CREATE TABLE attention_items (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL,
  kind TEXT NOT NULL,             -- run_failed | dead_letter | approval_pending | no_runner | schedule_blocked
  ref TEXT NOT NULL,              -- dedup key within kind (session id, workflow id, ...)
  title TEXT NOT NULL,
  detail JSONB DEFAULT '{}',
  session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
  workflow_id UUID REFERENCES workflows(id) ON DELETE SET NULL,
  status TEXT DEFAULT 'open',     -- open | acked
  created_at TIMESTAMPTZ DEFAULT NOW(),
  acked_by UUID REFERENCES users(id),
  acked_at TIMESTAMPTZ
);
CREATE INDEX attention_org ON attention_items (org_id, status, created_at DESC);
CREATE UNIQUE INDEX attention_open_dedup ON attention_items (org_id, kind, ref)
  WHERE status = 'open';

-- ------------------------------------------- workspace notification webhook
-- One outbound webhook per workspace. The URL is readable; the HMAC signing
-- secret is write-only (returned once when set, never again) so receivers
-- can verify payload authenticity. Delivery is best-effort with backoff and
-- never blocks dispatch or execution.
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS notify_webhook_url TEXT;
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS notify_webhook_secret TEXT;

-- ------------------------------------------------------------------ RLS
ALTER TABLE attention_items ENABLE ROW LEVEL SECURITY;

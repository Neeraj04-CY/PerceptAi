-- 006: Business Memory — organizational intelligence that compounds.
-- Every correction, approval lesson, recovery pattern and application quirk
-- becomes a durable, org-scoped lesson that future runs RECALL into planning.
-- Additive only; the pre-006 surface keeps working without it.

CREATE TABLE IF NOT EXISTS business_memory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id UUID NULL REFERENCES workspaces(id) ON DELETE SET NULL,
  -- correction | recovery | quirk | policy | preference | optimization
  kind TEXT NOT NULL,
  -- Where the lesson applies: app:<name> | workflow:<id> | org.
  -- App-scoped lessons propagate across every workflow touching that app —
  -- Finance's SAP lesson reaches Procurement immediately.
  scope TEXT NOT NULL DEFAULT 'org',
  subject TEXT NOT NULL,           -- what it's about (app, field, vendor...)
  lesson TEXT NOT NULL,            -- the reusable statement, plain language
  source TEXT NOT NULL,            -- taught | observed
  taught_by UUID NULL,             -- user id when source='taught'
  evidence JSONB DEFAULT '[]',     -- bounded refs: session/approval ids
  confidence REAL DEFAULT 0.7,
  times_reinforced INT DEFAULT 1,
  dedup_hash TEXT NOT NULL,        -- sha256(scope + normalized lesson)
  last_reinforced_at TIMESTAMPTZ DEFAULT now(),
  created_at TIMESTAMPTZ DEFAULT now(),
  archived BOOLEAN DEFAULT false
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bm_dedup ON business_memory(org_id, dedup_hash);
CREATE INDEX IF NOT EXISTS idx_bm_org ON business_memory(org_id, archived, kind);

-- Chapter Omega: platform foundations.
-- Additive migration — existing tables and rows keep working untouched.
-- Run after database.sql (001). Everything here is architecture-first:
-- plans are data, RBAC is data, policy is data. No behavior is hardcoded.

-- ---------------------------------------------------------------- plans
-- Plan limits live on the plan row — the ONLY source of plan behavior.
ALTER TABLE plans ADD COLUMN IF NOT EXISTS limits JSONB NOT NULL DEFAULT '{}';

UPDATE plans SET limits = '{"max_parallel": 2, "max_work_orders": 6, "max_mission_duration_s": 1800, "max_total_cost": 25}' WHERE id = 'free';
UPDATE plans SET limits = '{"max_parallel": 4, "max_work_orders": 12, "max_mission_duration_s": 3600, "max_total_cost": 100}' WHERE id = 'builder';
UPDATE plans SET limits = '{"max_parallel": 8, "max_work_orders": 24, "max_mission_duration_s": 7200, "max_total_cost": 500}' WHERE id = 'scale';

INSERT INTO plans (id, name, monthly_executions, price_usd, limits)
VALUES ('enterprise', 'Enterprise', 999999, 499,
        '{"max_parallel": 16, "max_work_orders": 64, "max_mission_duration_s": 14400, "max_total_cost": 5000}')
ON CONFLICT (id) DO NOTHING;

-- -------------------------------------------------------- organizations
CREATE TABLE organizations (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  plan_id TEXT REFERENCES plans(id) DEFAULT 'free',
  is_personal BOOLEAN DEFAULT FALSE,
  created_by UUID REFERENCES users(id),
  settings JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- RBAC as data: one row per membership, role checked in api/rbac.py.
CREATE TABLE organization_members (
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member',  -- owner | admin | member | viewer
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (org_id, user_id)
);

-- Workspaces scope execution, policy, secrets and audit. `environment`
-- is data (production/staging/dev), never a branch in code.
CREATE TABLE workspaces (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  description TEXT DEFAULT '',
  environment TEXT DEFAULT 'production',
  -- {approval_capabilities: [], allowed_capabilities: null, max_cost_per_mission: null}
  policy JSONB DEFAULT '{}',
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (org_id, slug)
);

-- ------------------------------------------------------------- secrets
-- Values are Fernet-encrypted server-side (api/secrets_crypto.py); the
-- plaintext never lands in the database or the API response.
CREATE TABLE secrets (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  ciphertext TEXT NOT NULL,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (org_id, workspace_id, name)
);

-- ----------------------------------------------------------- workflows
-- A workflow is a named, versioned, parametrized instruction: the Agent
-- Studio unit. Branching/parallelism live in the engine's WorkGraph —
-- there is deliberately no second workflow interpreter.
CREATE TABLE workflows (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  description TEXT DEFAULT '',
  instruction TEXT NOT NULL,          -- plain English with {{variable}} slots
  variables JSONB DEFAULT '[]',       -- [{name,label,type,default,required,description}]
  mode TEXT DEFAULT 'task',           -- task | mission
  policy JSONB DEFAULT '{}',          -- capability allowlist / budget overrides
  status TEXT DEFAULT 'draft',        -- draft | published | archived
  version INTEGER DEFAULT 0,          -- latest published version, 0 = never
  schedule JSONB,                     -- {enabled, interval_minutes, next_run_at}
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Immutable snapshots created on publish; runs reference a version.
CREATE TABLE workflow_versions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  workflow_id UUID REFERENCES workflows(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  instruction TEXT NOT NULL,
  variables JSONB DEFAULT '[]',
  mode TEXT DEFAULT 'task',
  policy JSONB DEFAULT '{}',
  published_by UUID REFERENCES users(id),
  published_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (workflow_id, version)
);

-- ------------------------------------------------------------ missions
-- One row per workforce mission (the Chapter 5 layer). Mirrors sessions:
-- the full MissionResult is persisted as JSONB, the event stream in events.
CREATE TABLE missions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  workspace_id UUID REFERENCES workspaces(id),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  api_key_id UUID REFERENCES api_keys(id),
  workflow_id UUID REFERENCES workflows(id) ON DELETE SET NULL,
  instruction TEXT NOT NULL,
  status TEXT DEFAULT 'pending',      -- running | completed | partial | failed | cancelled
  result JSONB,                       -- MissionResult.to_dict()
  metrics JSONB,                      -- MissionMetrics.to_dict()
  error TEXT,
  duration_s FLOAT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);
CREATE INDEX missions_user ON missions (user_id, created_at DESC);
CREATE INDEX missions_org ON missions (org_id, created_at DESC);

-- ----------------------------------------------------------- approvals
-- Durable approval records wired into MissionPolicy's approver hook.
-- Grant-ahead model: an approved row for (workspace, capability) is
-- consumed by the next matching dispatch; a missing grant creates a
-- pending row and the order is denied honestly (never silently run).
CREATE TABLE approvals (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
  mission_id UUID,
  capability TEXT NOT NULL,
  objective TEXT DEFAULT '',
  status TEXT DEFAULT 'pending',      -- pending | approved | denied | consumed
  requested_by UUID REFERENCES users(id),
  decided_by UUID REFERENCES users(id),
  reason TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  decided_at TIMESTAMPTZ,
  consumed_at TIMESTAMPTZ
);
CREATE INDEX approvals_org ON approvals (org_id, status, created_at DESC);

-- -------------------------------------------------------------- events
-- The canonical event stream, persisted. One row per TaskEvent; replay,
-- mission timelines, reasoning traces and evidence lineage all read this.
CREATE TABLE events (
  id BIGSERIAL PRIMARY KEY,
  owner_kind TEXT NOT NULL,           -- 'session' | 'mission'
  owner_id UUID NOT NULL,
  seq INTEGER NOT NULL,
  type TEXT NOT NULL,
  task_id TEXT DEFAULT '',
  ts TIMESTAMPTZ,
  payload JSONB DEFAULT '{}'
);
CREATE INDEX events_owner ON events (owner_kind, owner_id, seq);

-- ------------------------------------------------------------ audit log
-- Administrative actions (member changes, secrets, policy edits, key
-- lifecycle, approvals). Execution audit is the events table; this is
-- the control-plane trail.
CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id UUID,
  actor_id UUID,
  actor_email TEXT DEFAULT '',
  action TEXT NOT NULL,               -- e.g. 'member.added', 'secret.created'
  target TEXT DEFAULT '',
  detail JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX audit_org ON audit_log (org_id, created_at DESC);

-- --------------------------------------------- scope existing resources
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id);
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id);
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id);

-- ------------------------------------------------------------------ RLS
-- The API talks through the service role; RLS stays on as defense in depth.
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE missions ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

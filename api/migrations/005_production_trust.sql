-- Chapter IX: Production Trust.
-- Additive migration - run after 004_operations.sql. Nothing here changes an
-- existing execution path: it records session truth, cryptographic runner
-- identity, data-egress policy and learning consent, all as DATA.

-- ------------------------------------------------------- session truth
-- The host's own report of whether it can drive a desktop right now:
-- {state, detail, fix, can_execute}. Liveness stays derived from the
-- heartbeat; readiness is the HOST's fact, and the two compose into the
-- status an operator sees. A live-but-locked runner is 'locked', not 'online'.
ALTER TABLE runners ADD COLUMN IF NOT EXISTS readiness JSONB DEFAULT '{}';

-- --------------------------------------------------- runner identity (mutual)
-- The runner generates an Ed25519 keypair at registration and sends ONLY its
-- public key; the private key never leaves the host. The plane verifies every
-- runner request against this key, so identity is cryptographic rather than a
-- shared bearer secret: a stolen credential compromises exactly one runner.
-- `key_algorithm` lets HMAC-era runners keep working through the migration.
ALTER TABLE runners ADD COLUMN IF NOT EXISTS public_key TEXT;
ALTER TABLE runners ADD COLUMN IF NOT EXISTS key_algorithm TEXT DEFAULT 'hmac-sha256';
ALTER TABLE runners ADD COLUMN IF NOT EXISTS key_registered_at TIMESTAMPTZ;

-- ------------------------------------------------------------ egress policy
-- What may leave the machine, why, and to whom. Policy is data (never a
-- hardcoded security decision): {mode, redact, allow_vision}.
--   deny       - nothing observed may be sent to any model
--   allow      - default; observations may be sent
--   redact     - observations are sent with sensitive spans removed
--   local_only - no PIXELS leave (vision provider disabled); text may, per redact
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS egress_policy JSONB DEFAULT '{}';

-- ---------------------------------------------------------- learning consent
-- The legal foundation of the flywheel, present before the first contract is
-- signed. Nothing consumes this yet (organizational learning is deliberately
-- NOT built here) - but a workspace can already declare what PerceptAI may
-- learn from its executions, and consent is an immutable, attributable record.
--   tier: workspace_only | anonymized_priors | model_improvement
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS learning_policy JSONB DEFAULT '{}';

CREATE TABLE learning_consent (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
  tier TEXT NOT NULL,                  -- the tier being granted
  policy JSONB NOT NULL DEFAULT '{}',  -- the exact policy snapshot consented to
  policy_version TEXT NOT NULL,        -- version of the terms consented to
  granted BOOLEAN NOT NULL,            -- grant or revoke; history is append-only
  actor_id UUID REFERENCES users(id),
  actor_email TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX learning_consent_scope ON learning_consent (org_id, workspace_id, created_at DESC);

-- Consent is never mutated, only superseded: the current state is the latest
-- row per (workspace, tier). An auditor can reconstruct who granted what, when,
-- and under which version of the terms.

ALTER TABLE learning_consent ENABLE ROW LEVEL SECURITY;

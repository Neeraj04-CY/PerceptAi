-- Baseline schema (001). Fresh installs: run this file first, then every
-- file in api/migrations/ in order (002_platform.sql adds organizations,
-- workspaces, RBAC, secrets, workflows, missions, approvals, events and
-- audit). Each statement lives in exactly one file — never copy them here.

-- Users table
CREATE TABLE users (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- API Keys table
CREATE TABLE api_keys (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  key_hash TEXT UNIQUE NOT NULL,
  key_prefix TEXT NOT NULL,
  name TEXT DEFAULT 'Default Key',
  is_active BOOLEAN DEFAULT TRUE,
  last_used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sessions table (every task execution)
CREATE TABLE sessions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  api_key_id UUID REFERENCES api_keys(id),
  instruction TEXT NOT NULL,
  status TEXT DEFAULT 'pending',
  steps JSONB DEFAULT '[]',
  result JSONB,
  error TEXT,
  execution_time FLOAT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

-- Usage tracking
CREATE TABLE usage (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  session_id UUID REFERENCES sessions(id),
  month TEXT NOT NULL,
  executions INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, month)
);

-- Plans table
CREATE TABLE plans (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  monthly_executions INTEGER NOT NULL,
  price_usd INTEGER NOT NULL
);

INSERT INTO plans VALUES
  ('free', 'Starter', 100, 0),
  ('builder', 'Builder', 10000, 29),
  ('scale', 'Scale', 999999, 99);

-- User plans
CREATE TABLE user_plans (
  user_id UUID REFERENCES users(id) PRIMARY KEY,
  plan_id TEXT REFERENCES plans(id) DEFAULT 'free',
  started_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS Policies
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_plans ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users own data" ON users FOR ALL USING (auth.uid()::text = id::text);
CREATE POLICY "Users own keys" ON api_keys FOR ALL USING (auth.uid()::text = user_id::text);
CREATE POLICY "Users own sessions" ON sessions FOR ALL USING (auth.uid()::text = user_id::text);
CREATE POLICY "Users own usage" ON usage FOR ALL USING (auth.uid()::text = user_id::text);
CREATE POLICY "Users own plan" ON user_plans FOR ALL USING (auth.uid()::text = user_id::text);
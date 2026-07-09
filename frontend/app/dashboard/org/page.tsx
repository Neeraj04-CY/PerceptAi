"use client";

/** Organization: members & RBAC, workspaces & policy, secrets vault,
 * audit trail and plan usage — the company-facing control plane. */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, KeySquare, Plus, ScrollText, Trash2, Users } from "lucide-react";
import { cn, isAbortError } from "@/lib/utils";
import { PageHeader } from "@/components/dashboard/page-header";
import {
  ApiAuditEntry,
  ApiCapabilities,
  ApiMember,
  ApiOrgDetail,
  ApiSecretMeta,
  ApiWorkspace,
  OrgUsage,
  addMember,
  createSecret,
  createWorkspace,
  deleteSecret,
  getAudit,
  getCapabilities,
  getMembers,
  getOrgDetail,
  getOrgs,
  getOrgUsage,
  getSecrets,
  removeMember,
  updateMemberRole,
  setWorkspaceWebhook,
  updateWorkspacePolicy,
} from "@/lib/api";

const TABS = ["overview", "members", "workspaces", "secrets", "audit"] as const;
const ROLES = ["owner", "admin", "member", "viewer"];

export default function OrganizationPage() {
  const router = useRouter();
  const [tab, setTab] = useState<(typeof TABS)[number]>("overview");
  const [org, setOrg] = useState<ApiOrgDetail | null>(null);
  const [members, setMembers] = useState<ApiMember[]>([]);
  const [secrets, setSecrets] = useState<ApiSecretMeta[]>([]);
  const [audit, setAudit] = useState<ApiAuditEntry[]>([]);
  const [usage, setUsage] = useState<OrgUsage | null>(null);
  const [capabilities, setCapabilities] = useState<ApiCapabilities | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const orgs = await getOrgs(signal);
      if (!orgs.length) throw new Error("No organization");
      const detail = await getOrgDetail(orgs[0].id, signal);
      setOrg(detail);
      const [m, s, a, u, c] = await Promise.allSettled([
        getMembers(detail.id, signal),
        getSecrets(detail.id, signal),
        getAudit(detail.id, 100, signal),
        getOrgUsage(detail.id, signal),
        getCapabilities(signal),
      ]);
      if (m.status === "fulfilled") setMembers(m.value);
      if (s.status === "fulfilled") setSecrets(s.value);
      if (a.status === "fulfilled") setAudit(a.value);
      if (u.status === "fulfilled") setUsage(u.value);
      if (c.status === "fulfilled") setCapabilities(c.value);
    } catch (e) {
      if (isAbortError(e)) return;
      if (String(e).includes("Unauthorized")) router.replace("/signin");
      else setError(e instanceof Error ? e.message : "Failed to load organization");
    }
  }, [router]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-400/20 bg-red-400/[0.04] px-4 py-3 text-[12px] text-red-300">
        {error}
      </div>
    );
  }
  if (!org) {
    return <div className="h-96 rounded-xl bg-white/[0.04] animate-pulse" />;
  }

  const canManage = org.role === "owner" || org.role === "admin";

  return (
    <div className="space-y-6">
      <PageHeader
        title={org.name}
        subtitle={`${org.plan.name} plan · ${org.member_count} member${org.member_count === 1 ? "" : "s"} · your role: ${org.role}`}
      />
      <div className="flex items-center gap-1 rounded-lg border border-white/[0.07] bg-white/[0.02] p-1 w-fit overflow-x-auto no-scrollbar">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
                  className={cn("rounded-md px-3 h-8 font-mono text-[10px] uppercase tracking-wider transition-colors whitespace-nowrap",
                                tab === t ? "bg-white/[0.07] text-white" : "text-white/40 hover:text-white")}>
            {t}
          </button>
        ))}
      </div>

      {tab === "overview" && <Overview org={org} usage={usage} members={members} secrets={secrets} />}
      {tab === "members" && (
        <MembersTab members={members} canManage={canManage} actorRole={org.role}
                    orgId={org.id} onChanged={() => load()} />
      )}
      {tab === "workspaces" && (
        <WorkspacesTab org={org} capabilities={capabilities} canManage={canManage}
                       onChanged={() => load()} />
      )}
      {tab === "secrets" && (
        <SecretsTab orgId={org.id} secrets={secrets} workspaces={org.workspaces}
                    canManage={canManage} onChanged={() => load()} />
      )}
      {tab === "audit" && <AuditTab audit={audit} />}
    </div>
  );
}

/* -------------------------------------------------------------- shared */

function Card({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <section className="glass rounded-xl p-4">
      {title && (
        <h2 className="mb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">{title}</h2>
      )}
      {children}
    </section>
  );
}

/* ------------------------------------------------------------ overview */

function Overview({ org, usage, members, secrets }: {
  org: ApiOrgDetail; usage: OrgUsage | null; members: ApiMember[]; secrets: ApiSecretMeta[];
}) {
  const pct = usage && usage.executions_limit
    ? Math.min(100, (usage.executions_used / usage.executions_limit) * 100) : 0;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
      <Card title={`Usage — ${usage?.month ?? ""}`}>
        <div className="flex items-baseline justify-between">
          <span className="text-[22px] font-medium tabular-nums text-white">
            {(usage?.executions_used ?? 0).toLocaleString()}
          </span>
          <span className="font-mono text-[10px] text-white/35">
            of {(usage?.executions_limit ?? 0).toLocaleString()} executions
          </span>
        </div>
        <div className="mt-2 h-1 rounded-full bg-white/[0.06] overflow-hidden">
          <div className={cn("h-full rounded-full",
                             pct > 90 ? "bg-red-400" : pct > 70 ? "bg-amber-300" : "bg-accent")}
               style={{ width: `${pct}%` }} />
        </div>
        {usage?.workforce_limits && (
          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1.5">
            {[
              ["parallel specialists", usage.workforce_limits.max_parallel],
              ["orders per mission", usage.workforce_limits.max_work_orders],
              ["mission budget", `${usage.workforce_limits.max_total_cost} cr`],
              ["mission wall clock", `${Math.round((usage.workforce_limits.max_mission_duration_s ?? 0) / 60)}m`],
            ].map(([k, v]) => (
              <div key={String(k)} className="flex items-center justify-between">
                <dt className="font-mono text-[9px] uppercase tracking-wider text-white/30">{k}</dt>
                <dd className="font-mono text-[11px] text-white/65 tabular-nums">{String(v)}</dd>
              </div>
            ))}
          </dl>
        )}
      </Card>
      <Card title="At a glance">
        <div className="space-y-2.5">
          {[
            { icon: Users, label: "Members", value: `${members.length}` },
            { icon: Building2, label: "Workspaces", value: `${org.workspaces.length}` },
            { icon: KeySquare, label: "Secrets", value: `${secrets.length}` },
            { icon: ScrollText, label: "Plan", value: org.plan.name },
          ].map((row) => (
            <div key={row.label} className="flex items-center gap-3">
              <row.icon size={13} className="text-white/30" />
              <span className="flex-1 text-[12px] text-white/55">{row.label}</span>
              <span className="font-mono text-[12px] text-white/80">{row.value}</span>
            </div>
          ))}
        </div>
        <p className="mt-4 text-[10px] leading-relaxed text-white/30">
          Plan limits are data — upgrading changes numbers, never behavior.
          Workspace policies (approvals, capability allowlists) live under
          the Workspaces tab.
        </p>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------- members */

function MembersTab({ members, canManage, actorRole, orgId, onChanged }: {
  members: ApiMember[]; canManage: boolean; actorRole: string;
  orgId: string; onChanged: () => void;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const grantable = ROLES.slice(ROLES.indexOf(actorRole));

  const submit = async () => {
    if (!email.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await addMember(orgId, email.trim(), role);
      setEmail("");
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add member");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {canManage && (
        <Card title="Add member">
          <div className="flex flex-wrap items-center gap-2">
            <input value={email} onChange={(e) => setEmail(e.target.value)}
                   placeholder="teammate@company.com" type="email"
                   className="h-9 min-w-[220px] flex-1 rounded-md border border-white/[0.08] bg-black/30 px-3 text-[13px] text-white focus:outline-none focus:border-accent/35" />
            <select value={role} onChange={(e) => setRole(e.target.value)}
                    className="h-9 rounded-md border border-white/[0.08] bg-black/30 px-2 font-mono text-[11px] uppercase tracking-wider text-white/70 focus:outline-none">
              {grantable.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <button onClick={submit} disabled={busy || !email.trim()}
                    className="inline-flex h-9 items-center gap-1.5 rounded-md bg-accent/15 px-3 font-mono text-[11px] uppercase tracking-wider text-accent hover:bg-accent/25 transition-colors disabled:opacity-50">
              <Plus size={12} /> Add
            </button>
          </div>
          <p className="mt-2 text-[10px] text-white/30">
            The teammate needs an existing PerceptAI account (email invites are on the roadmap).
          </p>
          {error && <p className="mt-2 text-[12px] text-red-300">{error}</p>}
        </Card>
      )}
      <Card title={`Members · ${members.length}`}>
        <div className="divide-y divide-white/[0.04]">
          {members.map((member) => (
            <MemberRow key={member.user_id} member={member} orgId={orgId}
                       canManage={canManage} grantable={grantable} onChanged={onChanged} />
          ))}
        </div>
      </Card>
    </div>
  );
}

function MemberRow({ member, orgId, canManage, grantable, onChanged }: {
  member: ApiMember; orgId: string; canManage: boolean;
  grantable: string[]; onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent/50 to-accent/15 text-[10px] font-medium text-black">
        {(member.email || "?").slice(0, 2).toUpperCase()}
      </div>
      <span className="min-w-0 flex-1 truncate text-[13px] text-white/80">{member.email}</span>
      {canManage && grantable.includes(member.role) && member.role !== "owner" ? (
        <select value={member.role} disabled={busy}
                onChange={async (e) => {
                  setBusy(true);
                  try { await updateMemberRole(orgId, member.user_id, e.target.value); onChanged(); }
                  catch { /* row stays; refresh shows truth */ }
                  finally { setBusy(false); }
                }}
                className="h-7 rounded-md border border-white/[0.08] bg-black/30 px-2 font-mono text-[10px] uppercase tracking-wider text-white/60 focus:outline-none">
          {grantable.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      ) : (
        <span className="font-mono text-[10px] uppercase tracking-wider text-white/40">{member.role}</span>
      )}
      {canManage && member.role !== "owner" && (
        <button disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try { await removeMember(orgId, member.user_id); onChanged(); }
                  catch { /* refresh shows truth */ }
                  finally { setBusy(false); }
                }}
                className="rounded-md p-1.5 text-white/25 hover:text-red-300 hover:bg-red-400/10 transition-colors"
                aria-label={`Remove ${member.email}`}>
          <Trash2 size={13} />
        </button>
      )}
    </div>
  );
}

/* ---------------------------------------------------------- workspaces */

function WorkspacesTab({ org, capabilities, canManage, onChanged }: {
  org: ApiOrgDetail; capabilities: ApiCapabilities | null;
  canManage: boolean; onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [environment, setEnvironment] = useState("production");
  const [busy, setBusy] = useState(false);
  const allCapabilities = capabilities?.capabilities ?? [];

  return (
    <div className="space-y-4">
      {canManage && (
        <Card title="New workspace">
          <div className="flex flex-wrap items-center gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Finance Ops"
                   className="h-9 min-w-[220px] flex-1 rounded-md border border-white/[0.08] bg-black/30 px-3 text-[13px] text-white focus:outline-none focus:border-accent/35" />
            <select value={environment} onChange={(e) => setEnvironment(e.target.value)}
                    className="h-9 rounded-md border border-white/[0.08] bg-black/30 px-2 font-mono text-[11px] uppercase tracking-wider text-white/70 focus:outline-none">
              {["production", "staging", "development"].map((env) => (
                <option key={env} value={env}>{env}</option>
              ))}
            </select>
            <button disabled={busy || !name.trim()}
                    onClick={async () => {
                      setBusy(true);
                      try { await createWorkspace(org.id, name.trim(), "", environment); setName(""); onChanged(); }
                      finally { setBusy(false); }
                    }}
                    className="inline-flex h-9 items-center gap-1.5 rounded-md bg-accent/15 px-3 font-mono text-[11px] uppercase tracking-wider text-accent hover:bg-accent/25 transition-colors disabled:opacity-50">
              <Plus size={12} /> Create
            </button>
          </div>
        </Card>
      )}
      {org.workspaces.map((workspace) => (
        <WorkspaceCard key={workspace.id} orgId={org.id} workspace={workspace}
                       allCapabilities={allCapabilities} canManage={canManage}
                       onChanged={onChanged} />
      ))}
    </div>
  );
}

function WorkspaceCard({ orgId, workspace, allCapabilities, canManage, onChanged }: {
  orgId: string; workspace: ApiWorkspace; allCapabilities: string[];
  canManage: boolean; onChanged: () => void;
}) {
  const policy = workspace.policy || {};
  const approvalCaps = policy.approval_capabilities || [];
  const [busy, setBusy] = useState(false);

  const toggleApproval = async (capability: string) => {
    if (!canManage) return;
    const next = approvalCaps.includes(capability)
      ? approvalCaps.filter((c) => c !== capability)
      : [...approvalCaps, capability];
    setBusy(true);
    try {
      await updateWorkspacePolicy(orgId, workspace.id, { ...policy, approval_capabilities: next });
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[14px] text-white/90">{workspace.name}</span>
        <span className={cn("rounded border px-1.5 py-[1px] font-mono text-[9px] uppercase tracking-wider",
                            workspace.environment === "production"
                              ? "border-accent/25 text-accent/80" : "border-amber-300/25 text-amber-300/90")}>
          {workspace.environment}
        </span>
        <span className="font-mono text-[10px] text-white/25">/{workspace.slug}</span>
      </div>
      <div className="mt-3">
        <div className="mb-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-white/30">
          Capabilities requiring approval
        </div>
        {allCapabilities.length === 0 ? (
          <p className="text-[11px] text-white/30">
            Capability list appears when the engine is online.
          </p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {allCapabilities.map((capability) => {
              const gated = approvalCaps.includes(capability);
              return (
                <button key={capability} onClick={() => toggleApproval(capability)}
                        disabled={busy || !canManage}
                        title={gated ? "Requires approval — click to remove the gate"
                                     : "Runs freely — click to require approval"}
                        className={cn("rounded-full border px-2.5 py-[3px] font-mono text-[10px] tracking-wider transition-colors",
                                      gated ? "border-amber-300/40 text-amber-300 bg-amber-300/[0.07]"
                                            : "border-white/10 text-white/40 hover:text-white",
                                      !canManage && "cursor-default")}>
                  {capability}{gated && " 🔒"}
                </button>
              );
            })}
          </div>
        )}
      </div>
      <WebhookConfig orgId={orgId} workspace={workspace}
                     canManage={canManage} onChanged={onChanged} />
    </Card>
  );
}

/** Attention webhook: where unattended failures reach a human when nobody
 * has the dashboard open. The signing secret is shown exactly once when the
 * URL is set — after that it is write-only, like vault values. */
function WebhookConfig({ orgId, workspace, canManage, onChanged }: {
  orgId: string; workspace: ApiWorkspace; canManage: boolean; onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState(workspace.notify_webhook_url ?? "");
  const [minted, setMinted] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = async (nextUrl: string | null) => {
    setBusy(true);
    setError(null);
    try {
      const result = await setWorkspaceWebhook(orgId, workspace.id, nextUrl);
      setMinted(result.secret);
      setEditing(false);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update the webhook");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 border-t border-white/[0.05] pt-3">
      <div className="mb-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-white/30">
        Attention webhook
      </div>
      {minted && (
        <div className="mb-2 rounded-lg border border-accent/25 bg-accent/[0.05] px-3 py-2">
          <p className="font-mono text-[10px] uppercase tracking-wider text-accent">
            signing secret — shown once, save it now
          </p>
          <code className="mt-1 block break-all font-mono text-[11px] text-white/85">{minted}</code>
          <p className="mt-1 text-[10px] text-white/40">
            Verify deliveries with HMAC-SHA256 over the request body
            (header <code className="font-mono">X-PerceptAI-Signature</code>).
          </p>
        </div>
      )}
      {!editing ? (
        <div className="flex flex-wrap items-center gap-2">
          {workspace.notify_webhook_url ? (
            <code className="min-w-0 flex-1 truncate font-mono text-[11px] text-white/60">
              {workspace.notify_webhook_url}
            </code>
          ) : (
            <span className="flex-1 text-[11px] text-white/30">
              Not set — unattended failures reach the Attention inbox only.
            </span>
          )}
          {canManage && (
            <div className="flex items-center gap-1.5">
              <button onClick={() => { setUrl(workspace.notify_webhook_url ?? ""); setEditing(true); }}
                      className="rounded-md bg-white/[0.04] px-2.5 h-6 font-mono text-[10px] uppercase tracking-wider text-white/50 hover:text-white transition-colors">
                {workspace.notify_webhook_url ? "Replace" : "Set"}
              </button>
              {workspace.notify_webhook_url && (
                <button onClick={() => apply(null)} disabled={busy}
                        className="rounded-md px-2 h-6 font-mono text-[10px] uppercase tracking-wider text-white/35 hover:text-red-300 transition-colors disabled:opacity-50">
                  Clear
                </button>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <input value={url} onChange={(e) => setUrl(e.target.value)}
                 placeholder="https://hooks.example.com/perceptai"
                 className="h-8 min-w-[240px] flex-1 rounded-md border border-white/[0.08] bg-black/30 px-3 font-mono text-[12px] text-white focus:outline-none focus:border-accent/35" />
          <button onClick={() => apply(url.trim())} disabled={busy || !url.trim().startsWith("https://")}
                  className="rounded-md bg-accent/15 px-2.5 h-8 font-mono text-[10px] uppercase tracking-wider text-accent hover:bg-accent/25 transition-colors disabled:opacity-50">
            Save
          </button>
          <button onClick={() => setEditing(false)}
                  className="rounded-md px-2 h-8 font-mono text-[10px] uppercase tracking-wider text-white/40 hover:text-white transition-colors">
            Cancel
          </button>
        </div>
      )}
      {error && <p className="mt-1.5 text-[11px] text-red-300">{error}</p>}
    </div>
  );
}

/* -------------------------------------------------------------- secrets */

function SecretsTab({ orgId, secrets, workspaces, canManage, onChanged }: {
  orgId: string; secrets: ApiSecretMeta[]; workspaces: ApiWorkspace[];
  canManage: boolean; onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const workspaceName = (id: string | null) =>
    workspaces.find((w) => w.id === id)?.name ?? "org-wide";

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-3 flex items-start gap-2.5">
        <KeySquare size={14} className="text-accent mt-0.5 shrink-0" />
        <p className="text-[12.5px] leading-relaxed text-white/55">
          Use a secret in an automation by referencing it as{" "}
          <code className="font-mono text-accent/90">{"{{secret:NAME}}"}</code> — the agent injects the
          value only into a confirmed credential field, and the value is never sent to the model, the
          event stream, the report, or any log. Values are write-only here and encrypted at rest.
        </p>
      </div>
      {canManage && (
        <Card title="Add secret">
          <div className="flex flex-wrap items-center gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="NAME (e.g. CRM_PASSWORD)"
                   className="h-9 w-56 rounded-md border border-white/[0.08] bg-black/30 px-3 font-mono text-[12px] text-white focus:outline-none focus:border-accent/35" />
            <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="value" type="password"
                   className="h-9 min-w-[180px] flex-1 rounded-md border border-white/[0.08] bg-black/30 px-3 text-[13px] text-white focus:outline-none focus:border-accent/35" />
            <select value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)}
                    className="h-9 rounded-md border border-white/[0.08] bg-black/30 px-2 font-mono text-[11px] text-white/70 focus:outline-none">
              <option value="">org-wide</option>
              {workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
            <button disabled={busy || !name.trim() || !value}
                    onClick={async () => {
                      setBusy(true);
                      setError(null);
                      try {
                        await createSecret(orgId, name.trim(), value, workspaceId || undefined);
                        setName(""); setValue(""); onChanged();
                      } catch (e) {
                        setError(e instanceof Error ? e.message : "Could not save secret");
                      } finally { setBusy(false); }
                    }}
                    className="inline-flex h-9 items-center gap-1.5 rounded-md bg-accent/15 px-3 font-mono text-[11px] uppercase tracking-wider text-accent hover:bg-accent/25 transition-colors disabled:opacity-50">
              <Plus size={12} /> Store
            </button>
          </div>
          {error && <p className="mt-2 text-[12px] text-red-300">{error}</p>}
          <p className="mt-2 text-[10px] leading-relaxed text-white/30">
            Encrypted server-side (AES + HMAC); values are write-only — they can
            be rotated or deleted, never read back. Runtime injection into typed
            fields is on the roadmap.
          </p>
        </Card>
      )}
      <Card title={`Secrets · ${secrets.length}`}>
        {secrets.length === 0 ? (
          <p className="py-3 text-[12px] text-white/35">No secrets stored.</p>
        ) : (
          <div className="divide-y divide-white/[0.04]">
            {secrets.map((secret) => (
              <div key={secret.id} className="flex items-center gap-3 py-2.5">
                <KeySquare size={13} className="text-white/30 shrink-0" />
                <span className="font-mono text-[12px] text-white/85">{secret.name}</span>
                <span className="font-mono text-[12px] text-white/25 tracking-widest">••••••••</span>
                <span className="flex-1" />
                <span className="font-mono text-[10px] text-white/30">{workspaceName(secret.workspace_id)}</span>
                {canManage && (
                  <button
                    onClick={async () => { await deleteSecret(orgId, secret.id); onChanged(); }}
                    className="rounded-md p-1.5 text-white/25 hover:text-red-300 hover:bg-red-400/10 transition-colors"
                    aria-label={`Delete ${secret.name}`}>
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------- audit */

function AuditTab({ audit }: { audit: ApiAuditEntry[] }) {
  return (
    <Card title={`Audit trail · latest ${audit.length}`}>
      {audit.length === 0 ? (
        <p className="py-3 text-[12px] text-white/35">
          No control-plane events yet. Member changes, secrets, policy edits
          and approval decisions land here.
        </p>
      ) : (
        <div className="divide-y divide-white/[0.04]">
          {audit.map((entry) => (
            <div key={entry.id} className="flex items-center gap-3 py-2">
              <span className="w-32 shrink-0 font-mono text-[10px] text-white/30">
                {new Date(entry.created_at).toLocaleString()}
              </span>
              <span className="w-40 shrink-0 truncate font-mono text-[11px] text-accent/75">
                {entry.action}
              </span>
              <span className="min-w-0 flex-1 truncate text-[12px] text-white/60">
                {entry.target}
              </span>
              <span className="shrink-0 truncate font-mono text-[10px] text-white/30 max-w-[16ch]">
                {entry.actor_email || "system"}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

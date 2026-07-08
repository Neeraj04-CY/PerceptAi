"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Plus, Cpu, Server, AlertTriangle, RefreshCcw, Copy, Check, X, Circle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/dashboard/page-header";
import { getRunners, registerRunner, type ApiRunner, type NewRunner } from "@/lib/api";
import { cn } from "@/lib/utils";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const API_V1 = `${API_BASE}/api/v1`;

export default function RunnersPage() {
  const router = useRouter();
  const [runners, setRunners] = useState<ApiRunner[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [registering, setRegistering] = useState(false);
  const [created, setCreated] = useState<NewRunner | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setError(null);
    try {
      setRunners(await getRunners(signal));
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      if ((err as Error).message === "Unauthorized") { router.replace("/signin"); return; }
      setError((err as Error).message || "Failed to load runners");
      setRunners([]);
    }
  }, [router]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    const id = setInterval(() => load(), 5000);  // fleet status is live
    return () => { controller.abort(); clearInterval(id); };
  }, [load]);

  const handleRegister = async () => {
    setRegistering(true);
    try {
      const result = await registerRunner(`runner-${new Date().toISOString().slice(5, 16).replace("T", "-")}`);
      setCreated(result);
      await load();
    } catch (err) {
      setError((err as Error).message || "Registration failed");
    } finally {
      setRegistering(false);
    }
  };

  const online = runners?.filter((r) => r.status !== "offline").length ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Runners"
        subtitle="Machines that execute work wherever it lives. The control plane dispatches signed tasks to a runner; results stream back to the same live cockpit."
        actions={
          <Button variant="primary" size="sm" onClick={handleRegister} disabled={registering} className="gap-2">
            <Plus size={14} strokeWidth={2.5} />
            {registering ? "Registering…" : "Register runner"}
          </Button>
        }
      />

      {created && <RegisteredPanel runner={created} onDismiss={() => setCreated(null)} />}

      {error ? (
        <ErrorState message={error} onRetry={() => load()} />
      ) : runners === null ? (
        <Skeleton />
      ) : runners.length === 0 ? (
        <EmptyState onRegister={handleRegister} busy={registering} />
      ) : (
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden">
          <div className="hidden sm:grid grid-cols-[1.4fr_120px_1fr_130px_110px] gap-3 px-5 py-3 border-b border-white/[0.06] font-mono text-[10px] uppercase tracking-[0.2em] text-white/35">
            <div>Runner</div>
            <div>Status</div>
            <div>Capabilities</div>
            <div>Last seen</div>
            <div className="text-right">Token</div>
          </div>
          {runners.map((r, i) => (
            <motion.div
              key={r.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.3) }}
              className="grid grid-cols-1 sm:grid-cols-[1.4fr_120px_1fr_130px_110px] gap-x-3 gap-y-1.5 px-5 py-4 border-b border-white/[0.04] last:border-0 items-center"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <Server size={15} className="text-white/45 shrink-0" />
                <span className="text-[13.5px] text-white truncate">{r.name}</span>
              </div>
              <StatusBadge status={r.status} />
              <div className="font-mono text-[11.5px] text-white/55 truncate">
                {capabilitySummary(r.capabilities)}
              </div>
              <div className="font-mono text-[12px] text-white/45">
                {r.last_heartbeat_at ? timeAgo(r.last_heartbeat_at) : "never"}
              </div>
              <code className="font-mono text-[11.5px] text-white/45 sm:text-right truncate">{r.token_prefix}…</code>
            </motion.div>
          ))}
        </div>
      )}

      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 flex items-start gap-3">
        <Cpu size={14} className="text-accent mt-0.5 shrink-0" />
        <div>
          <div className="text-[13px] text-white">
            {online} runner{online === 1 ? "" : "s"} online · how it works
          </div>
          <div className="mt-1 text-[12.5px] text-white/55 leading-relaxed">
            A runner pulls signed work over an outbound connection — no inbound ports, so it runs
            behind any firewall. It executes through the same runtime as a local run and streams
            canonical events back. Register one, drop its credentials into the runner, and start it.
          </div>
        </div>
      </div>
    </div>
  );
}

function RegisteredPanel({ runner, onDismiss }: { runner: NewRunner; onDismiss: () => void }) {
  const setup = [
    `# 1. install the runner (from the repo)`,
    `pip install -e .`,
    ``,
    `# 2. set the credentials from this registration`,
    `export RUNNER_PLANE_URL=${API_V1}`,
    `export RUNNER_TOKEN=${runner.token}`,
    `export RUNNER_SIGNING_KEY=${runner.signing_key}`,
    ``,
    `# 3. verify the host is ready, then start`,
    `perceptai-runner --doctor`,
    `perceptai-runner`,
  ].join("\n");
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-accent/25 bg-accent/[0.05] overflow-hidden"
    >
      <div className="flex items-center justify-between px-5 h-11 border-b border-accent/15">
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
          runner registered — credentials shown once
        </span>
        <button onClick={onDismiss} className="text-white/50 hover:text-white transition-colors" aria-label="Dismiss">
          <X size={15} />
        </button>
      </div>
      <div className="p-5 space-y-3">
        <p className="text-[13px] text-white/70 leading-relaxed">
          Copy the token and signing key now — they are hashed at rest and cannot be shown again.
          Set them on the runner host, then run <code className="font-mono text-accent/90">--doctor</code> to
          confirm the environment is ready before starting:
        </p>
        <CopyBlock label="setup" value={setup} />
        <p className="text-[12px] text-white/45">
          <code className="font-mono">--doctor</code> checks dependencies, screen access, plane
          connectivity and credentials, and tells you exactly how to fix anything missing. The runner
          takes over the real mouse and keyboard on that host — run it on a machine dedicated to automation.
        </p>
      </div>
    </motion.div>
  );
}

function CopyBlock({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); } catch { /* best effort */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };
  return (
    <div className="relative rounded-lg border border-white/[0.08] bg-black/40">
      <div className="flex items-center justify-between px-3 h-8 border-b border-white/[0.06]">
        <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-white/35">{label}</span>
        <button onClick={copy} className="inline-flex items-center gap-1 text-[11px] text-white/55 hover:text-white transition-colors">
          {copied ? <Check size={11} className="text-accent" /> : <Copy size={11} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto px-3 py-2.5 font-mono text-[11.5px] leading-relaxed text-white/75">{value}</pre>
    </div>
  );
}

function StatusBadge({ status }: { status: ApiRunner["status"] }) {
  const look = {
    online: { c: "text-accent border-accent/30 bg-accent/10", label: "online" },
    busy: { c: "text-amber-200 border-amber-400/30 bg-amber-400/10", label: "busy" },
    offline: { c: "text-white/40 border-white/15 bg-white/5", label: "offline" },
  }[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md border px-2 h-6 font-mono text-[10px] uppercase tracking-[0.14em] w-fit", look.c)}>
      <Circle size={7} className="fill-current" />
      {look.label}
    </span>
  );
}

function capabilitySummary(caps: Record<string, unknown>): string {
  if (!caps || Object.keys(caps).length === 0) return "—";
  const parts: string[] = [];
  if (caps.os) parts.push(String(caps.os));
  if (caps.engine_version) parts.push(`engine ${caps.engine_version}`);
  if (Array.isArray(caps.tags) && caps.tags.length) parts.push(caps.tags.join(", "));
  return parts.join(" · ") || Object.keys(caps).join(", ");
}

function EmptyState({ onRegister, busy }: { onRegister: () => void; busy: boolean }) {
  return (
    <div className="rounded-xl border border-dashed border-white/[0.1] bg-white/[0.015] px-6 py-14 flex flex-col items-center text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-white/50">
        <Server size={20} strokeWidth={1.6} />
      </span>
      <h3 className="mt-4 text-[15px] font-medium text-white">No runners yet</h3>
      <p className="mt-1.5 max-w-md text-[13px] leading-relaxed text-white/50">
        Register a runner to execute tasks on another machine — a back-office desktop, a VM, or a
        dedicated automation host. You&apos;ll get credentials to drop into the runner once.
      </p>
      <Button variant="primary" size="sm" onClick={onRegister} disabled={busy} className="mt-5 gap-2">
        <Plus size={14} strokeWidth={2.5} />
        {busy ? "Registering…" : "Register your first runner"}
      </Button>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-red-400/25 bg-red-400/[0.05] p-6">
      <div className="flex items-center gap-2 text-red-300">
        <AlertTriangle size={15} />
        <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Couldn&apos;t load runners</span>
      </div>
      <p className="mt-2 text-[13px] text-white/70">{message}</p>
      <button onClick={onRetry} className="mt-4 inline-flex items-center gap-2 rounded-lg border border-white/[0.1] bg-white/[0.04] px-3.5 h-9 text-[12.5px] text-white/80 hover:text-white transition-colors">
        <RefreshCcw size={13} /> Retry
      </button>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden animate-pulse">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-5 py-4 border-b border-white/[0.04] last:border-0">
          <div className="h-3.5 w-3.5 rounded-full bg-white/10" />
          <div className="h-3.5 w-40 rounded bg-white/10" />
          <div className="ml-auto h-3.5 w-20 rounded bg-white/10" />
        </div>
      ))}
    </div>
  );
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const s = Math.max(0, (Date.now() - then) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

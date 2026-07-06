"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Plus, ShieldCheck, ShieldOff, KeyRound, AlertTriangle, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/dashboard/page-header";
import { CreateKeyModal } from "./create-key-modal";
import { getKeys, createKey, revokeKey, type ApiKey } from "@/lib/api";
import { cn } from "@/lib/utils";

const ACTIVE_KEY_STORAGE_KEY = "perceptai_active_key";

export function KeysTable() {
  const router = useRouter();
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setError(null);
    try {
      const data = await getKeys(signal);
      setKeys(data);
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      if ((err as Error).message === "Unauthorized") {
        router.replace("/signin");
        return;
      }
      setError((err as Error).message || "Failed to load keys");
      setKeys([]);
    }
  }, [router]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const handleCreate = async (name: string): Promise<string> => {
    const created = await createKey(name);
    try {
      window.localStorage.setItem(ACTIVE_KEY_STORAGE_KEY, created.full_key);
    } catch {
      /* ignore */
    }
    await load();
    return created.full_key;
  };

  const handleRevoke = async (id: string) => {
    setBusyId(id);
    try {
      await revokeKey(id);
      await load();
    } catch {
      /* surfaced on refresh */
    } finally {
      setBusyId(null);
      setConfirmId(null);
    }
  };

  const activeCount = keys?.filter((k) => k.is_active).length ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="API Keys"
        subtitle="Credentials for the PerceptAI runtime. Keys are shown once at creation and hashed at rest — rotate and revoke them here."
        actions={
          <Button variant="primary" size="sm" onClick={() => setModalOpen(true)} data-testid="create-key-btn" className="gap-2">
            <Plus size={14} strokeWidth={2.5} />
            New key
          </Button>
        }
      />

      {error ? (
        <ErrorState message={error} onRetry={() => load()} />
      ) : keys === null ? (
        <TableSkeleton />
      ) : keys.length === 0 ? (
        <EmptyState onCreate={() => setModalOpen(true)} />
      ) : (
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden" data-testid="keys-table">
          <div className="hidden sm:grid grid-cols-[1.6fr_1.2fr_130px_130px_88px] gap-3 px-5 py-3 border-b border-white/[0.06] font-mono text-[10px] uppercase tracking-[0.2em] text-white/35">
            <div>Name</div>
            <div>Key</div>
            <div>Last used</div>
            <div>Created</div>
            <div className="text-right">Status</div>
          </div>

          {keys.map((k, i) => (
            <motion.div
              key={k.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.3) }}
              className={cn(
                "grid grid-cols-1 sm:grid-cols-[1.6fr_1.2fr_130px_130px_88px] gap-x-3 gap-y-1.5 px-5 py-4 border-b border-white/[0.04] last:border-0 items-center group",
                !k.is_active && "opacity-55"
              )}
              data-testid={`key-row-${k.id}`}
            >
              <div className="flex items-center gap-2 min-w-0">
                {k.is_active ? (
                  <ShieldCheck size={14} className="text-accent shrink-0" />
                ) : (
                  <ShieldOff size={14} className="text-white/30 shrink-0" />
                )}
                <span className="text-[13.5px] text-white truncate">{k.name}</span>
              </div>

              <code className="font-mono text-[12.5px] text-white/70 truncate">{k.key_prefix}…</code>

              <div className="font-mono text-[12px] text-white/55">
                {k.last_used_at ? timeAgo(k.last_used_at) : "never"}
              </div>
              <div className="font-mono text-[12px] text-white/45">{formatDate(k.created_at)}</div>

              <div className="flex sm:justify-end items-center gap-2">
                {k.is_active ? (
                  confirmId === k.id ? (
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => handleRevoke(k.id)}
                        disabled={busyId === k.id}
                        className="rounded-md bg-red-400/15 px-2 h-6 font-mono text-[10px] uppercase tracking-wider text-red-300 hover:bg-red-400/25 transition-colors disabled:opacity-50"
                      >
                        {busyId === k.id ? "…" : "Confirm"}
                      </button>
                      <button
                        onClick={() => setConfirmId(null)}
                        className="rounded-md px-1.5 h-6 font-mono text-[10px] uppercase tracking-wider text-white/40 hover:text-white transition-colors"
                      >
                        No
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmId(k.id)}
                      data-testid={`revoke-key-${k.id}`}
                      className="rounded-md border border-white/[0.08] bg-white/[0.02] px-2.5 h-6 font-mono text-[10px] uppercase tracking-wider text-white/45 hover:text-red-300 hover:border-red-400/30 transition-colors sm:opacity-0 sm:group-hover:opacity-100"
                    >
                      Revoke
                    </button>
                  )
                ) : (
                  <span className="font-mono text-[10px] uppercase tracking-wider text-white/35">revoked</span>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* Footer note */}
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 flex items-start gap-3">
        <ShieldCheck size={14} className="text-accent mt-0.5 shrink-0" />
        <div>
          <div className="text-[13px] text-white">
            {activeCount} active {activeCount === 1 ? "key" : "keys"} · best practices
          </div>
          <div className="mt-1 text-[12.5px] text-white/55 leading-relaxed">
            Rotate production keys regularly. Never commit keys to source control —
            use environment variables or a secrets manager like Doppler, Vault, or Infisical.
          </div>
        </div>
      </div>

      <CreateKeyModal open={modalOpen} onOpenChange={setModalOpen} onCreate={handleCreate} />
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="rounded-xl border border-dashed border-white/[0.1] bg-white/[0.015] px-6 py-14 flex flex-col items-center text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-white/50">
        <KeyRound size={20} strokeWidth={1.6} />
      </span>
      <h3 className="mt-4 text-[15px] font-medium text-white">No API keys yet</h3>
      <p className="mt-1.5 max-w-sm text-[13px] leading-relaxed text-white/50">
        Create a key to call the runtime from the API, CI, or your own tools.
        You&apos;ll see the full key once — store it safely.
      </p>
      <Button variant="primary" size="sm" onClick={onCreate} className="mt-5 gap-2">
        <Plus size={14} strokeWidth={2.5} />
        Create your first key
      </Button>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-red-400/25 bg-red-400/[0.05] p-6">
      <div className="flex items-center gap-2 text-red-300">
        <AlertTriangle size={15} />
        <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Couldn&apos;t load keys</span>
      </div>
      <p className="mt-2 text-[13px] text-white/70">{message}</p>
      <button
        onClick={onRetry}
        className="mt-4 inline-flex items-center gap-2 rounded-lg border border-white/[0.1] bg-white/[0.04] px-3.5 h-9 text-[12.5px] text-white/80 hover:text-white transition-colors"
      >
        <RefreshCcw size={13} /> Retry
      </button>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden animate-pulse">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-5 py-4 border-b border-white/[0.04] last:border-0">
          <div className="h-3.5 w-3.5 rounded-full bg-white/10" />
          <div className="h-3.5 w-40 rounded bg-white/10" />
          <div className="ml-auto h-3.5 w-24 rounded bg-white/10" />
        </div>
      ))}
    </div>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" });
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

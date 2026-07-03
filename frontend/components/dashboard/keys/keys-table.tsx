"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Plus, Copy, Check, MoreHorizontal, ShieldCheck, ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { initialKeys, makeFreshKey, type ApiKeyRow } from "./mock";
import { CreateKeyModal } from "./create-key-modal";
import { cn } from "@/lib/utils";

const FULL_KEY_STORAGE_PREFIX = "perceptai_full_key_";
const ACTIVE_KEY_STORAGE_KEY = "perceptai_active_key";

function storeFullKey(id: string, fullKey: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(FULL_KEY_STORAGE_PREFIX + id, fullKey);
}

function getStoredFullKey(id: string): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(FULL_KEY_STORAGE_PREFIX + id);
}

function saveActiveKey(fullKey: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACTIVE_KEY_STORAGE_KEY, fullKey);
}

export function KeysTable() {
  const [keys, setKeys] = useState<ApiKeyRow[]>(initialKeys);
  const [modalOpen, setModalOpen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopy = (key: ApiKeyRow) => {
    const fullKey = getStoredFullKey(key.id);
    if (!fullKey) {
      alert("Full key only shown once at creation. Create a new key to get a copyable key.");
      return;
    }
    navigator.clipboard?.writeText(fullKey);
    setCopiedId(key.id);
    setTimeout(() => setCopiedId(null), 1200);
  };

  const handleCreate = (name: string, env: ApiKeyRow["env"]) => {
    const fresh = makeFreshKey(name);
    const keyPrefix = fresh.slice(0, 12);
    saveActiveKey(fresh);
    const newKeyId = "key_" + Math.random().toString(36).slice(2, 10).toUpperCase();
    const newKey: ApiKeyRow = {
      id: newKeyId,
      name,
      prefix: keyPrefix,
      env,
      createdAt: new Date().toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" }),
      lastUsed: "never",
      status: "active",
      scopes: ["run:write", "run:read"],
    };
    storeFullKey(newKeyId, fresh);
    setKeys((prev) => [newKey, ...prev]);
    return fresh;
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold tracking-tight text-white">Your keys</h2>
          <p className="mt-1 text-[12.5px] text-white/50 max-w-lg">
            Each key is signed with HMAC and scoped to a single environment. Revoke instantly — old keys are blacklisted within 200ms globally.
          </p>
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setModalOpen(true)}
          data-testid="create-key-btn"
          className="gap-2 shrink-0"
        >
          <Plus size={14} strokeWidth={2.5} />
          New key
        </Button>
      </div>

      {/* Keys table */}
      <div
        className="rounded-xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl overflow-hidden"
        data-testid="keys-table"
      >
        <div className="grid grid-cols-[1.4fr_1.4fr_110px_110px_110px_60px] gap-3 px-5 py-3 border-b border-white/[0.06] font-mono text-[10px] uppercase tracking-[0.22em] text-white/35">
          <div>Name</div>
          <div>Key</div>
          <div>Env</div>
          <div>Last used</div>
          <div>Created</div>
          <div></div>
        </div>

        {keys.map((k, i) => (
          <motion.div
            key={k.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: i * 0.04 }}
            className={cn(
              "grid grid-cols-[1.4fr_1.4fr_110px_110px_110px_60px] gap-3 px-5 py-3.5 border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] transition-colors items-center group",
              k.status === "revoked" && "opacity-55"
            )}
            data-testid={`key-row-${k.id}`}
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                {k.status === "active" ? (
                  <ShieldCheck size={13} className="text-accent shrink-0" />
                ) : (
                  <ShieldOff size={13} className="text-white/30 shrink-0" />
                )}
                <span className="text-[13px] text-white truncate">{k.name}</span>
              </div>
              <div className="mt-1 flex items-center gap-1.5">
                {k.scopes.map((s) => (
                  <span
                    key={s}
                    className="rounded-sm bg-white/[0.04] px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-white/45"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2 min-w-0">
              <code className="font-mono text-[12px] text-white/75 truncate">{k.prefix}</code>
              <button
                onClick={() => handleCopy(k)}
                disabled={k.status === "revoked"}
                data-testid={`copy-key-${k.id}`}
                className="opacity-0 group-hover:opacity-100 transition-opacity rounded-md border border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.06] h-6 w-6 flex items-center justify-center text-white/65 disabled:opacity-30"
                aria-label="Copy"
              >
                {copiedId === k.id ? <Check size={11} className="text-accent" /> : <Copy size={11} />}
              </button>
            </div>

            <div>
              <span
                className={cn(
                  "inline-flex font-mono text-[10px] uppercase tracking-wider rounded-sm px-1.5 py-0.5",
                  k.env === "production" && "bg-accent/10 text-accent",
                  k.env === "staging" && "bg-[#E8C44A]/10 text-[#E8C44A]",
                  k.env === "development" && "bg-white/[0.05] text-white/55"
                )}
              >
                {k.env}
              </span>
            </div>

            <div className="font-mono text-[11px] text-white/55">{k.lastUsed}</div>
            <div className="font-mono text-[11px] text-white/45">{k.createdAt}</div>
            <div className="flex justify-end">
              <button
                className="opacity-0 group-hover:opacity-100 transition-opacity rounded-md h-7 w-7 flex items-center justify-center text-white/45 hover:text-white hover:bg-white/[0.04]"
                aria-label="More actions"
                data-testid={`key-actions-${k.id}`}
              >
                <MoreHorizontal size={14} />
              </button>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Footer note */}
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 flex items-start gap-3">
        <ShieldCheck size={14} className="text-accent mt-0.5 shrink-0" />
        <div>
          <div className="text-[13px] text-white">Best practices</div>
          <div className="mt-1 text-[12px] text-white/55 leading-relaxed">
            Rotate production keys every 90 days. Never commit keys to source control —
            use environment variables and a secrets manager like Doppler, Vault, or Infisical.
          </div>
        </div>
      </div>

      <CreateKeyModal open={modalOpen} onOpenChange={setModalOpen} onCreate={handleCreate} />
    </div>
  );
}

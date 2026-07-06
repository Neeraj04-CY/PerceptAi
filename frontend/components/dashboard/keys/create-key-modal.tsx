"use client";

import { useState } from "react";
import { Dialog, DialogHeader, DialogTitle, DialogDescription, DialogBody, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Check, Copy, ShieldCheck, AlertTriangle } from "lucide-react";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** Calls the real API; resolves to the one-time full key. */
  onCreate: (name: string) => Promise<string>;
}

export function CreateKeyModal({ open, onOpenChange, onCreate }: Props) {
  const [name, setName] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setName("");
    setCreated(null);
    setCopied(false);
    setBusy(false);
    setError(null);
  };

  const handleCreate = async () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const key = await onCreate(name.trim());
      setCreated(key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create key");
    } finally {
      setBusy(false);
    }
  };

  const handleCopy = () => {
    if (!created) return;
    navigator.clipboard?.writeText(created);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  const handleClose = (v: boolean) => {
    if (!v) setTimeout(reset, 220);
    onOpenChange(v);
  };

  if (created) {
    return (
      <Dialog open={open} onOpenChange={handleClose} size="lg">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-accent/15 text-accent">
              <ShieldCheck size={14} />
            </span>
            <DialogTitle>Key created</DialogTitle>
          </div>
          <DialogDescription>
            Copy your secret key now — it will <span className="text-white/85">never be shown again</span>.
            Store it in a secure secret manager.
          </DialogDescription>
        </DialogHeader>

        <DialogBody>
          <div
            className="rounded-lg border border-accent/30 bg-accent/[0.04] p-3 flex items-center gap-3"
            data-testid="created-key-display"
          >
            <code className="flex-1 font-mono text-[12.5px] text-white break-all">{created}</code>
            <button
              onClick={handleCopy}
              data-testid="copy-created-key"
              className="shrink-0 inline-flex items-center gap-1.5 rounded-md border border-white/[0.10] bg-white/[0.04] hover:bg-white/[0.08] px-2.5 h-8 font-mono text-[11px] uppercase tracking-wider text-white/80 transition-colors"
            >
              {copied ? <Check size={12} className="text-accent" /> : <Copy size={12} />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>

          <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-[#E8C44A]/20 bg-[#E8C44A]/[0.04] p-3">
            <AlertTriangle size={14} className="text-[#E8C44A] mt-0.5 shrink-0" />
            <p className="text-[12.5px] text-white/65 leading-relaxed">
              For your security, this is the only time the full key will be visible.
              You can revoke it from this page at any time.
            </p>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="primary" size="sm" onClick={() => handleClose(false)} data-testid="created-key-done">
            Done
          </Button>
        </DialogFooter>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogHeader>
        <DialogTitle>Create new API key</DialogTitle>
        <DialogDescription>
          API keys grant access to the PerceptAI runtime. Give each key a
          descriptive name so you can tell them apart when rotating.
        </DialogDescription>
      </DialogHeader>

      <DialogBody>
        <div className="space-y-4">
          <div>
            <label className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
              Name
            </label>
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="e.g. Production · primary"
              className="mt-2"
              data-testid="new-key-name"
            />
          </div>
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-400/25 bg-red-400/[0.06] px-3 py-2 text-[12.5px] text-red-200">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" />
              {error}
            </div>
          )}
        </div>
      </DialogBody>

      <DialogFooter>
        <Button variant="ghost" size="sm" onClick={() => handleClose(false)} data-testid="cancel-create-key">
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={handleCreate}
          data-testid="confirm-create-key"
          className={!name.trim() || busy ? "opacity-50 pointer-events-none" : ""}
        >
          {busy ? "Creating…" : "Create key"}
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

"use client";

import { useEffect, useState } from "react";
import { getPlatformHealth, type PlatformHealth } from "@/lib/api";
import { cn } from "@/lib/utils";

type Status = "loading" | "healthy" | "degraded" | "offline";

/** Honest runtime status wired to /platform/health — replaces the old
 * hardcoded "runtime online". Green only when the API + database are up;
 * amber when the desktop engine is missing (cloud host); red when the API
 * can't be reached at all. */
export function RuntimeHealth({ compact = false }: { compact?: boolean }) {
  const [health, setHealth] = useState<PlatformHealth | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const poll = async () => {
      try {
        const h = await getPlatformHealth(controller.signal);
        if (!active) return;
        setHealth(h);
        if (!h.database) setStatus("degraded");
        else if (!h.engine) setStatus("degraded");
        else setStatus("healthy");
      } catch (err) {
        if ((err as Error)?.name === "AbortError" || !active) return;
        setStatus("offline");
        setHealth(null);
      }
    };
    poll();
    const id = setInterval(poll, 20_000);
    return () => {
      active = false;
      controller.abort();
      clearInterval(id);
    };
  }, []);

  const meta: Record<Status, { label: string; dot: string; text: string }> = {
    loading: { label: "checking…", dot: "bg-white/30", text: "text-white/40" },
    healthy: { label: "workforce online", dot: "bg-accent", text: "text-white/60" },
    degraded: {
      label: health && !health.engine ? "execution offline" : "degraded",
      dot: "bg-amber-300",
      text: "text-amber-200/80",
    },
    offline: { label: "unreachable", dot: "bg-red-400", text: "text-red-300/80" },
  };
  const m = meta[status];

  const title = health
    ? [
        `API ${health ? "up" : "down"}`,
        `Database ${health.database ? "up" : "down"}`,
        `Engine ${health.engine ? "up" : health.engine_reason || "offline"}`,
        health.scheduler ? "Scheduler on" : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : "Runtime status";

  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-white/[0.07] bg-white/[0.02] px-2.5 h-8",
        compact && "h-7 px-2"
      )}
    >
      <span className="relative flex h-1.5 w-1.5">
        {status === "healthy" && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent/60" />
        )}
        <span className={cn("relative inline-flex h-1.5 w-1.5 rounded-full", m.dot)} />
      </span>
      {!compact && (
        <span
          className={cn(
            "font-mono text-[10px] uppercase tracking-[0.16em]",
            m.text
          )}
        >
          {m.label}
        </span>
      )}
    </span>
  );
}

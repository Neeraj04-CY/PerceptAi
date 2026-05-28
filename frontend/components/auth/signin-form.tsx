"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, useAnimationControls } from "framer-motion";
import { Eye, EyeOff, ArrowRight, Loader2 } from "lucide-react";
import { saveToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

const API_BASE = "https://perceptai-production.up.railway.app/api/v1";

export function SigninForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shake = useAnimationControls();

  const triggerShake = async () => {
    await shake.start({
      x: [-4, 4, -4, 4, 0],
      transition: { duration: 0.35, ease: "easeOut" },
    });
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    setSubmitting(true);

    try {
      const res = await fetch(`${API_BASE}/auth/signin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        let msg = `Sign in failed (${res.status})`;
        try {
          const data = await res.json();
          if (data?.detail) msg = typeof data.detail === "string" ? data.detail : msg;
          else if (data?.message) msg = data.message;
        } catch {
          // keep default msg
        }
        throw new Error(msg);
      }

      const data = await res.json();
      const token = data?.access_token || data?.token;
      if (!token) throw new Error("No token returned from server");

      saveToken(token);
      router.push("/dashboard");
    } catch (err) {
      const msg = (err as Error).message || "Something went wrong. Try again.";
      setError(msg);
      setSubmitting(false);
      triggerShake();
    }
  };

  return (
    <motion.form
      onSubmit={onSubmit}
      animate={shake}
      className="space-y-4"
      data-testid="signin-form"
      noValidate
    >
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.35 }}
      >
        <Label>Email</Label>
        <FieldInput
          type="email"
          autoComplete="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          data-testid="signin-email"
          required
        />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.4 }}
      >
        <Label>Password</Label>
        <div className="relative">
          <FieldInput
            type={showPw ? "text" : "password"}
            autoComplete="current-password"
            placeholder="••••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            data-testid="signin-password"
            className="pr-11"
            required
          />
          <button
            type="button"
            onClick={() => setShowPw((v) => !v)}
            aria-label={showPw ? "Hide password" : "Show password"}
            data-testid="toggle-password"
            className="absolute right-2 top-1/2 -translate-y-1/2 h-7 w-7 inline-flex items-center justify-center rounded-md text-white/45 hover:text-white hover:bg-white/[0.04] transition-colors"
          >
            {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
      </motion.div>

      <motion.button
        type="submit"
        disabled={submitting}
        data-testid="signin-submit"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.45 }}
        whileHover={!submitting ? { y: -1 } : undefined}
        className={cn(
          "mt-6 w-full inline-flex items-center justify-center gap-2 h-11 rounded-lg bg-accent text-black font-mono text-[13px] uppercase tracking-[0.18em] font-semibold transition-all duration-200",
          "hover:bg-[#00e876] hover:shadow-[0_8px_32px_rgba(0,255,133,0.25)]",
          submitting && "opacity-80 cursor-wait"
        )}
      >
        {submitting ? (
          <>
            <Loader2 size={14} className="animate-spin" />
            Authenticating…
          </>
        ) : (
          <>
            Sign In
            <ArrowRight size={14} strokeWidth={2.5} />
          </>
        )}
      </motion.button>

      {error && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          role="alert"
          data-testid="signin-error"
          className="rounded-lg border border-[#FF3B3B]/20 bg-[#FF3B3B]/10 px-4 py-3 text-[13px] text-[#FF3B3B] leading-relaxed"
        >
          {error}
        </motion.div>
      )}

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.35, delay: 0.6 }}
        className="text-center text-[13px] text-white/45 pt-2"
      >
        No account?{" "}
        <Link
          href="/signup"
          data-testid="link-to-signup"
          className="text-accent hover:underline underline-offset-4"
        >
          Create one →
        </Link>
      </motion.div>
    </motion.form>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="block mb-2 font-mono text-[11px] uppercase tracking-[0.22em] text-white/40">
      {children}
    </label>
  );
}

function FieldInput({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "w-full h-11 rounded-lg bg-[#0D0D0D] border border-white/[0.08] px-4 text-[14px] text-white placeholder:text-white/20",
        "focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/10",
        "transition-all duration-200 font-sans",
        className
      )}
    />
  );
}

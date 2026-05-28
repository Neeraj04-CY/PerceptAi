"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, useAnimationControls } from "framer-motion";
import { Eye, EyeOff, ArrowRight, Loader2, Check } from "lucide-react";
import { saveToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

const API_BASE = "https://perceptai-production.up.railway.app/api/v1";
const MIN_PASSWORD = 8;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface Touched {
  email: boolean;
  password: boolean;
}

export function SignupForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [touched, setTouched] = useState<Touched>({ email: false, password: false });
  const shake = useAnimationControls();

  const emailError =
    touched.email && !EMAIL_RE.test(email.trim())
      ? "Enter a valid email address."
      : null;
  const passwordError =
    touched.password && password.length < MIN_PASSWORD
      ? `Password must be at least ${MIN_PASSWORD} characters.`
      : null;

  const formInvalid = !EMAIL_RE.test(email.trim()) || password.length < MIN_PASSWORD;

  const triggerShake = async () => {
    await shake.start({
      x: [-4, 4, -4, 4, 0],
      transition: { duration: 0.35, ease: "easeOut" },
    });
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    setTouched({ email: true, password: true });
    if (formInvalid) {
      triggerShake();
      return;
    }
    setServerError(null);
    setSubmitting(true);

    try {
      const res = await fetch(`${API_BASE}/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });

      if (!res.ok) {
        let msg = `Sign up failed (${res.status})`;
        try {
          const data = await res.json();
          if (data?.detail) msg = typeof data.detail === "string" ? data.detail : msg;
          else if (data?.message) msg = data.message;
        } catch {
          // keep default
        }
        throw new Error(msg);
      }

      const data = await res.json();
      const token = data?.access_token || data?.token;
      if (!token) throw new Error("No token returned from server");
      saveToken(token);
      router.push("/dashboard");
    } catch (err) {
      setServerError((err as Error).message || "Something went wrong. Try again.");
      setSubmitting(false);
      triggerShake();
    }
  };

  return (
    <motion.form
      onSubmit={onSubmit}
      animate={shake}
      className="space-y-4"
      data-testid="signup-form"
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
          onBlur={() => setTouched((t) => ({ ...t, email: true }))}
          data-testid="signup-email"
          aria-invalid={!!emailError}
          error={!!emailError}
          required
        />
        {emailError && <FieldError data-testid="signup-email-error">{emailError}</FieldError>}
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
            autoComplete="new-password"
            placeholder="At least 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onBlur={() => setTouched((t) => ({ ...t, password: true }))}
            data-testid="signup-password"
            aria-invalid={!!passwordError}
            error={!!passwordError}
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
        {passwordError ? (
          <FieldError data-testid="signup-password-error">{passwordError}</FieldError>
        ) : password.length > 0 && password.length < MIN_PASSWORD ? (
          <p className="mt-1.5 font-mono text-[10.5px] text-white/35">
            {MIN_PASSWORD - password.length} more character
            {MIN_PASSWORD - password.length === 1 ? "" : "s"} to go
          </p>
        ) : null}
      </motion.div>

      <motion.button
        type="submit"
        disabled={submitting}
        data-testid="signup-submit"
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
            Creating account…
          </>
        ) : (
          <>
            Create Account
            <ArrowRight size={14} strokeWidth={2.5} />
          </>
        )}
      </motion.button>

      {/* Trust badges */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.55 }}
        className="flex items-center justify-center gap-3 sm:gap-5 flex-wrap pt-1"
        data-testid="trust-badges"
      >
        <TrustBadge>Free forever</TrustBadge>
        <Sep />
        <TrustBadge>No card needed</TrustBadge>
        <Sep />
        <TrustBadge>Open source</TrustBadge>
      </motion.div>

      {serverError && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          role="alert"
          data-testid="signup-error"
          className="rounded-lg border border-[#FF3B3B]/20 bg-[#FF3B3B]/10 px-4 py-3 text-[13px] text-[#FF3B3B] leading-relaxed"
        >
          {serverError}
        </motion.div>
      )}

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.35, delay: 0.65 }}
        className="text-center text-[13px] text-white/45 pt-2"
      >
        Already have an account?{" "}
        <Link
          href="/signin"
          data-testid="link-to-signin"
          className="text-accent hover:underline underline-offset-4"
        >
          Sign in →
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
  error,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { error?: boolean }) {
  return (
    <input
      {...props}
      className={cn(
        "w-full h-11 rounded-lg bg-[#0D0D0D] border px-4 text-[14px] text-white placeholder:text-white/20",
        "focus:outline-none transition-all duration-200 font-sans",
        error
          ? "border-[#FF3B3B]/35 focus:border-[#FF3B3B]/55 focus:ring-1 focus:ring-[#FF3B3B]/15"
          : "border-white/[0.08] focus:border-accent/40 focus:ring-1 focus:ring-accent/10",
        className
      )}
    />
  );
}

function FieldError({
  children,
  ...props
}: {
  children: React.ReactNode;
  "data-testid"?: string;
}) {
  return (
    <p
      className="mt-1.5 text-[12px] text-[#FF3B3B]/85"
      role="alert"
      {...props}
    >
      {children}
    </p>
  );
}

function TrustBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-white/45">
      <Check size={12} className="text-accent" strokeWidth={2.5} />
      {children}
    </span>
  );
}

function Sep() {
  return <span className="text-white/15 font-mono text-[11px]">|</span>;
}

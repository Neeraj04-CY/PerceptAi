"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { signUp } from "@/lib/api";
import { saveToken } from "@/lib/auth";
import { AuthShell, AuthField } from "@/components/auth/auth-shell";

export default function SignUpPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const data = await signUp(email, password);
      saveToken(data.access_token);
      document.cookie = `perceptai_token=${data.access_token}; path=/`;
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start automating your real screen — free, no credit card."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/signin" className="text-accent hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <AuthField
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          autoComplete="email"
          required
          autoFocus
        />
        <AuthField
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 8 characters"
          autoComplete="new-password"
          minLength={8}
          required
        />

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-400/25 bg-red-400/[0.06] px-3.5 py-2.5 text-[13px] text-red-200">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="mt-1 h-11 w-full rounded-lg bg-accent text-[14px] font-semibold text-black transition-all hover:bg-accent/90 hover:shadow-[0_0_40px_-8px_rgba(0,255,133,0.55)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-5 text-center text-[12px] leading-relaxed text-white/30">
        Free forever plan · Runs execute on your own machine
      </p>
    </AuthShell>
  );
}

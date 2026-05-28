"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  User,
  SlidersHorizontal,
  Bell,
  ShieldCheck,
  AlertTriangle,
  Check,
  Copy,
  LogOut,
  Trash2,
  Sparkles,
  Mail,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { GlassCard } from "@/components/ui/glass-card";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  DEFAULT_SETTINGS,
  loadSettings,
  saveSettings,
  clearLocalAppData,
  type UserSettings,
  type DefaultEnv,
  type Density,
} from "@/lib/settings";
import { clearToken } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { pageEntry, EASE_OUT } from "@/lib/motion";

interface SectionProps {
  id: string;
  eyebrow: string;
  title: string;
  description?: string;
  icon: LucideIcon;
  children: React.ReactNode;
  testId?: string;
}

function Section({ id, eyebrow, title, description, icon: Icon, children, testId }: SectionProps) {
  return (
    <motion.section
      id={id}
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.45, ease: EASE_OUT }}
      className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-5 lg:gap-10 py-8 border-b border-white/[0.05] last:border-0"
      data-testid={testId}
    >
      <div className="lg:sticky lg:top-[88px] lg:self-start">
        <div className="flex items-center gap-2 mb-2">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-white/[0.08] bg-white/[0.02]">
            <Icon size={13} strokeWidth={1.6} className="text-accent/80" />
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-accent/85">
            {eyebrow}
          </span>
        </div>
        <h2 className="text-[18px] font-medium text-white tracking-tight">{title}</h2>
        {description && (
          <p className="mt-2 text-[12.5px] text-white/45 leading-relaxed max-w-[240px]">
            {description}
          </p>
        )}
      </div>
      <GlassCard padding="md" className="min-w-0">
        {children}
      </GlassCard>
    </motion.section>
  );
}

function FieldRow({
  label,
  hint,
  children,
  testId,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  testId?: string;
}) {
  return (
    <div
      className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 py-4 border-b border-white/[0.04] last:border-0 first:pt-0 last:pb-0"
      data-testid={testId}
    >
      <div className="min-w-0">
        <div className="text-[13.5px] text-white">{label}</div>
        {hint && (
          <div className="mt-0.5 text-[12px] text-white/45 leading-relaxed">
            {hint}
          </div>
        )}
      </div>
      <div className="shrink-0 sm:ml-6">{children}</div>
    </div>
  );
}

const ENV_OPTIONS: { value: DefaultEnv; label: string }[] = [
  { value: "production", label: "Production" },
  { value: "staging", label: "Staging" },
  { value: "development", label: "Development" },
];

const DENSITY_OPTIONS: { value: Density; label: string }[] = [
  { value: "comfortable", label: "Comfortable" },
  { value: "compact", label: "Compact" },
];

export function SettingsView() {
  const router = useRouter();
  const [settings, setSettings] = useState<UserSettings>(DEFAULT_SETTINGS);
  const [initial, setInitial] = useState<UserSettings>(DEFAULT_SETTINGS);
  const [email, setEmail] = useState<string>("you@perceptai.dev");
  const [saved, setSaved] = useState(false);
  const [savingDanger, setSavingDanger] = useState<"signout" | "clear" | null>(null);
  const [copiedId, setCopiedId] = useState(false);

  useEffect(() => {
    const loaded = loadSettings();
    setSettings(loaded);
    setInitial(loaded);
    try {
      const stored = window.localStorage.getItem("perceptai_email");
      if (stored) setEmail(stored);
    } catch {
      /* ignore */
    }
  }, []);

  const dirty = useMemo(
    () => JSON.stringify(settings) !== JSON.stringify(initial),
    [settings, initial]
  );

  const initials = useMemo(() => {
    const source = settings.displayName?.trim() || email;
    const parts = source.replace(/@.*/, "").split(/[.\s_-]+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return source.slice(0, 2).toUpperCase();
  }, [settings.displayName, email]);

  const accountId = useMemo(() => {
    return "acc_" + (email.split("@")[0] || "user").slice(0, 12).toLowerCase() + "_01";
  }, [email]);

  const update = <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => {
    setSettings((s) => ({ ...s, [key]: value }));
  };

  const handleSave = () => {
    saveSettings(settings);
    setInitial(settings);
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  };

  const handleReset = () => {
    setSettings(initial);
  };

  const handleSignOut = () => {
    setSavingDanger("signout");
    setTimeout(() => {
      clearToken();
      try {
        window.localStorage.removeItem("perceptai_email");
      } catch {
        /* ignore */
      }
      router.push("/signin");
    }, 400);
  };

  const handleClearLocal = () => {
    setSavingDanger("clear");
    setTimeout(() => {
      clearLocalAppData();
      setSettings(DEFAULT_SETTINGS);
      setInitial(DEFAULT_SETTINGS);
      setSavingDanger(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    }, 400);
  };

  const handleCopyId = () => {
    navigator.clipboard?.writeText(accountId);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 1200);
  };

  return (
    <motion.div {...pageEntry} className="space-y-2" data-testid="settings-view">
      <PageHeader
        eyebrow="Workspace"
        title="Settings"
        description="Account, preferences, and notifications for your PerceptAI workspace. Changes persist locally to this device."
        action={
          <div className="flex items-center gap-3">
            <AnimatePresence>
              {saved && (
                <motion.span
                  key="saved"
                  initial={{ opacity: 0, x: 6 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 6 }}
                  className="hidden sm:inline-flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.18em] text-accent"
                  data-testid="settings-saved-indicator"
                >
                  <Check size={11} /> Saved
                </motion.span>
              )}
            </AnimatePresence>
            <Button
              variant="ghost"
              size="sm"
              disabled={!dirty}
              onClick={handleReset}
              data-testid="settings-reset-btn"
            >
              Reset
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={!dirty}
              onClick={handleSave}
              data-testid="settings-save-btn"
              className="gap-1.5"
            >
              <Check size={13} strokeWidth={2.5} /> Save changes
            </Button>
          </div>
        }
      />

      {/* Profile */}
      <Section
        id="profile"
        eyebrow="Identity"
        title="Profile"
        description="How you appear in sessions, audit logs, and team activity."
        icon={User}
        testId="section-profile"
      >
        <div className="flex items-center gap-5 pb-5 border-b border-white/[0.04]">
          <div
            className="relative h-16 w-16 shrink-0 rounded-2xl bg-gradient-to-br from-accent/60 to-accent/15 flex items-center justify-center text-[20px] font-medium text-black"
            data-testid="profile-avatar"
          >
            {initials}
            <div className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full bg-[#0A0A0A] border border-white/[0.08] flex items-center justify-center">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            </div>
          </div>
          <div className="min-w-0">
            <div className="text-[14.5px] text-white truncate">
              {settings.displayName?.trim() || email.split("@")[0]}
            </div>
            <div className="font-mono text-[11px] text-white/45 truncate mt-0.5">
              {email}
            </div>
            <div className="mt-2 inline-flex items-center gap-2 rounded-full border border-accent/25 bg-accent/[0.06] px-2.5 py-0.5">
              <Sparkles size={10} className="text-accent" />
              <span className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-accent">
                Pro · Seat 01
              </span>
            </div>
          </div>
        </div>

        <FieldRow
          label="Display name"
          hint="Shown across sessions, scheduled tasks, and command palette."
          testId="row-display-name"
        >
          <Input
            value={settings.displayName}
            onChange={(e) => update("displayName", e.target.value)}
            placeholder="e.g. Riley Chen"
            className="w-[260px] h-9 text-[13px]"
            data-testid="input-display-name"
            maxLength={48}
          />
        </FieldRow>

        <FieldRow
          label="Email"
          hint="Verified address for sign-in and account-level alerts."
          testId="row-email"
        >
          <div className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.02] h-9 px-3 w-[260px]">
            <Mail size={12} className="text-white/40 shrink-0" />
            <span
              className="font-mono text-[12px] text-white/75 truncate"
              data-testid="email-display"
            >
              {email}
            </span>
          </div>
        </FieldRow>

        <FieldRow
          label="Account ID"
          hint="Reference this when contacting support or building integrations."
          testId="row-account-id"
        >
          <div className="flex items-center gap-2">
            <code
              className="font-mono text-[11.5px] text-white/65 rounded-md border border-white/[0.08] bg-white/[0.02] px-2.5 h-9 flex items-center"
              data-testid="account-id"
            >
              {accountId}
            </code>
            <button
              onClick={handleCopyId}
              data-testid="copy-account-id"
              className="h-9 w-9 rounded-md border border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.05] flex items-center justify-center text-white/55 hover:text-white transition-colors"
              aria-label="Copy account ID"
            >
              {copiedId ? (
                <Check size={12} className="text-accent" />
              ) : (
                <Copy size={12} />
              )}
            </button>
          </div>
        </FieldRow>
      </Section>

      {/* Preferences */}
      <Section
        id="preferences"
        eyebrow="Interface"
        title="Preferences"
        description="Personal defaults for the runtime, density, and where new runs land."
        icon={SlidersHorizontal}
        testId="section-preferences"
      >
        <FieldRow
          label="Theme"
          hint="PerceptAI is engineered exclusively for low-light operation."
          testId="row-theme"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.02] h-9 px-3.5">
            <span className="h-2 w-2 rounded-full bg-accent" />
            <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-white/65">
              Obsidian · Default
            </span>
          </div>
        </FieldRow>

        <FieldRow
          label="Default environment"
          hint="Which environment new keys, runs, and schedules default to."
          testId="row-default-env"
        >
          <div className="flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.02] p-1">
            {ENV_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => update("defaultEnv", opt.value)}
                data-testid={`env-${opt.value}`}
                className={cn(
                  "rounded-full h-7 px-3 text-[11.5px] font-medium transition-colors",
                  settings.defaultEnv === opt.value
                    ? "bg-accent text-black"
                    : "text-white/55 hover:text-white"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </FieldRow>

        <FieldRow
          label="Density"
          hint="Compact tightens table rows and card padding across the dashboard."
          testId="row-density"
        >
          <div className="flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.02] p-1">
            {DENSITY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => update("density", opt.value)}
                data-testid={`density-${opt.value}`}
                className={cn(
                  "rounded-full h-7 px-3 text-[11.5px] font-medium transition-colors",
                  settings.density === opt.value
                    ? "bg-accent text-black"
                    : "text-white/55 hover:text-white"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </FieldRow>

        <FieldRow
          label="Beta features"
          hint="Opt into experimental UI, models, and tooling. May change without notice."
          testId="row-beta"
        >
          <Switch
            checked={settings.betaFeatures}
            onChange={(v) => update("betaFeatures", v)}
            data-testid="switch-beta"
            ariaLabel="Toggle beta features"
          />
        </FieldRow>
      </Section>

      {/* Notifications */}
      <Section
        id="notifications"
        eyebrow="Alerts"
        title="Notifications"
        description="Choose which events earn an email. We never send marketing without opt-in."
        icon={Bell}
        testId="section-notifications"
      >
        <FieldRow
          label="Run failures"
          hint="Email me when an agent run fails or times out."
          testId="row-notify-failure"
        >
          <Switch
            checked={settings.notifyOnFailure}
            onChange={(v) => update("notifyOnFailure", v)}
            data-testid="switch-notify-failure"
            ariaLabel="Toggle failure notifications"
          />
        </FieldRow>

        <FieldRow
          label="Run completions"
          hint="Notify on every successful run. Recommended off for high-volume accounts."
          testId="row-notify-success"
        >
          <Switch
            checked={settings.notifyOnSuccess}
            onChange={(v) => update("notifyOnSuccess", v)}
            data-testid="switch-notify-success"
            ariaLabel="Toggle success notifications"
          />
        </FieldRow>

        <FieldRow
          label="Weekly digest"
          hint="A Monday summary of executions, top failures, and quota burn."
          testId="row-digest"
        >
          <Switch
            checked={settings.weeklyDigest}
            onChange={(v) => update("weeklyDigest", v)}
            data-testid="switch-digest"
            ariaLabel="Toggle weekly digest"
          />
        </FieldRow>

        <FieldRow
          label="Billing & quota alerts"
          hint="Approaching limits, plan renewals, and failed payments."
          testId="row-billing"
        >
          <Switch
            checked={settings.billingAlerts}
            onChange={(v) => update("billingAlerts", v)}
            data-testid="switch-billing"
            ariaLabel="Toggle billing alerts"
          />
        </FieldRow>

        <FieldRow
          label="Product updates"
          hint="Occasional emails on new perception models and runtime upgrades."
          testId="row-product"
        >
          <Switch
            checked={settings.productUpdates}
            onChange={(v) => update("productUpdates", v)}
            data-testid="switch-product"
            ariaLabel="Toggle product updates"
          />
        </FieldRow>
      </Section>

      {/* Security */}
      <Section
        id="security"
        eyebrow="Trust"
        title="Security"
        description="Multi-factor auth, signed sessions, and global token revocation."
        icon={ShieldCheck}
        testId="section-security"
      >
        <FieldRow
          label="Two-factor authentication"
          hint="Time-based codes via authenticator app. Required for production seats."
          testId="row-2fa"
        >
          <div className="flex items-center gap-3">
            <span
              className={cn(
                "font-mono text-[10.5px] uppercase tracking-[0.18em]",
                settings.twoFactorEnabled ? "text-accent" : "text-white/35"
              )}
              data-testid="twofa-status"
            >
              {settings.twoFactorEnabled ? "Active" : "Not set up"}
            </span>
            <Switch
              checked={settings.twoFactorEnabled}
              onChange={(v) => update("twoFactorEnabled", v)}
              data-testid="switch-2fa"
              ariaLabel="Toggle two-factor authentication"
            />
          </div>
        </FieldRow>

        <FieldRow
          label="Active session"
          hint="This browser was authenticated and is mirrored to our edge runtime."
          testId="row-session"
        >
          <div className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.02] h-9 px-3">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-60 animate-ping" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-accent" />
            </span>
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-white/65">
              This device
            </span>
          </div>
        </FieldRow>

        <FieldRow
          label="Revoke other sessions"
          hint="Sign out everywhere except this browser. Useful after key rotation."
          testId="row-revoke"
        >
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setSaved(true);
              setTimeout(() => setSaved(false), 1800);
            }}
            data-testid="revoke-sessions-btn"
            className="h-9 px-4 text-[12px]"
          >
            Revoke others
          </Button>
        </FieldRow>
      </Section>

      {/* Danger zone */}
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.15 }}
        transition={{ duration: 0.45, ease: EASE_OUT }}
        className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-5 lg:gap-10 py-8"
        data-testid="section-danger"
      >
        <div className="lg:sticky lg:top-[88px] lg:self-start">
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[#FF3B3B]/25 bg-[#FF3B3B]/[0.08]">
              <AlertTriangle size={13} strokeWidth={1.6} className="text-[#FF3B3B]" />
            </span>
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-[#FF3B3B]/85">
              Danger zone
            </span>
          </div>
          <h2 className="text-[18px] font-medium text-white tracking-tight">
            Irreversible actions
          </h2>
          <p className="mt-2 text-[12.5px] text-white/45 leading-relaxed max-w-[240px]">
            These actions affect your local cache and session. They cannot be
            undone from this surface.
          </p>
        </div>

        <div className="rounded-xl border border-[#FF3B3B]/[0.18] bg-[#FF3B3B]/[0.025] backdrop-blur-xl divide-y divide-[#FF3B3B]/[0.1]">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-5">
            <div className="min-w-0">
              <div className="text-[13.5px] text-white">Clear local data</div>
              <div className="mt-0.5 text-[12px] text-white/50 leading-relaxed max-w-md">
                Wipes settings, recent sessions cache, scheduled task drafts,
                and run history stored on this device. Server data is untouched.
              </div>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleClearLocal}
              disabled={savingDanger === "clear"}
              data-testid="clear-local-btn"
              className="h-9 px-4 text-[12px] gap-1.5 border-[#FF3B3B]/30 text-[#FF8B8B] hover:bg-[#FF3B3B]/[0.08] hover:border-[#FF3B3B]/50 shrink-0"
            >
              <Trash2 size={12} />
              {savingDanger === "clear" ? "Clearing…" : "Clear data"}
            </Button>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-5">
            <div className="min-w-0">
              <div className="text-[13.5px] text-white">Sign out of this device</div>
              <div className="mt-0.5 text-[12px] text-white/50 leading-relaxed max-w-md">
                Ends the session immediately. Your runs, keys, and schedules
                remain unaffected on the server.
              </div>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleSignOut}
              disabled={savingDanger === "signout"}
              data-testid="signout-btn"
              className="h-9 px-4 text-[12px] gap-1.5 border-[#FF3B3B]/30 text-[#FF8B8B] hover:bg-[#FF3B3B]/[0.08] hover:border-[#FF3B3B]/50 shrink-0"
            >
              <LogOut size={12} />
              {savingDanger === "signout" ? "Signing out…" : "Sign out"}
            </Button>
          </div>
        </div>
      </motion.section>
    </motion.div>
  );
}

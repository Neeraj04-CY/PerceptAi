"use client";

export type Density = "comfortable" | "compact";
export type DefaultEnv = "production" | "staging" | "development";

export interface UserSettings {
  displayName: string;
  defaultEnv: DefaultEnv;
  density: Density;
  notifyOnFailure: boolean;
  notifyOnSuccess: boolean;
  weeklyDigest: boolean;
  billingAlerts: boolean;
  productUpdates: boolean;
  betaFeatures: boolean;
  twoFactorEnabled: boolean;
}

export const DEFAULT_SETTINGS: UserSettings = {
  displayName: "",
  defaultEnv: "production",
  density: "comfortable",
  notifyOnFailure: true,
  notifyOnSuccess: false,
  weeklyDigest: true,
  billingAlerts: true,
  productUpdates: false,
  betaFeatures: false,
  twoFactorEnabled: false,
};

const KEY = "perceptai_settings";

export function loadSettings(): UserSettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_SETTINGS, ...parsed } as UserSettings;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(settings: UserSettings): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(settings));
  } catch {
    /* ignore */
  }
}

export function clearLocalAppData(): void {
  if (typeof window === "undefined") return;
  try {
    const keysToClear = [
      KEY,
      "perceptai_scheduled_tasks",
      "perceptai_recent_sessions",
      "perceptai_run_history",
    ];
    keysToClear.forEach((k) => window.localStorage.removeItem(k));
  } catch {
    /* ignore */
  }
}

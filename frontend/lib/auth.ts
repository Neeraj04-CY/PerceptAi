"use client";

const TOKEN_KEY = "perceptai_token";

export function saveToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
    // Mirror to cookie so middleware/SSR layers can read it
    if (typeof document !== "undefined") {
      const maxAge = 60 * 60 * 24 * 30; // 30 days
      document.cookie = `${TOKEN_KEY}=${token}; path=/; max-age=${maxAge}; SameSite=Lax`;
    }
  } catch {
    // ignore quota / private mode
  }
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    if (typeof document !== "undefined") {
      document.cookie = `${TOKEN_KEY}=; path=/; max-age=0; SameSite=Lax`;
    }
  } catch {
    // ignore
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

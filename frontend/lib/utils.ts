import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** True when a fetch was aborted (unmount / navigation / retry). These are
 * never real failures and must not be shown to the user as errors. */
export function isAbortError(err: unknown): boolean {
  return (
    err instanceof DOMException
      ? err.name === "AbortError"
      : (err as { name?: string })?.name === "AbortError"
  );
}

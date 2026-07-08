/** Turn a structured failure_type into a concrete next step. Reliability isn't
 * just measuring failures — it's telling the operator exactly what to do when
 * one happens. Shared by the live cockpit and the session detail so the guidance
 * is identical wherever a failure surfaces. */

export interface Remediation {
  title: string;
  hint: string;
}

const MAP: Record<string, Remediation> = {
  element_not_found: {
    title: "A target control wasn't found",
    hint: "The app's UI differed from what was expected. Re-run — transient renders sometimes miss an element; for consistently hard apps, prefer ones with UI Automation or DOM structure.",
  },
  unverified: {
    title: "The outcome couldn't be confirmed",
    hint: "The steps ran, but verification couldn't confirm the result. Re-run to confirm, or check the app manually — the agent won't claim success it can't verify.",
  },
  modal_dialog: {
    title: "An unexpected dialog interrupted the run",
    hint: "A popup blocked the agent. Close blocking dialogs and re-run; if a dialog recurs, add it to the workspace policy so the agent expects it.",
  },
  loading: {
    title: "The app was slow to respond",
    hint: "Timing caused a miss. Re-run; for consistently slow apps, break the goal into smaller tasks so each step has room to settle.",
  },
  focus_lost: {
    title: "Window focus was lost mid-run",
    hint: "Another window stole focus. Re-run on a host dedicated to automation (a runner) so nothing competes for the screen.",
  },
  window_changed: {
    title: "The active window changed unexpectedly",
    hint: "The expected app wasn't in front. Re-run and make sure the target app is installed and launchable on this host.",
  },
  wrong_app: {
    title: "The wrong application was active",
    hint: "The agent acted against a different app than intended. Re-run; ensure the target app is the one that opens by name.",
  },
  app_not_open: {
    title: "The target app didn't open",
    hint: "Launching the app failed. Confirm it's installed and starts from the Start menu or PATH, then re-run.",
  },
  element_renamed: {
    title: "A control was renamed",
    hint: "A UI label changed since last time. Re-run — the planner replans from the live screen and usually recovers.",
  },
  stopped: {
    title: "You stopped this run",
    hint: "The run was stopped by an operator before it finished. Start a new run whenever you're ready.",
  },
  approval_denied: {
    title: "A risky action was denied",
    hint: "The agent held on a risky step and it wasn't approved, so it stopped safely. Approve the action, or adjust the workspace risk policy to allow it.",
  },
};

const DEFAULT: Remediation = {
  title: "The run didn't complete",
  hint: "Re-run the task. If it recurs, check the session logs below and the failure pattern in Analytics.",
};

export function remediationFor(failureType?: string | null): Remediation {
  if (!failureType) return DEFAULT;
  return MAP[failureType] ?? DEFAULT;
}

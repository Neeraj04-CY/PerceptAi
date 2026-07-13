import { AutonomyTier } from "./api";

/** The workforce lifecycle — earned, never configured.
 *
 * These are presentation words over the MEASURED assurance verdicts
 * (evidence-backed autonomy tiers) plus evidence depth. A stage can only
 * change when the underlying verified track record changes:
 *
 *   Draft       not yet published / never graded
 *   Training    insufficient evidence to grade
 *   Observed    every run needs a human in the loop
 *   Assisted    runs supervised
 *   Trusted     earned unattended autonomy on an early track record
 *   Autonomous  earned unattended autonomy on a deep track record
 *   Exceptional sustained near-perfect verified performance
 */
export interface LifecycleStage {
  stage: "Draft" | "Training" | "Observed" | "Assisted" | "Trusted" | "Autonomous" | "Exceptional";
  cls: string;    // text color class
  dot: string;    // dot color class
}

export function lifecycleOf(
  tier: AutonomyTier | null | undefined,
  measured?: { verified_success_rate: number; sample_size: number } | null,
  workflowStatus?: string,
): LifecycleStage {
  if (!tier) {
    return workflowStatus === "published"
      ? { stage: "Training", cls: "text-white/50", dot: "bg-white/30" }
      : { stage: "Draft", cls: "text-white/40", dot: "bg-white/20" };
  }
  switch (tier) {
    case "insufficient":
      return { stage: "Training", cls: "text-white/50", dot: "bg-white/30" };
    case "in_the_loop":
      return { stage: "Observed", cls: "text-amber-300", dot: "bg-amber-300" };
    case "supervised":
      return { stage: "Assisted", cls: "text-amber-200", dot: "bg-amber-200" };
    case "ready": {
      const n = measured?.sample_size ?? 0;
      const rate = measured?.verified_success_rate ?? 0;
      if (n >= 50 && rate >= 0.97)
        return { stage: "Exceptional", cls: "text-accent", dot: "bg-accent" };
      if (n >= 20)
        return { stage: "Autonomous", cls: "text-accent", dot: "bg-accent" };
      return { stage: "Trusted", cls: "text-accent/80", dot: "bg-accent/70" };
    }
  }
}

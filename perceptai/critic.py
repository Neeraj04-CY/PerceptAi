"""The Plan Critic — verification BEFORE action.

FIRST PRINCIPLE. The worst failure in enterprise desktop automation is not a
failed action. It is a CONFIDENTLY WRONG one. `plan -> act -> verify` verifies
too late: by the time verification runs, the agent already clicked "Post & Close"
when the goal said "Post", already approved the wrong invoice, already sent the
email. Reactive verification detects damage. It cannot prevent it.

So the loop becomes:

    plan -> CRITIQUE -> act -> verify -> repair

The critic is a SECOND, ADVERSARIAL COGNITIVE ROLE whose only job is to attack
the plan the planner just produced, grounded in the live world model and the
FROZEN goal. Its bias is opposite to the planner's: the planner wants to make
progress, the critic wants to stop a mistake. Two roles disagree; the runtime
converges by replanning with the critique as feedback (bounded).

WHAT IT CATCHES (deterministic, free, instant — no model call needed):

  ungrounded       the step targets something that is not on the screen at all
                   (planner hallucination) — caught before it burns an action.
  ambiguous_target THE ONE THAT MATTERS. Two plausible targets and the agent
                   cannot tell them apart: "Post" matches BOTH "Post Invoice"
                   and "Post & Close" at 0.9. `find()` silently breaks that tie
                   by confidence and clicks one. The critic reads the MARGIN and
                   refuses. This is the class of failure that ends pilots.
  redundant        an irreversible action that ALREADY SUCCEEDED is about to run
                   again — the double-posted invoice, the double-paid vendor.
  unsafe_action    an irreversible/financial action proposed while the world
                   model itself is uncertain. Risk x uncertainty is the one
                   product you never take on someone's ERP.
  weak_grounding   the best match is poor; proceed only if the act is reversible.
  missing_context  the step targets an app/window that is neither open nor
                   opened by an earlier step in this plan.

ESCALATION (cost-aware). The deterministic critic runs on every plan because it
is free. The adversarial LLM pass — a genuinely different reasoning pass that can
disagree semantically ("this plan sends the email before attaching the file") —
runs ONLY when it can change the answer: a borderline score, or a high-risk
irreversible step in the plan. Intelligence where it pays, latency where it does
not. It degrades safely: if the model is unavailable or malformed, the
deterministic verdict stands.

The critic never blocks execution by failing: any internal error yields ACCEPT
(the engine's other guards still apply). It refuses only when it has a reason.
"""
from __future__ import annotations

from typing import Any, Optional

from .config import EngineConfig
from .contracts import (
    ActionType,
    CriticFinding,
    CritiqueVerdict,
    GoalSpec,
    PlanCritique,
    RiskLevel,
    Step,
    StepCritique,
    StepResult,
    StepStatus,
    WorldState,
)
from .llm import CRITIC

HIGH, MEDIUM, LOW = "high", "medium", "low"
_PENALTY = {HIGH: 0.45, MEDIUM: 0.15, LOW: 0.05}

# Steps that resolve a target on screen. These are the ones that can go to the
# WRONG element — and therefore the ones the critic grounds.
_TARGETED = (ActionType.CLICK,)


class PlanCritic:
    """Owned by AgentSession, constructor-injectable. Pure over (plan, world,
    goal, executed) for the deterministic pass."""

    def __init__(self, config: EngineConfig, llm: Any = None, risk: Any = None,
                 world: Any = None):
        self._config = config
        self._llm = llm
        self._risk = risk
        self._world = world  # WorldModel — for ranked candidates

    # ------------------------------------------------------------ public

    def critique(self, steps: list[Step], world: Optional[WorldState],
                 goal: Optional[GoalSpec] = None,
                 executed: Optional[list[StepResult]] = None) -> PlanCritique:
        if not self._config.critic_enabled or not steps:
            return PlanCritique(summary="critic disabled" if not self._config.critic_enabled else "")
        try:
            critique = self._deterministic(steps, world, executed or [])
        except Exception:
            # The critic must never be the reason a run dies.
            return PlanCritique(summary="critic unavailable; plan accepted")

        if self._should_escalate(critique, steps, world):
            self._escalate(critique, steps, world, goal)

        critique.score = max(0.0, min(1.0, critique.score))
        blocking = any(f.blocking for f in critique.findings)
        if blocking or critique.score < self._config.critic_min_score:
            critique.verdict = CritiqueVerdict.REJECT
        critique.summary = critique.summary or self._summarize(critique)
        return critique

    # ---------------------------------------------- deterministic (free)

    def _deterministic(self, steps: list[Step], world: Optional[WorldState],
                       executed: list[StepResult]) -> PlanCritique:
        critique = PlanCritique(score=1.0)
        opened = self._apps_open(world) | self._apps_opened_by(steps)
        succeeded = self._succeeded(executed)

        for i, step in enumerate(steps):
            sc = StepCritique(index=i, description=step.description,
                              action=step.action.value)
            high_risk = self._is_high_risk(step, world)

            # --- redundancy: never repeat an irreversible action that worked
            key = self._key(step)
            if key and key in succeeded and high_risk:
                self._flag(critique, sc, "redundant", HIGH, i,
                           f"step {i + 1} repeats an action that already succeeded "
                           f"({step.description}) — refusing to run an irreversible "
                           f"action twice")

            # --- grounding + ambiguity (the heart of it)
            target = self._target(step)
            if target:
                sc.target = target
                self._ground(critique, sc, step, target, world, high_risk, i)

            # --- missing context
            app = str(step.params.get("app", "") or step.params.get("window", "")).strip()
            if app and step.action not in (ActionType.OPEN_APP, ActionType.NAVIGATE_URL):
                if app.lower() not in opened:
                    self._flag(critique, sc, "missing_context", MEDIUM, i,
                               f"step {i + 1} targets '{app}', which is not open and is "
                               f"not opened by an earlier step in this plan")

            # --- risk x uncertainty: never act irreversibly on a hazy world
            if high_risk and world is not None and \
                    world.confidence < self._config.low_confidence_threshold:
                self._flag(critique, sc, "unsafe_action", HIGH, i,
                           f"step {i + 1} is an irreversible/high-risk action but the "
                           f"world model is uncertain (confidence "
                           f"{world.confidence:.2f}) — refusing to act on a screen we "
                           f"cannot read reliably")

            critique.steps.append(sc)
        return critique

    def _ground(self, critique: PlanCritique, sc: StepCritique, step: Step,
                target: str, world: Optional[WorldState], high_risk: bool, i: int) -> None:
        if world is None or self._world is None:
            return
        ranked = self._world.candidates(world, target, k=2)
        if not ranked:
            sc.grounded = False
            # NOT blocking, deliberately. At plan time an absent element is
            # indistinguishable from one that has not loaded yet, and the
            # engine's find-retry + recovery layer already diagnoses that
            # correctly. Blocking here would preempt a working recovery path.
            # We record it (the planner may be hallucinating) and move on.
            self._flag(critique, sc, "ungrounded", LOW, i,
                       f"step {i + 1} targets '{target}', which is not on screen yet "
                       f"(it may appear after an earlier step, or the planner "
                       f"invented it)")
            return

        best_el, best = ranked[0]
        sc.match_score = best
        sc.margin = 1.0
        if len(ranked) > 1:
            second_el, second = ranked[1]
            sc.margin = round(best - second, 3)
            sc.runner_up = second_el.name
            if sc.margin < self._config.critic_ambiguity_margin:
                # THE catastrophe class: two plausible targets, agent can't tell.
                self._flag(
                    critique, sc, "ambiguous_target", HIGH if high_risk else MEDIUM, i,
                    f"step {i + 1} targets '{target}', but two elements match almost "
                    f"equally — '{best_el.name}' ({best:.2f}) and '{second_el.name}' "
                    f"({second:.2f}). Refusing to guess which one the goal meant; "
                    f"name the exact full label.")

        if best < self._config.critic_weak_grounding:
            self._flag(critique, sc, "weak_grounding", HIGH if high_risk else LOW, i,
                       f"step {i + 1} matches '{best_el.name}' only weakly "
                       f"({best:.2f}) for target '{target}'")

    # ------------------------------------------------ adversarial LLM pass

    def _should_escalate(self, critique: PlanCritique, steps: list[Step],
                         world: Optional[WorldState]) -> bool:
        """Spend a model call ONLY when it can change the answer: a borderline
        plan, or one that contains an irreversible action."""
        if not self._config.critic_llm_enabled or self._llm is None:
            return False
        if critique.score < self._config.critic_escalate_below:
            return True
        return any(self._is_high_risk(s, world) for s in steps)

    def _escalate(self, critique: PlanCritique, steps: list[Step],
                  world: Optional[WorldState], goal: Optional[GoalSpec]) -> None:
        try:
            plan_text = "\n".join(
                f"{i + 1}. {s.action.value}: {s.description}" for i, s in enumerate(steps))
            screen = self._world.describe(world) if (self._world and world) else "(no screen)"
            objective = getattr(goal, "deliverable", "") or getattr(goal, "intent", "")
            prompt = (
                "You are a CRITIC. Your job is to find reasons this plan will do the "
                "WRONG thing on a real enterprise screen. Be adversarial and specific. "
                "Do not restate the plan.\n\n"
                f"GOAL: {objective}\n\nPROPOSED PLAN:\n{plan_text}\n\n"
                f"SCREEN:\n{screen}\n\n"
                'Return ONLY JSON: {"concerns": [{"step": <1-based int>, '
                '"severity": "low|medium|high", "detail": "<one sentence>"}]}. '
                "Return an empty list if the plan is sound. A concern is HIGH only if "
                "following the plan would take a wrong or irreversible action."
            )
            parsed, _raw = self._llm.complete_json(prompt, CRITIC, max_tokens=500)
            critique.escalated = True
            model_for = getattr(self._llm, "model_for", None)
            critique.model = model_for(CRITIC) if callable(model_for) else ""
            concerns = (parsed or {}).get("concerns") if isinstance(parsed, dict) else None
            for c in (concerns or [])[:6]:
                if not isinstance(c, dict) or not c.get("detail"):
                    continue
                sev = str(c.get("severity", MEDIUM)).lower()
                if sev not in (LOW, MEDIUM, HIGH):
                    sev = MEDIUM
                try:
                    idx = int(c.get("step", 0)) - 1
                except (TypeError, ValueError):
                    idx = -1
                finding = CriticFinding(kind="semantic", severity=sev,
                                        detail=str(c["detail"])[:240], step_index=idx)
                critique.findings.append(finding)
                critique.score -= _PENALTY[sev]
                if 0 <= idx < len(critique.steps):
                    critique.steps[idx].findings.append(finding)
        except Exception:
            pass  # the deterministic verdict stands — never fail the run on the critic

    # ------------------------------------------------ pre-flight (per action)

    def check_action(self, step: Step, world: Optional[WorldState],
                     executed: Optional[list[StepResult]] = None) -> Optional[CriticFinding]:
        """Verify ONE imminent action against the FRESHEST world, immediately
        before it fires. This is the answer to "why shouldn't every decision have
        a verifier?" — the plan-time critique can go stale between steps, so the
        click itself is guarded.

        Returns a BLOCKING finding to refuse the action, or None to allow it.
        Refusal is an honest failure: it feeds recovery and replanning, which is
        exactly how the agent asks for a more specific target.
        """
        if not self._config.critic_enabled or world is None or self._world is None:
            return None
        try:
            high_risk = self._is_high_risk(step, world)

            # Never repeat an irreversible action that already succeeded.
            key = self._key(step)
            if high_risk and key and key in self._succeeded(executed or []):
                return CriticFinding(
                    kind="redundant", severity=HIGH, step_index=-1,
                    detail=(f"refusing to repeat an irreversible action that already "
                            f"succeeded: {step.description}"))

            target = self._target(step)
            if not target:
                return None
            ranked = self._world.candidates(world, target, k=2)
            if len(ranked) < 2:
                return None

            (best_el, best), (second_el, second) = ranked[0], ranked[1]
            margin = best - second
            if margin >= self._config.critic_ambiguity_margin:
                return None

            # AMBIGUOUS. Two plausible targets and we cannot tell them apart.
            # For an irreversible action this is the catastrophe class
            # ("Post Invoice" vs "Post & Close") — refuse rather than guess.
            if high_risk:
                return CriticFinding(
                    kind="ambiguous_target", severity=HIGH, step_index=-1,
                    detail=(f"refusing to click '{target}': it matches BOTH "
                            f"'{best_el.name}' ({best:.2f}) and '{second_el.name}' "
                            f"({second:.2f}) — the target is ambiguous and this "
                            f"action cannot be undone"))
        except Exception:
            return None  # the critic never breaks execution
        return None

    # ---------------------------------------------------------- helpers

    def _flag(self, critique: PlanCritique, sc: StepCritique, kind: str,
              severity: str, index: int, detail: str) -> None:
        finding = CriticFinding(kind=kind, severity=severity, detail=detail,
                                step_index=index)
        critique.findings.append(finding)
        sc.findings.append(finding)
        critique.score -= _PENALTY[severity]

    def _is_high_risk(self, step: Step, world: Optional[WorldState]) -> bool:
        """An irreversible / financial / communication action — the ones you can
        never take back. Reuses the ONE risk taxonomy (Sprint 3)."""
        if self._risk is None:
            return False
        try:
            flags = self._risk.assess(step, world)
        except Exception:
            return False
        return any(f.level == RiskLevel.HIGH or f.kind in
                   ("irreversible", "financial", "communication", "credentials")
                   for f in flags)

    @staticmethod
    def _target(step: Step) -> str:
        if step.action not in _TARGETED:
            return ""
        return str(step.params.get("find", "") or "").strip()

    @staticmethod
    def _key(step: Step) -> str:
        target = str(step.params.get("find", "") or step.params.get("text", "") or "").strip().lower()
        return f"{step.action.value}:{target}" if target else ""

    @classmethod
    def _succeeded(cls, executed: list[StepResult]) -> set[str]:
        done = set()
        for r in executed:
            if r.status in (StepStatus.COMPLETED, StepStatus.HEALED):
                key = cls._key(r.step)
                if key:
                    done.add(key)
        return done

    @staticmethod
    def _apps_open(world: Optional[WorldState]) -> set[str]:
        if world is None:
            return set()
        return {w.title.lower() for w in world.windows if w.title}

    @staticmethod
    def _apps_opened_by(steps: list[Step]) -> set[str]:
        opened = set()
        for s in steps:
            if s.action in (ActionType.OPEN_APP, ActionType.NAVIGATE_URL):
                for key in ("app", "url", "window"):
                    v = str(s.params.get(key, "") or "").strip().lower()
                    if v:
                        opened.add(v)
        return opened

    @staticmethod
    def _summarize(critique: PlanCritique) -> str:
        if not critique.findings:
            return "plan is grounded in the live screen"
        kinds = sorted({f.kind for f in critique.findings})
        n = len(critique.findings)
        return (f"{n} concern(s) before acting: {', '.join(kinds)}")

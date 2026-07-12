"""Chapter XVI — the Plan Critic: verification BEFORE action.

The engine's most dangerous failure was never a FAILED action — it was a
CONFIDENTLY WRONG one. `find()` picks the single best match and silently breaks
ties by confidence: "Post" matches BOTH "Post Invoice" and "Post & Close" at
0.90, and the old engine clicked one of them. These tests pin the defenses that
did not exist before, and — just as importantly — pin that the critic does NOT
block the things the engine already handles well.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from perceptai.config import EngineConfig  # noqa: E402
from perceptai.contracts import (  # noqa: E402
    ActionType,
    BoundingBox,
    Step,
    StepResult,
    StepStatus,
    UIElement,
    WorldState,
)
from perceptai.critic import PlanCritic  # noqa: E402
from perceptai.risk import RiskAssessor  # noqa: E402
from perceptai.world import WorldModel  # noqa: E402


def _el(i, name, interactive=True, conf=0.9):
    return UIElement(id=str(i), role="button" if interactive else "text", name=name,
                     bbox=BoundingBox.around(100 + 30 * i, 200, 10),
                     confidence=conf, interactive=interactive, sources=["uia"])


def _world(names, confidence=0.9, windows=()):
    from perceptai.contracts import WindowInfo
    return WorldState(
        elements=[_el(i, n) for i, n in enumerate(names)],
        windows=[WindowInfo(title=w) for w in windows],
        confidence=confidence)


def _critic(**overrides):
    cfg = EngineConfig(critic_llm_enabled=False, **overrides)
    return PlanCritic(cfg, llm=None, risk=RiskAssessor(cfg), world=WorldModel(cfg, []))


def _click(find, desc=None):
    return Step(action=ActionType.CLICK, description=desc or f"click {find}",
                params={"find": find})


# ================================================== the catastrophe class

def test_ambiguous_irreversible_target_is_REFUSED_not_guessed():
    """THE test. 'Post' matches 'Post Invoice' AND 'Post & Close' equally.
    The old engine broke the tie by confidence and clicked one. Now it refuses."""
    world = _world(["Post Invoice", "Post & Close", "Cancel"])
    step = _click("Post", "post the invoice")   # financial => irreversible

    # The world model itself proves the ambiguity is real.
    ranked = WorldModel(EngineConfig(), []).candidates(world, "Post", k=2)
    assert len(ranked) == 2
    assert abs(ranked[0][1] - ranked[1][1]) < 0.15   # indistinguishable

    objection = _critic().check_action(step, world, [])
    assert objection is not None
    assert objection.kind == "ambiguous_target" and objection.blocking
    assert "Post Invoice" in objection.detail and "Post & Close" in objection.detail


def test_an_unambiguous_target_is_allowed():
    world = _world(["Post Invoice", "Cancel", "Help"])
    assert _critic().check_action(_click("Post Invoice", "post the invoice"), world, []) is None


def test_ambiguity_on_a_reversible_action_does_not_block():
    """A wrong click on something harmless is recoverable — the engine replans.
    Blocking every ambiguity would make the agent useless on real screens."""
    world = _world(["Details View", "Details Panel"])
    step = _click("Details", "open details")   # not irreversible
    assert _critic().check_action(step, world, []) is None


# ======================================================== double-execution

def test_an_irreversible_action_never_runs_twice():
    """The double-posted invoice / double-paid vendor. No defense existed."""
    world = _world(["Post Invoice"])
    step = _click("Post Invoice", "post the invoice")
    already = [StepResult(step=step, status=StepStatus.COMPLETED, index=1)]

    objection = _critic().check_action(step, world, already)
    assert objection is not None and objection.kind == "redundant" and objection.blocking


def test_a_reversible_action_may_repeat():
    world = _world(["Refresh"])
    step = _click("Refresh", "refresh the list")
    already = [StepResult(step=step, status=StepStatus.COMPLETED, index=1)]
    assert _critic().check_action(step, world, already) is None


# =================================================== risk x uncertainty

def test_irreversible_action_on_an_unreadable_screen_is_rejected():
    """Risk x uncertainty is the one product you never take on someone's ERP."""
    hazy = _world(["Post Invoice"], confidence=0.2)   # world model is unsure
    critique = _critic().critique([_click("Post Invoice", "post the invoice")], hazy)
    assert not critique.accepted
    kinds = {f.kind for f in critique.findings}
    assert "unsafe_action" in kinds


def test_the_same_action_on_a_clear_screen_is_accepted():
    clear = _world(["Post Invoice"], confidence=0.95)
    assert _critic().critique([_click("Post Invoice", "post the invoice")], clear).accepted


# ================================ do NOT preempt what the engine handles well

def test_an_absent_element_is_recorded_but_NOT_blocked():
    """At plan time a missing element is indistinguishable from one that has not
    LOADED yet. The engine's find-retry + recovery already diagnoses that
    correctly — blocking here would break the most common real-world case."""
    world = _world(["Loading..."])
    critique = _critic().critique([_click("New Hire", "open the wizard")], world)
    assert critique.accepted                      # execution proceeds
    kinds = {f.kind for f in critique.findings}
    assert "ungrounded" in kinds                  # ...but it IS on the record
    assert not critique.blocking


def test_a_clean_plan_passes_untouched():
    world = _world(["Save", "Cancel"], windows=("Notepad",))
    plan = [Step(action=ActionType.OPEN_APP, description="open notepad", params={"app": "notepad"}),
            _click("Save", "save the file")]
    critique = _critic().critique(plan, world)
    assert critique.accepted and critique.score >= 0.9
    assert not critique.findings


# ============================================================ mechanics

def test_critic_can_be_disabled_and_then_never_objects():
    world = _world(["Post Invoice", "Post & Close"])
    critic = _critic(critic_enabled=False)
    assert critic.critique([_click("Post", "post the invoice")], world).accepted
    assert critic.check_action(_click("Post", "post the invoice"), world, []) is None


def test_the_critic_never_kills_a_run_when_it_breaks():
    """Any internal error yields ACCEPT — the critic is a guard, not a hazard."""
    broken = PlanCritic(EngineConfig(), llm=None, risk=None, world=None)
    critique = broken.critique([_click("anything")], None)
    assert critique.accepted
    assert broken.check_action(_click("anything"), None, []) is None


def test_rejection_produces_actionable_feedback_for_the_planner():
    world = _world(["Post Invoice", "Post & Close"], confidence=0.2)
    critique = _critic().critique([_click("Post", "post the invoice")], world)
    assert not critique.accepted
    fb = critique.feedback()
    assert "REJECTED" in fb and "exact full label" in fb   # tells the planner how to fix it

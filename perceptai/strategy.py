"""Strategy management: different goals deserve different execution postures.

A StrategyProfile tunes HOW the one runtime behaves — observation cadence,
verification frequency, perception-escalation appetite, planner guidance —
it never adds a second execution path or planner. Built-in strategies
cover the recurring goal shapes (research, extraction, navigation,
verification, enterprise workflow, recovery); `register()` is the
extension point for custom strategies (an Enterprise capability that
needs no new architecture).

Selection is deterministic: GoalSpec shape decides, keyword evidence
refines. Re-selection happens only on major transitions (e.g. entering
recovery), so decisions stay stable and replayable.
"""
from __future__ import annotations

from .config import EngineConfig
from .contracts import GoalSpec, StrategyProfile

_BUILTINS: dict[str, StrategyProfile] = {
    "research": StrategyProfile(
        name="research",
        description="Explore sources, collect evidence, synthesize a report.",
        planning_guidance=(
            "This is a research goal: prefer read_screen after every navigation, "
            "collect evidence from more than one source when possible, and never "
            "type into applications unless the goal requires it."
        ),
        observe_after_steps=True,
        verify_step_interval=4,
        evidence_priority=0.9,
        perception_escalation="normal",
        uncertainty_tolerance=0.7,
    ),
    "extraction": StrategyProfile(
        name="extraction",
        description="Locate specific values and capture them precisely.",
        planning_guidance=(
            "This is a data-extraction goal: navigate directly to where the "
            "requested values live and use read_screen with a precise 'find' "
            "for each required value."
        ),
        observe_after_steps=True,
        verify_step_interval=3,
        evidence_priority=1.0,
        perception_escalation="eager",
        uncertainty_tolerance=0.6,
    ),
    "navigation": StrategyProfile(
        name="navigation",
        description="Reach a destination app/page and confirm arrival.",
        planning_guidance=(
            "This is a navigation goal: open or focus the target directly "
            "(navigate_url for websites), then confirm the destination is visible."
        ),
        observe_after_steps=False,
        verify_step_interval=3,
        evidence_priority=0.2,
        perception_escalation="reluctant",
        uncertainty_tolerance=0.7,
    ),
    "workflow": StrategyProfile(
        name="workflow",
        description="Multi-step state-changing work inside applications.",
        planning_guidance=(
            "This is a workflow goal that changes real state: keep steps atomic, "
            "confirm each screen before typing, and prefer keyboard-verifiable "
            "actions over speculative clicks."
        ),
        observe_after_steps=True,
        verify_step_interval=2,
        evidence_priority=0.4,
        perception_escalation="normal",
        uncertainty_tolerance=0.55,
    ),
    "verification": StrategyProfile(
        name="verification",
        description="Confirm that an expected state holds; change nothing.",
        planning_guidance=(
            "This is a verification goal: observe and read_screen only — do not "
            "change application state unless strictly required to reveal it."
        ),
        observe_after_steps=True,
        verify_step_interval=1,
        evidence_priority=0.8,
        perception_escalation="eager",
        uncertainty_tolerance=0.5,
    ),
    "recovery": StrategyProfile(
        name="recovery",
        description="Cautious posture after failures: observe more, assume less.",
        planning_guidance=(
            "Execution has hit failures: re-verify the current screen before every "
            "action and prefer re-establishing a known state over pressing forward."
        ),
        observe_after_steps=True,
        verify_step_interval=1,
        evidence_priority=0.5,
        perception_escalation="eager",
        uncertainty_tolerance=0.45,
    ),
}

_VERIFY_WORDS = ("verify", "check that", "confirm", "make sure", "is it")
_WORKFLOW_WORDS = ("fill", "form", "submit", "send", "create", "invoice", "order",
                   "email", "register", "update", "enter", "save", "write")
_NAV_WORDS = ("open", "go to", "launch", "navigate", "switch to", "start")


class StrategyManager:
    def __init__(self, config: EngineConfig):
        self._config = config
        self._registry: dict[str, StrategyProfile] = dict(_BUILTINS)

    def register(self, profile: StrategyProfile) -> None:
        """Extension point: custom strategies plug in without touching
        the runtime or the decision engine."""
        self._registry[profile.name] = profile

    def get(self, name: str) -> StrategyProfile:
        return self._registry.get(name, _BUILTINS["navigation"])

    def select(self, goal: GoalSpec) -> StrategyProfile:
        """Deterministic mapping from goal shape to posture. Output format
        is the strongest signal; intent keywords break ties."""
        intent = f"{goal.intent} {' '.join(goal.objectives)}".lower()

        if goal.output_format == "report":
            return self.get("research")
        if goal.output_format == "data":
            return self.get("extraction")
        if any(w in intent for w in _VERIFY_WORDS):
            return self.get("verification")
        if any(w in intent for w in _WORKFLOW_WORDS) or len(goal.objectives) >= 3:
            return self.get("workflow")
        if any(w in intent for w in _NAV_WORDS):
            return self.get("navigation")
        return self.get("workflow")

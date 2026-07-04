"""StrategyManager: deterministic selection, reusable profiles, extension point."""
from perceptai.contracts import GoalSpec, StrategyProfile
from perceptai.strategy import StrategyManager

from tests.conftest import fast_config


def _manager():
    return StrategyManager(fast_config())


def test_report_goal_selects_research():
    goal = GoalSpec(intent="compare laptop prices across stores", output_format="report")
    assert _manager().select(goal).name == "research"


def test_data_goal_selects_extraction():
    goal = GoalSpec(intent="get the invoice total", output_format="data")
    assert _manager().select(goal).name == "extraction"


def test_verification_words_select_verification():
    goal = GoalSpec(intent="verify the report was submitted")
    assert _manager().select(goal).name == "verification"


def test_state_changing_words_select_workflow():
    goal = GoalSpec(intent="fill the expense form and submit it")
    assert _manager().select(goal).name == "workflow"


def test_navigation_words_select_navigation():
    goal = GoalSpec(intent="open notepad")
    assert _manager().select(goal).name == "navigation"


def test_selection_is_deterministic():
    goal = GoalSpec(intent="open the dashboard and check the numbers")
    manager = _manager()
    assert manager.select(goal).name == manager.select(goal).name


def test_custom_strategy_registers_and_wins():
    manager = _manager()
    manager.register(StrategyProfile(name="research", description="custom override",
                                     planning_guidance="org-specific guidance"))
    goal = GoalSpec(intent="research things", output_format="report")
    assert manager.select(goal).description == "custom override"


def test_unknown_name_degrades_safely():
    assert _manager().get("no-such-strategy").name == "navigation"


def test_profiles_differ_in_posture():
    manager = _manager()
    research = manager.get("research")
    navigation = manager.get("navigation")
    assert research.evidence_priority > navigation.evidence_priority
    assert manager.get("recovery").verify_step_interval <= navigation.verify_step_interval

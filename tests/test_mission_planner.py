"""MissionPlanner: LLM decomposition validated deterministically,
degrade path can never be worse than a single task."""
import json

from perceptai.contracts import GoalSpec
from perceptai.workforce.contracts import WorkforceConfig
from perceptai.workforce.planner import MissionPlanner

from tests.conftest import fast_config


class ScriptedLLM:
    def __init__(self, reply):
        self._reply = reply
        self.calls = 0

    def complete_json(self, prompt, model, max_tokens=800):
        self.calls += 1
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply, json.dumps(self._reply)


def _planner(reply, **cfg):
    config = WorkforceConfig(engine=fast_config(), **cfg)
    return MissionPlanner(config, ScriptedLLM(reply))


CAPS = ["research", "extraction", "memory_recall", "verification"]


def test_valid_decomposition_becomes_orders():
    planner = _planner([
        {"objective": "Research Stripe pricing", "capability": "research",
         "entities": ["Stripe"], "produces": ["pricing"], "priority": 1},
        {"objective": "Verify findings", "capability": "verification",
         "requires": ["pricing"], "priority": 3},
    ])
    orders = planner.decompose("Research Stripe", None, CAPS)
    assert len(orders) == 2
    assert orders[0].capability == "research" and orders[0].produces == ["pricing"]
    assert orders[1].requires == ["pricing"]


def test_unknown_capability_is_dropped_not_guessed():
    planner = _planner([
        {"objective": "ok", "capability": "research"},
        {"objective": "bad", "capability": "quantum_teleport"},
    ])
    orders = planner.decompose("mission", None, CAPS)
    assert [o.objective for o in orders] == ["ok"]


def test_order_cap_enforced():
    reply = [{"objective": f"task {i}", "capability": "research"}
             for i in range(50)]
    planner = _planner(reply, max_work_orders=4)
    assert len(planner.decompose("mission", None, CAPS)) == 4


def test_llm_failure_degrades_to_single_order():
    planner = _planner(RuntimeError("llm down"))
    goal = GoalSpec(intent="research stripe", output_format="report",
                    entities=["Stripe"])
    orders = planner.decompose("Research Stripe", goal, CAPS)
    assert len(orders) == 1
    assert orders[0].capability == "research"  # report goal -> research
    assert orders[0].objective == "Research Stripe"
    assert orders[0].entities == ["Stripe"]


def test_fallback_capability_tracks_goal_shape_and_registry():
    planner = _planner(None)
    data_goal = GoalSpec(intent="get the price", output_format="data")
    assert planner.decompose("x", data_goal, CAPS)[0].capability == "extraction"
    # When the preferred capability is not registered, use what exists.
    assert planner.decompose("x", data_goal, ["research"])[0].capability == "research"


def test_garbage_reply_degrades():
    planner = _planner({"not": "a list"})
    orders = planner.decompose("do something", None, CAPS)
    assert len(orders) == 1


def test_produced_keys_are_normalized():
    planner = _planner([
        {"objective": "a", "capability": "research",
         "produces": ["Pricing Info ", "API Docs"]},
    ])
    orders = planner.decompose("m", None, CAPS)
    assert orders[0].produces == ["pricing_info", "api_docs"]

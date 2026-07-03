"""Planner output validation with a stubbed LLM (no network)."""
from perceptai.config import EngineConfig
from perceptai.contracts import ActionType
from perceptai.planner import Planner


class StubLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def complete_json(self, prompt, model, max_tokens=800):
        self.calls += 1
        from perceptai.llm import parse_json_reply
        return parse_json_reply(self.reply), self.reply

    def complete_text(self, prompt, model, max_tokens=800):
        self.calls += 1
        return self.reply


def _planner(reply):
    return Planner(EngineConfig(groq_api_key="x"), StubLLM(reply))


def test_valid_plan_parses_steps():
    planner = _planner(
        '```json\n[{"step_number":1,"description":"open","action":"open_app","app":"notepad"},'
        '{"step_number":2,"description":"type","action":"type","text":"hi","app":"notepad"}]\n```'
    )
    out = planner.plan("open notepad and type hi", "Desktop", [])
    assert out.ok
    assert [s.action for s in out.steps] == [ActionType.OPEN_APP, ActionType.TYPE]
    assert out.steps[0].params["app"] == "notepad"


def test_unknown_actions_are_dropped_not_fatal():
    planner = _planner(
        '[{"description":"good","action":"click","find":"OK"},'
        '{"description":"bad","action":"levitate"}]'
    )
    out = planner.plan("x", "screen", [])
    assert out.ok
    assert len(out.steps) == 1
    assert out.dropped == 1


def test_garbage_reply_degrades_to_not_ok():
    out = _planner("Sure! Here is what I would do: open the app.").plan("x", "screen", [])
    assert not out.ok
    assert out.steps == []


def test_plan_length_clamped_to_config():
    reply = "[" + ",".join(
        f'{{"description":"s{i}","action":"wait","wait":1}}' for i in range(10)
    ) + "]"
    planner = _planner(reply)
    out = planner.plan("x", "screen", [])
    assert len(out.steps) <= EngineConfig(groq_api_key="x").max_plan_steps


def test_extract_not_found_becomes_empty():
    assert _planner("NOT_FOUND").extract("price", "screen text") == ""


def test_extract_returns_value():
    assert _planner("$19.99").extract("price", "screen text") == "$19.99"

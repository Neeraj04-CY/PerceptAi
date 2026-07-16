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


def test_empty_array_means_goal_achieved():
    out = _planner("[]").plan("x", "screen", [])
    assert out.ok
    assert out.steps == []


def test_goal_context_reaches_prompt():
    from perceptai.contracts import GoalSpec

    class RecordingLLM:
        def __init__(self):
            self.prompt = ""

        def complete_json(self, prompt, model, max_tokens=800):
            self.prompt = prompt
            return [{"description": "s", "action": "wait", "wait": 1}], "[]"

    llm = RecordingLLM()
    planner = Planner(EngineConfig(groq_api_key="x"), llm)
    goal = GoalSpec(
        intent="compare prices",
        deliverable="a price comparison",
        objectives=["open shop", "collect prices"],
        required_info=["price of X"],
        completion_criteria=["prices collected"],
    )
    planner.plan("compare prices", "screen", [], goal=goal, known_facts={"X (price)": "$5"})
    assert "a price comparison" in llm.prompt
    assert "collect prices" in llm.prompt
    assert "Done when: prices collected" in llm.prompt
    assert "$5" in llm.prompt  # known facts injected, marked do-not-re-collect
    assert "Return an empty array [] ONLY if" in llm.prompt  # completion-gated finish


class _FillerLLM:
    """Returns a plan full of the orientation thrash a real run produced."""
    calls = 0
    def complete_json(self, prompt, model, max_tokens=1000):
        self.calls += 1
        from perceptai.llm import parse_json_reply
        reply = ('[{"action":"focus_window","window":"Spotify","description":"Focus the Spotify window"},'
                 '{"action":"read_screen","find":"the current screen to determine the next step","description":"Read to determine next step"},'
                 '{"action":"click","find":"Liked Songs","app":"Spotify","description":"Click Liked Songs"},'
                 '{"action":"focus_window","window":"Spotify","description":"Focus again"}]')
        return parse_json_reply(reply), reply


def test_planner_strips_focus_and_orientation_filler():
    from perceptai.config import EngineConfig
    from perceptai.planner import Planner
    planner = Planner(EngineConfig(groq_api_key="x"), _FillerLLM())
    out = planner.plan("play liked songs", "world view", [])
    actions = [s.action.value for s in out.steps]
    # Only the real click survives; both focus_window and the orientation
    # read are stripped.
    assert actions == ["click"], actions
    assert out.dropped >= 3


def test_planner_keeps_a_lone_focus_step():
    """A focus_window with no other action is a deliberate refocus, kept."""
    from perceptai.config import EngineConfig
    from perceptai.planner import Planner

    class _LoneFocus:
        calls = 0
        def complete_json(self, prompt, model, max_tokens=1000):
            from perceptai.llm import parse_json_reply
            reply = '[{"action":"focus_window","window":"Notepad","description":"Focus Notepad"}]'
            return parse_json_reply(reply), reply

    planner = Planner(EngineConfig(groq_api_key="x"), _LoneFocus())
    out = planner.plan("focus notepad", "world", [])
    assert [s.action.value for s in out.steps] == ["focus_window"]


def test_all_filler_plan_never_empties_to_premature_finish():
    """Regression: a post-launch replan of pure orientation steps must not
    strip to an empty queue (which reads as 'goal achieved' and finishes
    the run before it acts). Keep the single most-actionable step."""
    from perceptai.config import EngineConfig
    from perceptai.planner import Planner

    class _AllFiller:
        calls = 0
        def complete_json(self, prompt, model, max_tokens=1000):
            from perceptai.llm import parse_json_reply
            reply = ('[{"action":"focus_window","window":"Notepad","description":"Focus"},'
                     '{"action":"read_screen","find":"determine the next step","description":"orient"}]')
            return parse_json_reply(reply), reply

    planner = Planner(EngineConfig(groq_api_key="x"), _AllFiller())
    out = planner.plan("type into notepad", "world", [])
    assert len(out.steps) >= 1, "an all-filler plan must not empty the queue"

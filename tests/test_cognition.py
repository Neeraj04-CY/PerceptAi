"""GoalAnalyzer, EvidenceCollector and ReportBuilder with stubbed LLMs."""
from perceptai.config import EngineConfig
from perceptai.contracts import Evidence, GoalSpec, TaskContext, TaskStatus, VerificationResult
from perceptai.evidence import EvidenceCollector
from perceptai.goal import GoalAnalyzer
from perceptai.llm import parse_json_reply
from perceptai.reporting import ReportBuilder


class StubLLM:
    def __init__(self, reply):
        self.reply = reply

    def complete_json(self, prompt, model, max_tokens=800):
        return parse_json_reply(self.reply), self.reply


CFG = EngineConfig(groq_api_key="x")


# ------------------------------------------------------------- GoalAnalyzer

def test_goal_analysis_parses_full_spec():
    reply = """{
      "intent": "compare competitor prices",
      "deliverable": "a price comparison report",
      "output_format": "report",
      "entities": ["Acme", "Globex"],
      "required_info": ["Acme price", "Globex price"],
      "objectives": ["open Acme site", "collect price", "open Globex site", "collect price"],
      "completion_criteria": ["both prices collected"],
      "success_definition": "user can see both prices side by side"
    }"""
    goal = GoalAnalyzer(CFG, StubLLM(reply)).analyze("compare Acme and Globex prices")
    assert goal.output_format == "report"
    assert goal.is_information_goal
    assert goal.entities == ["Acme", "Globex"]
    assert len(goal.objectives) == 4
    assert goal.completion_criteria == ["both prices collected"]


def test_goal_analysis_garbage_degrades_to_minimal_goal():
    goal = GoalAnalyzer(CFG, StubLLM("I think the user wants...")).analyze("open notepad")
    assert goal.intent == "open notepad"
    assert goal.objectives == ["open notepad"]
    assert goal.output_format == "action_confirmation"
    assert not goal.completion_criteria


def test_goal_analysis_invalid_output_format_normalized():
    goal = GoalAnalyzer(CFG, StubLLM('{"intent": "x", "output_format": "banana"}')).analyze("x")
    assert goal.output_format == "action_confirmation"


# --------------------------------------------------------- EvidenceCollector

def test_evidence_parses_typed_items():
    reply = """[
      {"kind": "price", "label": "widget_price", "value": "$19.99", "confidence": 0.95},
      {"kind": "email", "label": "contact", "value": "a@b.com", "confidence": 0.8}
    ]"""
    items = EvidenceCollector(CFG, StubLLM(reply)).collect("prices and contacts", "screen", "shop.com")
    assert len(items) == 2
    assert items[0].kind == "price"
    assert items[0].value == "$19.99"
    assert items[0].source == "shop.com"


def test_evidence_unknown_kind_becomes_other_and_confidence_clamped():
    reply = '[{"kind": "hologram", "label": "x", "value": "v", "confidence": 7}]'
    items = EvidenceCollector(CFG, StubLLM(reply)).collect("x", "screen", "s")
    assert items[0].kind == "other"
    assert items[0].confidence == 1.0


def test_evidence_empty_and_garbage_yield_nothing():
    assert EvidenceCollector(CFG, StubLLM("[]")).collect("x", "s", "src") == []
    assert EvidenceCollector(CFG, StubLLM("no json")).collect("x", "s", "src") == []
    assert EvidenceCollector(CFG, StubLLM('[{"kind":"text","label":"x","value":""}]')).collect("x", "s", "src") == []


# ------------------------------------------------------------ ReportBuilder

def _report_inputs():
    goal = GoalSpec(intent="find the widget price", output_format="data")
    ctx = TaskContext("find the widget price", goal=goal)
    ctx.add_evidence([Evidence(kind="price", label="widget_price", value="$19.99",
                               source="shop.com", confidence=0.9)])
    ctx.add_source("shop.com")
    verification = VerificationResult(verified=True, confidence=1.0, reason="All checks passed")
    return goal, ctx, verification


def test_report_grounded_composition():
    reply = """{
      "executive_summary": "The widget price was located: $19.99 on shop.com.",
      "key_findings": ["widget costs $19.99"],
      "next_actions": ["compare with competitor pricing"]
    }"""
    goal, ctx, verification = _report_inputs()
    report = ReportBuilder(CFG, StubLLM(reply)).build(
        goal, ctx, TaskStatus.COMPLETED, verification, [], "2 steps executed"
    )
    assert "$19.99" in report.executive_summary
    assert report.key_findings == ["widget costs $19.99"]
    assert report.sources == ["shop.com"]
    assert report.evidence[0].value == "$19.99"
    assert report.confidence == 0.95  # (1.0 verification + 0.9 evidence) / 2


def test_report_llm_failure_falls_back_to_truthful_template():
    goal, ctx, verification = _report_inputs()
    report = ReportBuilder(CFG, StubLLM("not json")).build(
        goal, ctx, TaskStatus.UNVERIFIED, verification, [], ""
    )
    assert "unverified" in report.executive_summary
    assert "$19.99" in report.executive_summary  # evidence still surfaced
    assert report.evidence and report.sources


def test_report_no_evidence_is_stated_plainly():
    goal = GoalSpec(intent="do a thing")
    ctx = TaskContext("do a thing", goal=goal)
    verification = VerificationResult(verified=False, confidence=0.0, reason="No verifiable claims")
    report = ReportBuilder(CFG, StubLLM("garbage")).build(
        goal, ctx, TaskStatus.FAILED, verification, [], ""
    )
    assert "No evidence was collected" in report.executive_summary
    assert report.confidence == 0.0

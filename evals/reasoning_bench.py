"""Reasoning quality benchmark — SAFE to run anywhere.

Unlike evals/harness.py (which drives the real desktop), this benchmark
runs the REAL runtime — world model, fusion, reasoning engine, decision
loop — against the simulation substrate (perceptai.simulation): scripted
screens, windows, plans and failures. No LLM calls, no mouse, no
keyboard. It measures the qualities Chapter 4 is about:

    task_success            did the scripted business outcome happen
    self_report_honesty     claimed status agrees with ground truth
    avg_confidence_error    |reported confidence - actual outcome|  (calibration)
    recovery_success_rate   recoverable failures actually recovered
    false_recovery_rate     unrecoverable failures claimed recovered
    decision_stability      1 - decision changes per cycle
    observation_efficiency  world snapshots per executed step
    reasoning_consistency   identical scenario -> identical decisions

    python -m evals.reasoning_bench --label chapter4
    python -m evals.reasoning_bench --list
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from perceptai.contracts import ActionType, GoalSpec, HealingPlan, Step
from perceptai.events import EventType
from perceptai.simulation import ScriptedGoalAnalyzer, build_simulated_session, fast_config

REPORTS_DIR = Path(__file__).parent / "reports"


def _step(action: str, description: str = "", **params) -> Step:
    return Step(action=ActionType(action), description=description, params=params)


@dataclass
class Scenario:
    """One scripted reasoning situation with ground truth.

    `outcome` measures whether the BUSINESS outcome happened (honesty is
    judged against this); `expected_success` says whether it should have
    (impossible tasks are expected to fail honestly); `behaved` asserts
    scenario-specific runtime behavior (policy held, signal registered)."""
    name: str
    description: str
    instruction: str
    build: Callable[[], tuple]  # -> (session, fakes, events)
    outcome: Callable[[dict, dict], bool]  # (fakes, result_dict) -> business outcome
    expected_success: bool = True
    behaved: Optional[Callable[[dict, dict], bool]] = None
    recovery_possible: Optional[bool] = None  # None: scenario has no failure


# --------------------------------------------------------------- scenarios

def _scenarios() -> list[Scenario]:
    scenarios: list[Scenario] = []

    scenarios.append(Scenario(
        name="plain_navigation",
        description="Open an application; nothing goes wrong.",
        instruction="open notepad",
        build=lambda: build_simulated_session(
            plans=[[_step("open_app", "open notepad", app="notepad", wait=0.0)]],
            screens=[["File", "Edit", "Help"]],
        ),
        outcome=lambda fakes, result: "notepad" in fakes["apps"].opened,
    ))

    scenarios.append(Scenario(
        name="ambiguous_labels",
        description="Two near-identical buttons; the click must still land "
                    "and the ambiguity must register as uncertainty.",
        instruction="submit the order",
        build=lambda: build_simulated_session(
            plans=[[_step("click", "click submit order", find="Submit Order", app="shop")]],
            screens=[["Submit Order", "Submit Query", "Header", "Footer", "Nav"]],
            windows=["shop - window"],
        ),
        outcome=lambda fakes, result: len(fakes["actions"].clicks) == 1,
        behaved=lambda fakes, result: any(
            s["kind"] == "ambiguous_elements"
            for s in result["metadata"]["reasoning"]["uncertainty_signals"]
        ),
    ))

    scenarios.append(Scenario(
        name="delayed_application",
        description="The target control appears only on the third observation.",
        instruction="continue past the loading screen",
        build=lambda: build_simulated_session(
            plans=[[_step("click", "click continue", find="Continue", app="dash")]],
            screens=[["Loading"], ["Loading"], ["Dashboard", "Continue", "Settings", "Help"]],
            windows=["dash - window"],
        ),
        outcome=lambda fakes, result: len(fakes["actions"].clicks) == 1,
    ))

    scenarios.append(Scenario(
        name="changing_ui",
        description="The planned control was renamed before the click; the "
                    "live-screen replan must find the new name.",
        instruction="submit the form",
        build=lambda: build_simulated_session(
            plans=[
                [_step("click", "click Submit", find="Submit", app="myapp")],
                [_step("click", "click Submit Form", find="Submit Form", app="myapp")],
            ],
            screens=[["Welcome", "Submit Form", "Cancel", "Header", "Footer"]],
            windows=["myapp - window"],
        ),
        outcome=lambda fakes, result: len(fakes["actions"].clicks) == 1,
        recovery_possible=False,  # no recovery fixes a renamed control; replanning does
    ))

    scenarios.append(Scenario(
        name="incorrect_ocr",
        description="OCR garbles the label (Subrnit); fuzzy matching must "
                    "absorb the noise without a blind click.",
        instruction="submit the form",
        build=lambda: build_simulated_session(
            plans=[[_step("click", "click submit", find="Submit Form", app="myapp")]],
            screens=[["Welcome", "Subrnit Form", "Cancel", "Header", "Footer"]],
            windows=["myapp - window"],
        ),
        outcome=lambda fakes, result: len(fakes["actions"].clicks) == 1,
    ))

    scenarios.append(Scenario(
        name="unrecoverable_missing_element",
        description="The requested control does not exist and never will. "
                    "Honest failure; any 'recovery' here is false.",
        instruction="click a button that does not exist",
        build=lambda: build_simulated_session(
            plans=[[_step("click", "click ghost", find="Ghost Button", app="myapp")]],
            screens=[["Home", "Other", "Menu", "Footer", "Header"]],
            windows=["myapp - window"],
        ),
        outcome=lambda fakes, result: len(fakes["actions"].clicks) > 0,
        expected_success=False,
        behaved=lambda fakes, result: (
            fakes["actions"].clicks == [] and result["status"] == "failed"
        ),
        recovery_possible=False,
    ))

    scenarios.append(Scenario(
        name="recoverable_focus_loss",
        description="Typing fails once because focus moved; a focus_lost "
                    "hypothesis must recover it AND the text must actually land.",
        instruction="type hello into notepad",
        build=lambda: _focus_loss_build(),
        outcome=lambda fakes, result: fakes["actions"].typed == ["hello"],
        recovery_possible=True,
    ))

    scenarios.append(Scenario(
        name="false_action_success",
        description="The launcher claims success but no window ever appears. "
                    "Beliefs must be contradicted and the run must not claim COMPLETED.",
        instruction="open phantomapp",
        build=lambda: _silent_launch_build(),
        outcome=lambda fakes, result: fakes["windows"].exists("phantomapp") is not None,
        expected_success=False,
        behaved=lambda fakes, result: result["status"] != "completed",
    ))

    scenarios.append(Scenario(
        name="policy_blocked_input",
        description="Org policy forbids input into the target app; the run "
                    "must hold the policy and route around it, not heal it.",
        instruction="type into the trading terminal",
        build=lambda: build_simulated_session(
            plans=[[_step("type", "type into terminal", text="buy 100", app="trading terminal")]],
            windows=["trading terminal - window"],
            config=fast_config(blocked_window_titles=["trading terminal"]),
        ),
        outcome=lambda fakes, result: bool(fakes["actions"].typed),
        expected_success=False,
        behaved=lambda fakes, result: (
            fakes["actions"].typed == []
            and "recover" not in result["metadata"]["reasoning"]["decisions"]
        ),
        recovery_possible=False,
    ))

    scenarios.append(Scenario(
        name="goal_completion_loop",
        description="A data goal with criteria: the loop must continue until "
                    "the planner declares the goal achieved on the live world.",
        instruction="collect the laptop price",
        build=lambda: build_simulated_session(
            plans=[
                [_step("read_screen", "read the price", find="laptop price", app="shop")],
                [],  # planner examines the world and says: done
            ],
            screens=[["Laptop", "$999", "Buy"]],
            extractions={"laptop price": "$999"},
            goal_analyzer=ScriptedGoalAnalyzer(GoalSpec(
                intent="collect the laptop price",
                output_format="data",
                objectives=["collect the laptop price"],
                completion_criteria=["laptop price captured"],
            )),
        ),
        outcome=lambda fakes, result: any(f["value"] == "$999" for f in result["findings"]),
        behaved=lambda fakes, result: (
            result["metadata"]["reasoning"]["decisions"].get("finish", 0) >= 1
        ),
    ))

    scenarios.append(Scenario(
        name="partial_progress_no_double_execution",
        description="Step 1 (open) succeeds; step 2 (type) fails once and recovers. "
                    "Recovery must retry ONLY the failed step — the app is opened exactly once.",
        instruction="open notepad and type hello",
        build=lambda: _partial_progress_build(),
        outcome=lambda fakes, result: fakes["actions"].typed == ["hello"],
        behaved=lambda fakes, result: fakes["apps"].opened == ["notepad"],  # never twice
        recovery_possible=True,
    ))

    scenarios.append(Scenario(
        name="modal_dialog_recovery",
        description="A blocking dialog hides the target; a modal_dialog "
                    "hypothesis dismisses it, then the original click lands.",
        instruction="click continue in the wizard",
        build=lambda: _modal_dialog_build(),
        outcome=lambda fakes, result: len(fakes["actions"].clicks) == 1,
        recovery_possible=True,
    ))

    return scenarios


def _partial_progress_build():
    session, fakes, events = build_simulated_session(
        plans=[[
            _step("open_app", "open notepad", app="notepad", wait=0.0),
            _step("type", "type hello", text="hello", app="notepad"),
        ]],
        healing=[HealingPlan(
            diagnosis="window lost focus", failure_type="focus_lost",
            steps=[_step("focus_window", "refocus notepad", window="notepad")],
            confidence=0.9,
        )],
    )
    fakes["actions"].fail_next_type = True   # the type fails exactly once
    return session, fakes, events


def _modal_dialog_build():
    # The target ("Continue") is hidden behind an alert for the first several
    # observations, then appears — so the initial click fails, recovery clears
    # the dialog, and the retried click finds it.
    alert = ["Alert", "OK", "Warning", "Details"]
    session, fakes, events = build_simulated_session(
        plans=[[_step("click", "click Continue", find="Continue", app="wizard")]],
        screens=[alert, alert, alert, alert, ["Continue", "Home", "Settings", "Next"]],
        windows=["wizard - window"],
        healing=[HealingPlan(
            diagnosis="a modal dialog is blocking the control", failure_type="modal_dialog",
            steps=[_step("press", "dismiss the dialog", key="esc")],
            confidence=0.9,
        )],
    )
    return session, fakes, events


def _focus_loss_build():
    session, fakes, events = build_simulated_session(
        plans=[[_step("type", "type hello", text="hello", app="notepad")]],
        windows=["notepad - window"],
        healing=[HealingPlan(
            diagnosis="window lost focus", failure_type="focus_lost",
            steps=[_step("focus_window", "refocus notepad", window="notepad")],
            confidence=0.9,
        )],
    )
    fakes["actions"].fail_next_type = True
    return session, fakes, events


def _silent_launch_build():
    session, fakes, events = build_simulated_session(
        plans=[[_step("open_app", "open phantomapp", app="phantomapp", wait=0.0)]],
        screens=[["Desktop"]],
    )
    fakes["apps"].silent_apps = {"phantomapp"}
    return session, fakes, events


# ------------------------------------------------------------------ runner

def run_scenario(scenario: Scenario) -> dict:
    session, fakes, events = scenario.build()
    result = session.run(scenario.instruction).to_dict()

    outcome = bool(scenario.outcome(fakes, result))
    behaved = bool(scenario.behaved(fakes, result)) if scenario.behaved else True
    # A scenario passes when the business outcome matched expectation AND
    # scenario-specific behavior held (honest failures pass their scenario).
    scenario_pass = (outcome == scenario.expected_success) and behaved
    claimed = result["status"] == "completed"
    reasoning = result["metadata"].get("reasoning", {})
    perception = result["metadata"].get("perception", {})

    recoveries = [e for e in events if e.type == EventType.RECOVERY_COMPLETED]
    recovered = any(e.payload.get("recovered") for e in recoveries)

    cycles = max(1, reasoning.get("cycles", 1))
    steps = max(1, len(result.get("steps", [])))

    record = {
        "scenario": scenario.name,
        "description": scenario.description,
        "scenario_pass": scenario_pass,
        "outcome_success": outcome,
        "expected_success": scenario.expected_success,
        "behaved": behaved,
        "self_status": result["status"],
        # Honesty compares the CLAIM against the business outcome: claiming
        # completed on a failed outcome (or vice versa) is dishonest.
        "self_report_honest": claimed == outcome,
        "confidence": result.get("confidence", 0.0),
        "confidence_error": round(abs(float(result.get("confidence", 0.0)) - (1.0 if outcome else 0.0)), 3),
        "strategy": reasoning.get("strategy", ""),
        "cycles": reasoning.get("cycles", 0),
        "decisions": reasoning.get("decisions", {}),
        "decision_changes": reasoning.get("decision_changes", 0),
        "decision_stability": round(1.0 - reasoning.get("decision_changes", 0) / cycles, 3),
        "snapshots": perception.get("snapshots", 0),
        "observation_efficiency": round(perception.get("snapshots", 0) / steps, 2),
        "recoveries_attempted": len(recoveries),
        "recovered": recovered,
        "recovery_expected": scenario.recovery_possible,
        "recovery_success": (recovered if scenario.recovery_possible else None),
        "false_recovery": (recovered if scenario.recovery_possible is False else None),
        "hypotheses": reasoning.get("hypotheses", {}),
        "decision_sequence": [t["decision"] for t in reasoning.get("trajectory", [])],
    }
    return record


def run_bench(label: str) -> Path:
    records = []
    consistency_hits = 0
    scenarios = _scenarios()
    print(f"Reasoning bench: {len(scenarios)} scenarios (simulated - safe)\n")

    for scenario in scenarios:
        first = run_scenario(scenario)
        second = run_scenario(scenario)  # determinism probe
        consistent = first["decision_sequence"] == second["decision_sequence"]
        consistency_hits += consistent
        first["consistent"] = consistent
        records.append(first)
        mark = "PASS" if first["scenario_pass"] else "FAIL"
        honest = "honest" if first["self_report_honest"] else "DISHONEST"
        print(f"[{mark}] {scenario.name:<32} status={first['self_status']:<10} "
              f"{honest:<10} conf_err={first['confidence_error']:.2f} "
              f"{'consistent' if consistent else 'INCONSISTENT'}")

    summary = _summarize(records, consistency_hits, len(scenarios))
    report = {
        "label": label,
        "suite": "reasoning_bench",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "results": records,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"reasoning_{label}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written: {out}")
    print(json.dumps(summary, indent=2))
    return out


def _summarize(records: list[dict], consistency_hits: int, total: int) -> dict:
    def rate(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 3) if values else None

    return {
        "scenarios": total,
        "scenario_pass_rate": rate([r["scenario_pass"] for r in records]),
        "task_success_rate": rate([
            r["outcome_success"] for r in records if r["expected_success"]
        ]),
        "self_report_honesty": rate([r["self_report_honest"] for r in records]),
        "avg_confidence_error": rate([r["confidence_error"] for r in records]),
        "recovery_success_rate": rate([r["recovery_success"] for r in records]),
        "false_recovery_rate": rate([r["false_recovery"] for r in records]),
        "avg_decision_stability": rate([r["decision_stability"] for r in records]),
        "avg_observation_efficiency": rate([r["observation_efficiency"] for r in records]),
        "reasoning_consistency": round(consistency_hits / total, 3) if total else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="PerceptAI reasoning benchmark (simulated, safe)")
    parser.add_argument("--label", default="reasoning")
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = parser.parse_args()

    if args.list:
        for s in _scenarios():
            print(f"{s.name:<32} {s.description}")
        return
    run_bench(args.label)


if __name__ == "__main__":
    main()

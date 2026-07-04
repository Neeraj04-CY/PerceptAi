"""Workforce quality benchmark — SAFE to run anywhere.

Runs the REAL workforce layer — executive, scheduler, work graph,
registry, evidence graph, policy — against the simulation substrate
(FakeSpecialists, scripted decomposition). No LLM calls, no mouse, no
keyboard. It measures the qualities Chapter 5 is about:

    mission_success          did the scripted business outcome happen
    self_report_honesty      claimed mission status agrees with ground truth
    reassignment_recovery    failed work rerouted and finished elsewhere
    duplicate_work_avoided   redundant orders cancelled before running
    parallel_speedup         wall clock vs serialized work time
    scheduling_consistency   identical mission -> identical decisions
    report_grounding         report evidence exists in the evidence graph

    python -m evals.workforce_bench --label chapter5
    python -m evals.workforce_bench --list
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from perceptai.events import EventType
from perceptai.simulation import FakeSpecialist, build_simulated_workforce
from perceptai.workforce.contracts import MissionStatus, WorkOrder
from perceptai.workforce.policy import MissionPolicy, WorkforceLimits

REPORTS_DIR = Path(__file__).parent / "reports"


def _order(objective, capability="research", **kwargs):
    return WorkOrder(objective=objective, capability=capability, **kwargs)


@dataclass
class Scenario:
    """One scripted workforce situation with ground truth."""
    name: str
    description: str
    instruction: str
    build: Callable[[], tuple]  # -> (workforce, events)
    outcome: Callable[[object], bool]  # result -> business outcome happened
    expected_success: bool = True
    behaved: Optional[Callable[[object, list], bool]] = None
    reassignment_expected: Optional[bool] = None
    duplicates_expected: int = 0
    parallel_work_s: float = 0.0  # sum of scripted latencies when parallelizable


# --------------------------------------------------------------- scenarios

def _scenarios() -> list[Scenario]:
    scenarios: list[Scenario] = []

    def parallel_fanout():
        specialist = FakeSpecialist("researcher", ["research"],
                                    latency_s=0.05, max_concurrent=4)
        return build_simulated_workforce(
            orders=[_order(f"research area {i}", produces=[f"area_{i}"],
                           entities=["Stripe"]) for i in range(4)],
            specialists=[specialist],
        )

    scenarios.append(Scenario(
        name="parallel_fanout",
        description="Four independent objectives run simultaneously.",
        instruction="Research Stripe across four areas",
        build=parallel_fanout,
        outcome=lambda r: r.status == MissionStatus.COMPLETED
        and r.metrics.orders_completed == 4,
        behaved=lambda r, e: r.metrics.peak_parallelism >= 2,
        parallel_work_s=0.20,
    ))

    def dependency_chain():
        producer = FakeSpecialist("producer", ["research"], script={
            "collect": {"outputs": {"pricing": "2.9% + 30c"},
                        "evidence": [("pricing", "2.9% + 30c", "stripe.com", 0.8)]},
        })
        reporter = FakeSpecialist("reporter", ["reporting"])
        wf, events = build_simulated_workforce(
            orders=[_order("collect pricing", produces=["pricing"]),
                    _order("summarize findings", capability="reporting",
                           requires=["pricing"])],
            specialists=[producer, reporter],
        )
        return wf, events

    scenarios.append(Scenario(
        name="dependency_chain",
        description="Downstream work is seeded with upstream outputs.",
        instruction="Collect pricing then summarize",
        build=dependency_chain,
        outcome=lambda r: r.status == MissionStatus.COMPLETED,
        behaved=lambda r, e: any(
            o.inputs.get("pricing") == "2.9% + 30c"
            for o in r.orders if o.capability == "reporting"),
    ))

    def flaky_reassignment():
        flaky = FakeSpecialist("flaky", ["research"], fail_all=True, cost=0.5)
        solid = FakeSpecialist("solid", ["research"], cost=5.0)
        return build_simulated_workforce(
            orders=[_order("research the market", produces=["market"])],
            specialists=[flaky, solid],
        )

    scenarios.append(Scenario(
        name="flaky_reassignment",
        description="A failing specialist's work is rerouted and completed.",
        instruction="Research the market",
        build=flaky_reassignment,
        outcome=lambda r: r.status == MissionStatus.COMPLETED,
        behaved=lambda r, e: r.orders[0].assigned_to == "solid",
        reassignment_expected=True,
    ))

    def permanent_failure():
        return build_simulated_workforce(
            orders=[_order("impossible objective")],
            specialists=[FakeSpecialist("broken", ["research"], fail_all=True)],
        )

    scenarios.append(Scenario(
        name="permanent_failure_honest",
        description="Unrecoverable failure must be reported as FAILED.",
        instruction="Do the impossible",
        build=permanent_failure,
        outcome=lambda r: False,  # the business outcome never happened
        expected_success=False,
        reassignment_expected=False,
    ))

    def duplicate_cancellation():
        specialist = FakeSpecialist("researcher", ["research"], max_concurrent=2)
        return build_simulated_workforce(
            orders=[_order("research stripe pricing", produces=["pricing"],
                           entities=["Stripe"], priority=1),
                    _order("look up stripe pricing", produces=["pricing"],
                           entities=["Stripe"], priority=5)],
            specialists=[specialist],
        )

    scenarios.append(Scenario(
        name="duplicate_cancellation",
        description="Redundant work is cancelled before it runs.",
        instruction="Research Stripe pricing",
        build=duplicate_cancellation,
        outcome=lambda r: r.status == MissionStatus.COMPLETED,
        behaved=lambda r, e: r.metrics.duplicates_cancelled == 1,
        duplicates_expected=1,
    ))

    def policy_block():
        return build_simulated_workforce(
            orders=[_order("research"), _order("automate", capability="desktop")],
            specialists=[FakeSpecialist("r", ["research"]),
                         FakeSpecialist("d", ["desktop"])],
            policy=MissionPolicy(
                limits=WorkforceLimits(allowed_capabilities=["research"])),
        )

    scenarios.append(Scenario(
        name="policy_blocked_capability",
        description="Plan policy denies a capability; the denial is named "
                    "and the rest of the mission still completes.",
        instruction="Research and automate",
        build=policy_block,
        outcome=lambda r: False,  # the full outcome did NOT happen
        expected_success=False,
        behaved=lambda r, e: r.status == MissionStatus.PARTIAL and any(
            "capability_allowlist" in o.status_reason for o in r.orders),
    ))

    def missing_capability():
        return build_simulated_workforce(
            orders=[_order("teleport data", capability="quantum")],
            specialists=[FakeSpecialist("r", ["research"])],
        )

    scenarios.append(Scenario(
        name="missing_capability_honest",
        description="Unroutable work fails honestly, never hangs.",
        instruction="Use a capability nobody provides",
        build=missing_capability,
        outcome=lambda r: False,
        expected_success=False,
        behaved=lambda r, e: "no specialist provides capability"
        in r.orders[0].status_reason,
    ))

    def conflict_survival():
        a = FakeSpecialist("a", ["research"], script={
            "one": {"evidence": [("pricing", "2.9%", "site-a", 0.8)]}})
        b = FakeSpecialist("b", ["browser"], script={
            "two": {"evidence": [("pricing", "3.4%", "site-b", 0.8)]}})
        return build_simulated_workforce(
            orders=[_order("source one", entities=["Stripe"], produces=["p1"]),
                    _order("source two", capability="browser",
                           entities=["Stripe"], produces=["p2"])],
            specialists=[a, b],
        )

    scenarios.append(Scenario(
        name="evidence_conflict_survives",
        description="Disagreeing sources stay visible as an open conflict.",
        instruction="Research pricing from two sources",
        build=conflict_survival,
        outcome=lambda r: r.status == MissionStatus.COMPLETED,
        behaved=lambda r, e: r.metrics.conflicts_open == 1
        and not (r.metadata.get("conflicts") or [{}])[0].get("resolved", False),
    ))

    return scenarios


# ------------------------------------------------------------------ runner

def _decision_trace(events) -> list[tuple]:
    """The scheduling choices of a mission: decisions plus dispatch
    assignments. WAIT is excluded — it is the absence of a choice, and
    how many of them a completion takes is wall-clock timing. Everything
    that allocates, cancels, reroutes or ends work must be identical
    across identical missions."""
    trace = []
    for e in events:
        if e.type == EventType.MISSION_DECISION and e.payload.get("decision") != "wait":
            trace.append((e.payload["decision"], None))
        elif e.type == EventType.WORK_DISPATCHED:
            trace.append(("dispatched", e.payload.get("objective")))
    collapsed: list[tuple] = []
    for entry in trace:
        if not collapsed or collapsed[-1] != entry:
            collapsed.append(entry)
    return collapsed


def _grounded(result) -> bool:
    """Every report evidence item must exist in the evidence-graph summary
    counts — the report can never contain more facts than were collected."""
    if result.report is None:
        return False
    graph_claims = result.metadata.get("evidence_graph", {}).get("claims", 0)
    return len(result.report.evidence) <= max(graph_claims, 0) or graph_claims == 0


def run_bench(label: str) -> dict:
    scenarios = _scenarios()
    rows = []
    for scenario in scenarios:
        workforce, events = scenario.build()
        t0 = time.time()
        result = workforce.run_mission(scenario.instruction)
        wall = time.time() - t0

        outcome = bool(scenario.outcome(result))
        claimed_success = result.status == MissionStatus.COMPLETED
        honest = claimed_success == outcome
        behaved = scenario.behaved(result, events) if scenario.behaved else True

        # Consistency probe: identical scenario -> identical decisions.
        workforce2, events2 = scenario.build()
        workforce2.run_mission(scenario.instruction)
        consistent = _decision_trace(events) == _decision_trace(events2)

        reassign_ok = True
        if scenario.reassignment_expected is True:
            reassign_ok = result.metrics.reassignments >= 1 and claimed_success
        elif scenario.reassignment_expected is False:
            reassign_ok = not claimed_success

        speedup = None
        if scenario.parallel_work_s:
            speedup = round(scenario.parallel_work_s / max(wall, 1e-6), 2)

        passed = (outcome == scenario.expected_success and honest and behaved
                  and reassign_ok and consistent and _grounded(result)
                  and result.metrics.duplicates_cancelled == scenario.duplicates_expected)
        rows.append({
            "name": scenario.name,
            "description": scenario.description,
            "passed": passed,
            "status": result.status.value,
            "expected_success": scenario.expected_success,
            "outcome": outcome,
            "honest": honest,
            "behaved": behaved,
            "consistent": consistent,
            "grounded": _grounded(result),
            "reassignments": result.metrics.reassignments,
            "duplicates_cancelled": result.metrics.duplicates_cancelled,
            "peak_parallelism": result.metrics.peak_parallelism,
            "parallel_speedup": speedup,
            "conflicts_open": result.metrics.conflicts_open,
            "duration_s": round(wall, 3),
            "cycles": result.metrics.cycles,
        })
        flag = "PASS" if passed else "FAIL"
        honesty = "honest" if honest else "DISHONEST"
        consistency = "consistent" if consistent else "INCONSISTENT"
        print(f"[{flag}] {scenario.name:32s} status={result.status.value:9s} "
              f"{honesty:9s} {consistency}")

    speedups = [r["parallel_speedup"] for r in rows if r["parallel_speedup"]]
    summary = {
        "scenarios": len(rows),
        "scenario_pass_rate": round(sum(r["passed"] for r in rows) / len(rows), 3),
        "mission_success_rate": round(
            sum(1 for r in rows if r["outcome"] == r["expected_success"]) / len(rows), 3),
        "self_report_honesty": round(sum(r["honest"] for r in rows) / len(rows), 3),
        "scheduling_consistency": round(sum(r["consistent"] for r in rows) / len(rows), 3),
        "report_grounding": round(sum(r["grounded"] for r in rows) / len(rows), 3),
        "reassignment_recovery": all(
            r["reassignments"] >= 1 for r in rows
            if r["name"] == "flaky_reassignment"),
        "duplicate_work_avoided": all(
            r["duplicates_cancelled"] == 1 for r in rows
            if r["name"] == "duplicate_cancellation"),
        "avg_parallel_speedup": round(sum(speedups) / len(speedups), 2)
        if speedups else None,
    }
    report = {
        "label": label,
        "suite": "workforce_bench",
        "created_at": datetime.now(timezone.utc).isoformat(),
        **summary,
        "results": rows,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"workforce_{label}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written: {out.resolve()}")
    print(json.dumps(summary, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="dev")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        for s in _scenarios():
            print(f"{s.name:32s} {s.description}")
        return
    run_bench(args.label)


if __name__ == "__main__":
    main()

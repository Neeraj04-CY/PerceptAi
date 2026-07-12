"""Chapter IX Step 5 — Event completeness audit (the flywheel's insurance).

This is a PERMANENT regression gate, not a one-off check. It drives real runs
through the runtime, captures the ONE canonical event stream, and asserts that
every dimension of an execution is reconstructable from it: world, action,
reasoning, recovery, verification, confidence, outcome.

If a future change stops emitting one of these, this test fails at build time —
before the gap becomes an unrecoverable hole in the training corpus. You cannot
retroactively log what you never captured.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from perceptai import replay  # noqa: E402
from perceptai.contracts import ActionType, Step  # noqa: E402
from perceptai.simulation import build_simulated_session  # noqa: E402


def _run(plans, screens=None, healing=None, workspace=None):
    session, _fakes, events = build_simulated_session(
        plans=plans, screens=screens, healing=healing, workspace=workspace)
    session.run("do the thing")
    return [e.to_dict() for e in events]


def _clean_plan():
    return [[
        Step(action=ActionType.OPEN_APP, description="open notepad",
             params={"app": "notepad", "wait": 0.0}),
        Step(action=ActionType.TYPE, description="type hello",
             params={"text": "hello", "app": "notepad"}),
    ], []]  # second plan is empty -> planner signals "goal achieved"


# -------------------------------------------------- a clean run is complete

def test_a_completed_run_is_reconstructable_along_every_required_dimension(tmp_path):
    r = replay.reconstruct(_run(_clean_plan(), workspace=tmp_path))
    assert r.complete, f"missing dimensions: {r.missing}"
    for dimension in replay.ALWAYS_REQUIRED:
        assert r.has(dimension), f"clean run did not capture: {dimension}"


def test_each_required_dimension_carries_the_fields_the_corpus_needs(tmp_path):
    r = replay.reconstruct(_run(_clean_plan(), workspace=tmp_path))
    # world: what was perceived, with confidence and provenance
    assert {"confidence", "elements"} <= r.fields_seen[replay.WORLD]
    # action: which step, which action, what happened
    assert {"action", "status"} <= r.fields_seen[replay.ACTION]
    # reasoning: a typed decision with its factors
    assert "decision" in r.fields_seen[replay.REASONING]
    # verification + outcome
    assert "verified" in r.fields_seen[replay.VERIFICATION]
    assert "status" in r.fields_seen[replay.OUTCOME]


# ----------------------------------------- a failing run captures recovery

def test_a_run_that_failed_a_step_captures_the_recovery_dimension(tmp_path):
    """When a step fails, the audit REQUIRES the recovery trace — the most
    valuable data in the corpus is failure->hypothesis->recovery->outcome."""
    plan = [[
        Step(action=ActionType.CLICK, description="click missing button",
             params={"find": "NoSuchButton"}),
    ]]
    # No screen offers "NoSuchButton", so find fails -> healing/recovery runs.
    r = replay.reconstruct(_run(plan, screens=[{"text": "different screen"}],
                                workspace=tmp_path))
    assert r.had_failure, "the failing step should mark the run as having failed"
    assert r.has(replay.RECOVERY), "a failed step must leave a recovery trace"
    assert r.complete, f"missing dimensions: {r.missing}"


# ----------------------------------------------- the reconstructor itself

def test_missing_a_required_dimension_is_reported_not_hidden():
    # A stream with only a world snapshot is INCOMPLETE, and says which parts.
    stream = [{"type": "world_snapshot", "payload": {"confidence": 0.9, "elements": 3}}]
    r = replay.reconstruct(stream)
    assert not r.complete
    assert "action" in r.missing and "outcome" in r.missing
    assert "world" not in r.missing            # what IS present is not reported missing


def test_recovery_is_not_required_when_no_failure_occurred():
    stream = [
        {"type": "world_snapshot", "payload": {"confidence": 0.9, "elements": 1}},
        {"type": "step_completed", "payload": {"action": "click", "status": "completed"}},
        {"type": "decision_made", "payload": {"decision": "continue", "factors": {}}},
        {"type": "verification", "payload": {"verified": True, "confidence": 0.8}},
        {"type": "task_completed", "payload": {"status": "completed", "report": {}}},
    ]
    r = replay.reconstruct(stream)
    assert r.complete and "recovery" not in r.missing   # a clean run owes no recovery


def test_reconstruction_is_deterministic(tmp_path):
    events = _run(_clean_plan(), workspace=tmp_path)
    assert replay.reconstruct(events).to_dict() == replay.reconstruct(events).to_dict()


def test_injection_and_egress_events_ride_the_same_canonical_stream(tmp_path):
    """Chapter IX's new security signals are on the ONE stream, not a side
    channel — so they are captured, persisted and replayable like everything
    else. (They are not required dimensions; they are corpus-enriching.)"""
    from perceptai.events import EventType
    from perceptai import streaming
    # Both new events map onto the wire, so a consumer can render them.
    assert EventType.INJECTION_DETECTED in streaming._TRUST_EVENTS
    assert EventType.EGRESS_DECIDED in streaming._TRUST_EVENTS

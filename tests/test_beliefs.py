"""BeliefState: evolution, corroboration, contradiction, reconciliation."""
from perceptai.beliefs import BeliefState
from perceptai.contracts import BoundingBox, UIElement, WindowInfo, WorldState


def test_new_belief_starts_at_asserted_confidence():
    beliefs = BeliefState()
    b = beliefs.assert_belief("notepad is open", "window_open", "notepad", 0.7, "launch ok", "action")
    assert b.confidence == 0.7
    assert b.supports == 1
    assert len(b.history) == 1


def test_agreement_compounds_noisy_or_and_never_reaches_certainty():
    beliefs = BeliefState()
    beliefs.assert_belief("notepad is open", "window_open", "notepad", 0.7, "launch ok", "action")
    b = beliefs.assert_belief("notepad is open", "window_open", "notepad", 0.9, "window visible", "world")
    assert b.confidence == round(0.7 + 0.9 - 0.7 * 0.9, 3)  # 0.97
    for _ in range(10):
        b = beliefs.assert_belief("notepad is open", "window_open", "notepad", 0.99, "again", "world")
    assert b.confidence <= 0.99
    assert b.supports == 12


def test_contradiction_erodes_but_never_zeroes():
    beliefs = BeliefState()
    beliefs.assert_belief("email sent", "action_effect", "email", 0.8, "send clicked", "action")
    b = beliefs.contradict("action_effect", "email", 0.5, "outbox still shows draft", "world")
    assert b.confidence == 0.4
    b = beliefs.contradict("action_effect", "email", 1.0, "hard contradiction", "world")
    assert b.confidence > 0.0  # floored: absence of evidence is not proof
    assert b.contradictions == 2


def test_beliefs_evolve_not_overwrite():
    beliefs = BeliefState()
    beliefs.assert_belief("x", "fact", "x", 0.5, "first", "memory")
    beliefs.assert_belief("x", "fact", "x", 0.5, "second", "evidence")
    beliefs.contradict("fact", "x", 0.3, "third", "world")
    b = beliefs.get("fact", "x")
    assert len(b.history) == 3
    reasons = [u.reason for u in b.history]
    assert reasons == ["first", "second", "third"]


def test_reconcile_corroborates_visible_window_and_contradicts_missing():
    beliefs = BeliefState()
    beliefs.assert_belief("notepad is open", "window_open", "notepad", 0.7, "launch ok", "action")
    beliefs.assert_belief("chrome is open", "window_open", "chrome", 0.7, "launch ok", "action")

    world = WorldState(windows=[WindowInfo(title="notepad - untitled")])
    changed = beliefs.reconcile_with_world(world)

    assert beliefs.get("window_open", "notepad").confidence > 0.7
    assert beliefs.get("window_open", "chrome").confidence < 0.7
    assert len(changed) == 2


def test_contradicted_count_feeds_uncertainty():
    beliefs = BeliefState()
    beliefs.assert_belief("a", "window_open", "a", 0.9, "r", "action")
    assert beliefs.contradicted_count() == 0
    beliefs.contradict("window_open", "a", 0.6, "gone", "world")
    assert beliefs.contradicted_count() == 1


def test_all_sorted_by_confidence():
    beliefs = BeliefState()
    beliefs.assert_belief("low", "fact", "low", 0.2, "r", "")
    beliefs.assert_belief("high", "fact", "high", 0.9, "r", "")
    assert [b.subject for b in beliefs.all()] == ["high", "low"]

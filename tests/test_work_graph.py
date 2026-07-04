"""WorkGraph: dependency derivation, ready-set, cycles, cascade, stall."""
from perceptai.workforce.contracts import WorkOrder, WorkStatus
from perceptai.workforce.graph import WorkGraph


def _order(objective, capability="research", **kwargs):
    return WorkOrder(objective=objective, capability=capability, **kwargs)


def test_data_keys_derive_dependencies():
    producer = _order("find pricing", produces=["pricing"])
    consumer = _order("write summary", requires=["pricing"])
    graph = WorkGraph([producer, consumer])
    assert consumer.depends_on == [producer.id]
    assert [o.id for o in graph.ready()] == [producer.id]


def test_ready_respects_completion_and_priority():
    a = _order("a", produces=["x"], priority=5)
    b = _order("b", requires=["x"], priority=1)
    c = _order("c", priority=2)
    graph = WorkGraph([a, b, c])
    # b is blocked; c outranks a on priority.
    assert [o.objective for o in graph.ready()] == ["c", "a"]
    a.status = WorkStatus.COMPLETED
    assert b in graph.ready()


def test_unknown_explicit_dependency_is_dropped():
    order = _order("solo", depends_on=["nonexistent"])
    graph = WorkGraph([order])
    assert order.depends_on == []
    assert graph.notes  # the drop is recorded, not silent


def test_cycles_are_broken_deterministically():
    a = _order("a", produces=["ka"], requires=["kb"])
    b = _order("b", produces=["kb"], requires=["ka"])
    graph = WorkGraph([a, b])
    # One edge dropped; the graph must be schedulable.
    assert graph.ready(), "cycle must be broken"
    assert any("cyclic" in note for note in graph.notes)


def test_failure_cascade_skips_transitive_dependents():
    a = _order("a", produces=["x"])
    b = _order("b", requires=["x"], produces=["y"])
    c = _order("c", requires=["y"])
    graph = WorkGraph([a, b, c])
    a.status = WorkStatus.FAILED
    a.attempts = a.max_attempts  # attempts exhausted: truly terminal
    skipped = graph.cascade_failure(a.id)
    assert {o.objective for o in skipped} == {"b", "c"}
    assert b.status == WorkStatus.SKIPPED and a.id in b.status_reason
    assert graph.done()


def test_failed_order_with_attempts_left_is_not_done():
    order = _order("a")
    graph = WorkGraph([order])
    order.status = WorkStatus.FAILED
    order.attempts = 1  # below max_attempts: still the scheduler's to reassign
    assert not graph.done()


def test_duplicates_detected_by_capability_outputs_entities():
    keep = _order("research stripe pricing", produces=["pricing"],
                  entities=["Stripe"], priority=1)
    dupe = _order("look up stripe pricing", produces=["pricing"],
                  entities=["stripe"], priority=5)
    other = _order("research adyen pricing", produces=["pricing"],
                   entities=["Adyen"])
    graph = WorkGraph([keep, dupe, other])
    pairs = graph.duplicates()
    assert len(pairs) == 1
    assert pairs[0][0].id == keep.id and pairs[0][1].id == dupe.id


def test_stall_detection_and_resolution():
    a = _order("a", produces=["x"])
    b = _order("b", requires=["x"])
    graph = WorkGraph([a, b])
    a.status = WorkStatus.CANCELLED
    assert graph.stalled()
    released = graph.resolve_stall()
    assert released and b.status == WorkStatus.SKIPPED
    assert graph.done() and not graph.stalled()


def test_progress_and_counts():
    a = _order("a")
    b = _order("b")
    graph = WorkGraph([a, b])
    assert graph.progress() == 0.0
    a.status = WorkStatus.COMPLETED
    assert graph.progress() == 0.5
    assert graph.counts() == {"completed": 1, "pending": 1}

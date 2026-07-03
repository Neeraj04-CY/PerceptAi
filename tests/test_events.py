from perceptai.events import EventBus, EventType


def test_events_are_ordered_and_sequenced():
    bus = EventBus()
    seen = []
    bus.subscribe(seen.append)
    bus.emit(EventType.LOG, "s1", "t1", message="one")
    bus.emit(EventType.LOG, "s1", "t1", message="two")
    assert [e.payload["message"] for e in seen] == ["one", "two"]
    assert [e.seq for e in seen] == [1, 2]


def test_failing_subscriber_does_not_break_others():
    bus = EventBus()
    seen = []

    def bad(_event):
        raise RuntimeError("boom")

    bus.subscribe(bad)
    bus.subscribe(seen.append)
    bus.emit(EventType.ERROR, "s1", "t1", message="still delivered")
    assert len(seen) == 1


def test_unsubscribe():
    bus = EventBus()
    seen = []
    fn = bus.subscribe(seen.append)
    bus.emit(EventType.LOG, "s", "t", message="a")
    bus.unsubscribe(fn)
    bus.emit(EventType.LOG, "s", "t", message="b")
    assert len(seen) == 1


def test_event_to_dict_is_plain():
    bus = EventBus()
    event = bus.emit(EventType.TASK_STARTED, "s1", "t1", instruction="go")
    d = event.to_dict()
    assert d["type"] == "task_started"
    assert d["payload"]["instruction"] == "go"

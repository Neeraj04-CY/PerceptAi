"""Sprint 7 Step 4 — secrets over the runner. The work order carries NAMES
only; the runner fetches values on demand and never persists them. Fully
faked transport."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "api"))

from perceptai.contracts import ActionType, Step  # noqa: E402
from perceptai.simulation import build_simulated_session  # noqa: E402
from runner.config import RunnerConfig  # noqa: E402
from runner.secrets import RemoteSecretResolver  # noqa: E402
from runner.worker import Worker  # noqa: E402
from runner_signing import sign_work_order, verify_work_order  # noqa: E402
import runners as runner_svc  # noqa: E402

KEY = "test-signing-key"


# ------------------------------------------------------------- work order

def test_work_order_carries_sorted_secret_names_and_signs_them():
    session = {"id": "s1", "instruction": "log in", "org_id": "o", "workspace_id": "w"}
    order = runner_svc.build_work_order(session, available_secrets=["ERP_PW", "API_KEY"])
    assert order["available_secrets"] == ["API_KEY", "ERP_PW"]     # sorted, names only

    signed = runner_svc.sign_for_runner("r1", order)
    from runner_signing import derive_runner_key
    key = derive_runner_key(runner_svc.config.RUNNER_SIGNING_KEY, "r1")
    assert verify_work_order(key, signed["work_order"], signed["signature"])
    # tampering the name set breaks the signature
    signed["work_order"]["available_secrets"].append("SNEAKY")
    assert not verify_work_order(key, signed["work_order"], signed["signature"])


# --------------------------------------------------- RemoteSecretResolver

class _FakeSecretClient:
    def __init__(self, values):
        self._values = values
        self.calls: list = []

    def fetch_secret(self, session_id, name):
        self.calls.append((session_id, name))
        return self._values.get(name)


def test_remote_resolver_fetches_caches_and_purges():
    client = _FakeSecretClient({"ERP_PW": "hunter2"})
    r = RemoteSecretResolver(client, "s1", available=["ERP_PW"])
    assert r.resolve("ERP_PW") == "hunter2"
    assert r.resolve("ERP_PW") == "hunter2"
    assert len(client.calls) == 1                 # fetched once, cached
    assert r.resolve("NOPE") is None              # not available -> no fetch
    buf = r._cache["ERP_PW"]
    r.purge()
    assert r._cache == {} and set(buf) == {0}     # zeroized + dropped


def test_remote_resolver_names_come_from_the_order():
    r = RemoteSecretResolver(_FakeSecretClient({}), "s1", available=["A", "B"])
    assert r.names() == ["A", "B"]


# ------------------------------------------------- worker wires the resolver

class _Plane:
    def __init__(self, order):
        self._order = order
        self._served = False
        self.events: list = []
        self.result = None

    def heartbeat(self, sid): pass
    def claim(self):
        if self._served:
            return None
        self._served = True
        return self._order
    def post_events(self, sid, events): self.events.extend(events)
    def post_result(self, sid, report): self.result = (sid, report)
    def get_control(self, sid): return {"state": "running", "approval_decision": None}
    def post_approval_request(self, sid, req): pass
    def fetch_secret(self, sid, name): return None


def test_worker_injects_secret_resolver_built_from_order(tmp_path):
    order = {"session_id": "s1", "instruction": "open notepad",
             "available_secrets": ["ERP_PW"], "mode": "task"}
    signed = {"work_order": order, "signature": sign_work_order(KEY, order)}

    captured: dict = {}

    def session_factory(instruction):
        session, _f, _e = build_simulated_session(
            plans=[[Step(action=ActionType.OPEN_APP, description="open notepad",
                         params={"app": "notepad", "wait": 0.0})]],
            workspace=tmp_path)
        captured["session"] = session
        return session

    seen: dict = {}

    def secrets_factory(sid, work_order):
        seen["sid"] = sid
        seen["names"] = work_order.get("available_secrets")
        return RemoteSecretResolver(_Plane(order), sid, work_order.get("available_secrets", []))

    worker = Worker(_Plane(signed), RunnerConfig(plane_url="x", token="rk", signing_key=KEY),
                    session_factory=session_factory, secrets_factory=secrets_factory)
    worker.execute_work_order(signed)

    assert seen["sid"] == "s1" and seen["names"] == ["ERP_PW"]
    assert captured["session"].secrets.names() == ["ERP_PW"]   # injected onto the session

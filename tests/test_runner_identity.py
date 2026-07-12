"""Chapter IX Step 4 — Runner identity: mutual asymmetric (Ed25519).

Eliminates shared trust. What these tests actually assert is BLAST RADIUS:
  * the plane can no longer derive any runner's identity;
  * a compromised runner cannot forge a work order;
  * a captured request cannot be replayed to another endpoint, mutated, or
    replayed outside the freshness window.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "api"))
sys.path.append(str(Path(__file__).parent))

import pytest  # noqa: E402

from perceptai import signing as sg  # noqa: E402
from runner.identity import RunnerIdentity  # noqa: E402


NOW = 1_800_000_000


# ------------------------------------------------------------------ keys

def test_generated_keypairs_are_unique_and_verifiable():
    priv_a, pub_a = sg.generate_keypair()
    priv_b, pub_b = sg.generate_keypair()
    assert priv_a != priv_b and pub_a != pub_b
    assert sg.public_key_for(priv_a) == pub_a           # public half is derivable
    sig = sg.sign_bytes(priv_a, b"hello")
    assert sg.verify_bytes(pub_a, b"hello", sig)
    assert not sg.verify_bytes(pub_b, b"hello", sig)    # not by anyone else's key


def test_a_public_key_cannot_sign():
    """The whole point: the plane stores only public keys. Holding the plane's
    database gives you the ability to VERIFY, never to impersonate."""
    priv, pub = sg.generate_keypair()
    assert not sg.verify_bytes(pub, b"x", sg.sign_bytes(priv, b"y"))


def test_plane_identity_is_derived_deterministically_from_its_existing_secret():
    a = sg.private_key_from_seed("server-secret")
    assert a == sg.private_key_from_seed("server-secret")       # stable across restarts
    assert a != sg.private_key_from_seed("other-secret")


# ------------------------------------------- work orders (plane -> runner)

def test_runner_verifies_a_work_order_without_holding_a_forging_secret():
    plane_priv = sg.private_key_from_seed("server-secret")
    plane_pub = sg.public_key_for(plane_priv)
    order = {"session_id": "s1", "instruction": "open notepad"}
    sig = sg.sign_work_order_ed25519(plane_priv, order)

    assert sg.verify_work_order_ed25519(plane_pub, order, sig)
    # A compromised runner holds only plane_pub -> it cannot mint a new order.
    forged = sg.sign_bytes(sg.generate_keypair()[0], b"anything")
    assert not sg.verify_work_order_ed25519(plane_pub, order, forged)


def test_tampering_with_a_signed_order_invalidates_it():
    plane_priv = sg.private_key_from_seed("s")
    plane_pub = sg.public_key_for(plane_priv)
    order = {"session_id": "s1", "instruction": "open notepad"}
    sig = sg.sign_work_order_ed25519(plane_priv, order)
    assert not sg.verify_work_order_ed25519(
        plane_pub, {**order, "instruction": "delete everything"}, sig)


def test_egress_policy_in_the_order_is_covered_by_the_signature():
    """A runner must not be tricked into a laxer egress policy than its
    workspace declared."""
    plane_priv = sg.private_key_from_seed("s")
    plane_pub = sg.public_key_for(plane_priv)
    order = {"session_id": "s", "egress_policy": {"mode": "local_only"}}
    sig = sg.sign_work_order_ed25519(plane_priv, order)
    downgraded = {**order, "egress_policy": {"mode": "allow"}}
    assert not sg.verify_work_order_ed25519(plane_pub, downgraded, sig)


# ------------------------------------------------ requests (runner -> plane)

def _sign(priv, method="POST", path="/api/v1/runners/claim", body=b"{}",
          ts=NOW, nonce="n1"):
    return sg.sign_request(priv, method, path, body, ts, nonce)


def test_a_signed_request_verifies():
    priv, pub = sg.generate_keypair()
    ok, reason = sg.verify_request(pub, "POST", "/api/v1/runners/claim", b"{}",
                                   NOW, "n1", _sign(priv), now=NOW)
    assert ok and reason == ""


def test_a_captured_signature_cannot_be_moved_to_another_endpoint():
    priv, pub = sg.generate_keypair()
    sig = _sign(priv, path="/api/v1/runners/claim")
    ok, reason = sg.verify_request(pub, "POST", "/api/v1/runners/executions/x/secrets",
                                   b"{}", NOW, "n1", sig, now=NOW)
    assert not ok and "signature does not match" in reason


def test_a_captured_signature_cannot_be_reused_with_a_different_body():
    priv, pub = sg.generate_keypair()
    sig = _sign(priv, body=b'{"name":"SAFE"}')
    ok, _ = sg.verify_request(pub, "POST", "/api/v1/runners/claim",
                              b'{"name":"ERP_PW"}', NOW, "n1", sig, now=NOW)
    assert not ok


def test_a_captured_request_cannot_be_replayed_later():
    priv, pub = sg.generate_keypair()
    sig = _sign(priv, ts=NOW)
    ok, reason = sg.verify_request(pub, "POST", "/api/v1/runners/claim", b"{}",
                                   NOW, "n1", sig, now=NOW + sg.MAX_CLOCK_SKEW_S + 1)
    assert not ok and "freshness window" in reason


def test_freshness_is_checked_before_the_signature():
    """An expired replay is rejected even when the signature is genuine."""
    priv, pub = sg.generate_keypair()
    ok, reason = sg.verify_request(pub, "POST", "/p", b"", NOW, "n", _sign(priv, path="/p", body=b""),
                                   now=NOW + 10_000)
    assert not ok and "freshness" in reason


def test_a_stolen_runner_key_impersonates_exactly_one_runner():
    stolen_priv, stolen_pub = sg.generate_keypair()
    _other_priv, other_pub = sg.generate_keypair()
    sig = _sign(stolen_priv)
    assert sg.verify_request(stolen_pub, "POST", "/api/v1/runners/claim", b"{}",
                             NOW, "n1", sig, now=NOW)[0] is True
    assert sg.verify_request(other_pub, "POST", "/api/v1/runners/claim", b"{}",
                             NOW, "n1", sig, now=NOW)[0] is False


def test_malformed_input_is_rejected_not_crashed():
    _priv, pub = sg.generate_keypair()
    assert sg.verify_request(pub, "POST", "/p", b"", "not-a-number", "n", "x")[0] is False
    assert sg.verify_bytes("not-a-key", b"x", "y") is False
    assert sg.verify_bytes(pub, b"x", "!!!not-base64!!!") is False


# ------------------------------------------------------ identity on the host

def test_identity_persists_and_reloads(tmp_path):
    path = tmp_path / "id.json"
    first = RunnerIdentity.load_or_create(path)
    again = RunnerIdentity.load_or_create(path)
    assert first.private_key == again.private_key
    assert again.public_key == sg.public_key_for(first.private_key)


def test_a_corrupt_identity_file_regenerates_rather_than_bricking_the_host(tmp_path):
    path = tmp_path / "id.json"
    path.write_text("{ not json")
    identity = RunnerIdentity.load_or_create(path)
    assert identity.private_key and identity.public_key


def test_identity_file_never_contains_the_plane_secret(tmp_path):
    path = tmp_path / "id.json"
    identity = RunnerIdentity.load_or_create(path)
    identity.plane_public_key = sg.public_key_for(sg.private_key_from_seed("server-secret"))
    identity.save(path)
    body = path.read_text()
    assert "server-secret" not in body
    assert sg.private_key_from_seed("server-secret") not in body   # never the private half


def test_identity_signs_request_headers(tmp_path):
    identity = RunnerIdentity.load_or_create(tmp_path / "id.json")
    headers = identity.sign("POST", "/api/v1/runners/claim", b"{}")
    ok, _ = sg.verify_request(identity.public_key, "POST", "/api/v1/runners/claim", b"{}",
                              int(headers["X-Runner-Timestamp"]),
                              headers["X-Runner-Nonce"], headers["X-Runner-Signature"])
    assert ok


def test_identity_verifies_work_orders_only_from_the_real_plane(tmp_path):
    identity = RunnerIdentity.load_or_create(tmp_path / "id.json")
    plane_priv = sg.private_key_from_seed("server-secret")
    identity.plane_public_key = sg.public_key_for(plane_priv)
    order = {"session_id": "s"}
    assert identity.verify_work_order(order, sg.sign_work_order_ed25519(plane_priv, order))

    impostor_priv, _ = sg.generate_keypair()
    assert not identity.verify_work_order(order, sg.sign_work_order_ed25519(impostor_priv, order))


def test_identity_without_a_plane_key_trusts_nothing(tmp_path):
    identity = RunnerIdentity.load_or_create(tmp_path / "id.json")
    assert identity.verify_work_order({"session_id": "s"}, "anything") is False


# ------------------------------------------------------- plane-side policy

def test_enrolled_runner_must_sign_and_legacy_runner_need_not():
    import runners as svc
    from fastapi import HTTPException

    priv, pub = sg.generate_keypair()
    enrolled = {"id": "r1", "public_key": pub, "key_algorithm": sg.ED25519}
    legacy = {"id": "r2", "key_algorithm": sg.HMAC_SHA256}

    # legacy: bearer token alone still works (no outage while the fleet upgrades)
    svc.verify_runner_request(legacy, method="POST", path="/p", body=b"",
                              timestamp="", nonce="", signature="")

    # enrolled: a token alone is no longer enough to be this runner
    with pytest.raises(HTTPException) as e:
        svc.verify_runner_request(enrolled, method="POST", path="/p", body=b"",
                                  timestamp="", nonce="", signature="")
    assert e.value.status_code == 401 and "must sign" in e.value.detail

    ts = int(time.time())
    sig = sg.sign_request(priv, "POST", "/p", b"", ts, "n")
    svc.verify_runner_request(enrolled, method="POST", path="/p", body=b"",
                              timestamp=str(ts), nonce="n", signature=sig)

    with pytest.raises(HTTPException):
        svc.verify_runner_request(enrolled, method="POST", path="/p", body=b"",
                                  timestamp=str(ts), nonce="n", signature="bad")


def test_enrollment_is_trust_on_first_use_and_refuses_silent_rotation():
    import runners as svc
    from fastapi import HTTPException
    from supafake import FakeSupabase

    db = FakeSupabase()
    _priv, pub = sg.generate_keypair()
    runner = {"id": "r1", "name": "vm", "org_id": "o1"}
    db.rows["runners"].append(dict(runner))

    result = svc.enroll_runner(db, runner, pub)
    assert result["algorithm"] == sg.ED25519
    assert result["plane_public_key"] == svc.plane_public_key()
    assert db.rows["runners"][0]["public_key"] == pub

    # A leaked bootstrap token must not silently replace a live identity.
    with pytest.raises(HTTPException) as e:
        svc.enroll_runner(db, db.rows["runners"][0], sg.generate_keypair()[1])
    assert e.value.status_code == 409 and "re-register" in e.value.detail


def test_enrollment_rejects_a_junk_key():
    import runners as svc
    from fastapi import HTTPException
    from supafake import FakeSupabase
    with pytest.raises(HTTPException):
        svc.enroll_runner(FakeSupabase(), {"id": "r"}, "short")


def test_work_order_is_signed_with_the_algorithm_the_runner_enrolled():
    import runners as svc
    order = {"session_id": "s", "instruction": "x"}

    signed = svc.sign_for_runner("r1", order, key_algorithm=sg.ED25519)
    assert signed["algorithm"] == sg.ED25519
    assert sg.verify_work_order_ed25519(svc.plane_public_key(), order, signed["signature"])

    legacy = svc.sign_for_runner("r1", order, key_algorithm=sg.HMAC_SHA256)
    assert legacy["algorithm"] == sg.HMAC_SHA256
    assert sg.verify_work_order(
        sg.derive_runner_key(svc.config.RUNNER_SIGNING_KEY, "r1"), order, legacy["signature"])


def test_public_runner_never_leaks_key_material():
    import runners as svc
    _priv, pub = sg.generate_keypair()
    pub_row = svc.public_runner({"id": "r", "name": "n", "token_hash": "h",
                                 "public_key": pub, "key_algorithm": sg.ED25519})
    assert "public_key" not in pub_row and "token_hash" not in pub_row

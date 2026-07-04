"""MissionPolicy, WorkforceLimits, WorkspaceContext, AuditLog."""
from perceptai.events import EventBus, EventType
from perceptai.workforce.contracts import WorkOrder
from perceptai.workforce.policy import (
    AuditLog,
    MissionPolicy,
    WorkforceLimits,
    WorkspaceContext,
)


def _order(capability="research"):
    return WorkOrder(objective="do work", capability=capability)


def test_plans_are_data_not_branches():
    starter = WorkforceLimits.for_plan("starter")
    enterprise = WorkforceLimits.for_plan("enterprise")
    assert starter.max_parallel < enterprise.max_parallel
    assert starter.max_work_orders < enterprise.max_work_orders
    # Unknown plan degrades to the most restrictive tier.
    assert WorkforceLimits.for_plan("nonsense").max_parallel == starter.max_parallel


def test_capability_allowlist_denies_with_policy_named():
    policy = MissionPolicy(
        limits=WorkforceLimits(allowed_capabilities=["research"]))
    assert policy.check_order(_order("research")).allowed
    verdict = policy.check_order(_order("desktop"))
    assert not verdict.allowed
    assert verdict.constraint == "capability_allowlist"
    assert "desktop" in verdict.reason


def test_approval_hook_gates_sensitive_capabilities():
    limits = WorkforceLimits(approval_capabilities=["desktop"])
    denied = MissionPolicy(limits=limits)  # no approver registered
    verdict = denied.check_order(_order("desktop"))
    assert not verdict.allowed and verdict.constraint == "approval_required"

    approved = MissionPolicy(limits=limits, approver=lambda order: True)
    assert approved.check_order(_order("desktop")).allowed
    # Capabilities outside the approval list never invoke the approver.
    assert denied.check_order(_order("research")).allowed


def test_broken_approver_denies_never_crashes():
    def approver(order):
        raise RuntimeError("approval service down")

    policy = MissionPolicy(
        limits=WorkforceLimits(approval_capabilities=["desktop"]),
        approver=approver)
    verdict = policy.check_order(_order("desktop"))
    assert not verdict.allowed


def test_audit_log_is_an_event_stream_consumer():
    workspace = WorkspaceContext(organization="acme", project="ops", user="neeraj")
    audit = AuditLog(workspace)
    bus = EventBus()
    audit.attach(bus)
    bus.emit(EventType.MISSION_STARTED, session_id="s", task_id="m",
             instruction="research")
    entries = audit.export()
    assert len(entries) == 1
    assert entries[0]["type"] == "mission_started"
    assert entries[0]["workspace"]["organization"] == "acme"

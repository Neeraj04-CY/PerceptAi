"""Enterprise workflow packs — the curated catalog that turns a blank platform
into "pick the automation you already do by hand, fill two fields, and run it."

Templates are DATA: a parametrized instruction plus a variable schema, exactly
the shape a workflow takes when saved. `{{name}}` slots are substituted by
render_instruction. Nothing here is a new execution path — a template compiles
to the ONE runtime like any workflow.

Each pack targets a department a Fortune 500 buyer recognizes, and each template
carries the framing that buyer needs: the value it removes, the apps it spans,
and the time it gives back. The flagship templates are the exact workflows
proven end-to-end in the Chapter X enterprise bench.

Note: a `{{secret:NAME}}` reference is not a variable — the slot regex ignores
the colon, so it passes through render untouched and is resolved out-of-band at
the action layer (Sprint 7). The value never enters an instruction string.
"""
from __future__ import annotations

import re
from typing import Any

_SLOT = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


# Packs are the catalog's top-level grouping — a department, not a feature.
PACKS: list[dict[str, str]] = [
    {"id": "finance", "name": "Finance & Accounting",
     "tagline": "Kill manual data entry in the ERP and close the books faster."},
    {"id": "sales", "name": "Sales & CRM",
     "tagline": "Keep the CRM current without a human retyping it."},
    {"id": "procurement", "name": "Procurement",
     "tagline": "Route approvals autonomously — with a human gate on the money."},
    {"id": "people", "name": "HR & IT Operations",
     "tagline": "Onboard, provision and audit across the apps IT actually uses."},
    {"id": "support", "name": "Customer Support",
     "tagline": "Triage across every tool an agent has open, in seconds."},
    {"id": "starter", "name": "Get started safely",
     "tagline": "A harmless first run that proves the whole loop in 15 seconds."},
]


def _var(name: str, label: str, default: str = "", required: bool = True,
         description: str = "") -> dict[str, Any]:
    return {"name": name, "label": label, "type": "text", "required": required,
            "default": default, "description": description}


TEMPLATES: list[dict[str, Any]] = [
    # ---------------------------------------------------------- FINANCE
    {
        "id": "erp-invoice-posting",
        "pack": "finance",
        "name": "Post invoice to the ERP",
        "category": "Accounts Payable",
        "mode": "task",
        "flagship": True,
        "value": "AP clerks key invoices by hand at $4-6 each - this eliminates the keystrokes and verifies the posting.",
        "apps": ["SAP", "Oracle", "NetSuite", "Any ERP"],
        "time_saved": "~5 min per invoice",
        "description": "Open the ERP, enter an invoice's header and lines, post "
                       "it, and verify the document number before reporting done.",
        "instruction": "In {{erp}}, create and post a vendor invoice for vendor "
                       "{{vendor}}, invoice number {{invoice_number}}, amount "
                       "{{amount}}. After posting, read the confirmation and report "
                       "the ERP document number. Do not post twice.",
        "variables": [
            _var("erp", "ERP application", "SAP", description="e.g. SAP, Oracle, NetSuite"),
            _var("vendor", "Vendor", description="Vendor name as it appears in the ERP"),
            _var("invoice_number", "Invoice number", description="The vendor's invoice number"),
            _var("amount", "Amount", description="Invoice total, e.g. 12,400.00"),
        ],
        "outputs": ["ERP document number", "Posting confirmation", "Verification result"],
    },
    {
        "id": "finance-reconciliation",
        "pack": "finance",
        "name": "Reconcile a payment batch",
        "category": "Reconciliation",
        "mode": "task",
        "flagship": True,
        "value": "Month-end reconciliation is hours of cross-checking two systems - run it unattended overnight instead.",
        "apps": ["ERP", "Banking portal", "Excel"],
        "time_saved": "~2-3 hrs per close",
        "description": "Match a payment batch between two systems, confirm the "
                       "totals agree, and flag every exception with evidence.",
        "instruction": "Reconcile payment batch {{batch}} between {{system_a}} and "
                       "{{system_b}}. Confirm the record counts and totals match. "
                       "List every unmatched or mismatched item with the values from "
                       "each system. Report a clean/exception verdict with evidence.",
        "variables": [
            _var("batch", "Batch reference", description="e.g. B-88 or a date range"),
            _var("system_a", "System A", "the ERP", description="First source of truth"),
            _var("system_b", "System B", "the banking portal", description="Second source of truth"),
        ],
        "outputs": ["Match verdict", "Exception list with evidence", "Totals compared"],
    },
    {
        "id": "statement-data-entry",
        "pack": "finance",
        "name": "Enter a record with verification",
        "category": "Data Entry",
        "mode": "task",
        "value": "Any 'type this into that system' task - done once, checked, and reported, not fire-and-forget.",
        "apps": ["Any application"],
        "time_saved": "~3 min per record",
        "description": "Enter a record into any application and verify it was "
                       "actually saved before reporting success.",
        "instruction": "Open {{app}} and enter the following record: {{record}}. "
                       "Verify the entry was saved and report what the application "
                       "shows afterwards.",
        "variables": [
            _var("app", "Application", description="Target application"),
            _var("record", "Record", description="The data to enter"),
        ],
        "outputs": ["Entry confirmation", "Verification result"],
    },

    # ------------------------------------------------------------- SALES
    {
        "id": "crm-opportunity-update",
        "pack": "sales",
        "name": "Update a CRM opportunity",
        "category": "CRM",
        "mode": "task",
        "flagship": True,
        "value": "Reps lose hours to CRM hygiene - the agent logs in with a vault credential and updates the record, and the password never touches the model.",
        "apps": ["Salesforce", "HubSpot", "Dynamics"],
        "time_saved": "~4 min per update",
        "description": "Sign into the CRM with a stored credential, open an "
                       "opportunity, update its stage and amount, and save.",
        "instruction": "Log into {{crm}} using the stored password {{secret:CRM_PASSWORD}}, "
                       "open the opportunity for {{account}}, set the amount to "
                       "{{amount}} and the stage to {{stage}}, then save and confirm "
                       "the change was written.",
        "variables": [
            _var("crm", "CRM", "Salesforce", description="e.g. Salesforce, HubSpot"),
            _var("account", "Account / opportunity", description="Which opportunity to update"),
            _var("amount", "Amount", description="New opportunity amount"),
            _var("stage", "Stage", "Negotiation", description="New stage"),
        ],
        "outputs": ["Save confirmation", "Field values written", "Verification result"],
    },
    {
        "id": "lead-enrichment",
        "pack": "sales",
        "name": "Capture lead details into the CRM",
        "category": "CRM",
        "mode": "task",
        "value": "Turn a name and a source into a clean CRM record - read the details, enter them, verify.",
        "apps": ["CRM", "Web", "Email"],
        "time_saved": "~5 min per lead",
        "description": "Read a lead's details from a source and enter them into "
                       "the CRM as a new record.",
        "instruction": "Read the lead details for {{lead}} from {{source}}, then "
                       "create a new lead in {{crm}} with those details. Verify the "
                       "record was created and report the fields captured.",
        "variables": [
            _var("lead", "Lead", description="Person or company"),
            _var("source", "Source", "the current page", description="Where the details are"),
            _var("crm", "CRM", "Salesforce"),
        ],
        "outputs": ["New record confirmation", "Captured fields", "Confidence per field"],
    },

    # -------------------------------------------------------- PROCUREMENT
    {
        "id": "po-approval",
        "pack": "procurement",
        "name": "Route a purchase-order approval",
        "category": "Approvals",
        "mode": "task",
        "flagship": True,
        "value": "Autonomy where it's safe, a human gate where it's not - an irreversible financial approval pauses for a person, on policy.",
        "apps": ["Coupa", "Ariba", "SAP"],
        "time_saved": "~8 min per PO",
        "description": "Open a purchase order, check it against policy, and route "
                       "the approval - pausing for human sign-off on high-value POs.",
        "instruction": "Open purchase order {{po}} in {{system}}. Confirm the vendor "
                       "and total. Approve it. (Approval of a financial action is "
                       "risk-gated: if the workspace requires it, wait for a human "
                       "before the approval is submitted.)",
        "variables": [
            _var("po", "Purchase order", description="PO number"),
            _var("system", "System", "Coupa", description="e.g. Coupa, Ariba, SAP"),
        ],
        "outputs": ["Approval outcome", "Risk flags raised", "Approver decision"],
    },
    {
        "id": "vendor-lookup",
        "pack": "procurement",
        "name": "Look up a vendor's status",
        "category": "Procurement",
        "mode": "task",
        "value": "Read-only vendor checks across the procurement system, reported with evidence - nothing is changed.",
        "apps": ["Procurement system"],
        "time_saved": "~4 min per lookup",
        "description": "Find a vendor in the procurement system and report their "
                       "current status and open orders - observation only.",
        "instruction": "In {{system}}, find vendor {{vendor}} and report their "
                       "current status, payment terms and any open purchase orders. "
                       "Do not change anything.",
        "variables": [
            _var("system", "System", "Coupa"),
            _var("vendor", "Vendor", description="Vendor to inspect"),
        ],
        "outputs": ["Vendor status", "Open orders", "Where each value was found"],
    },

    # ---------------------------------------------------------- HR / IT
    {
        "id": "employee-onboarding",
        "pack": "people",
        "name": "Onboard a new hire",
        "category": "HR Onboarding",
        "mode": "task",
        "flagship": True,
        "value": "Onboarding spans many screens and breaks brittle RPA scripts - the agent self-heals when the UI shifts and still completes the flow.",
        "apps": ["Workday", "BambooHR", "Active Directory"],
        "time_saved": "~20 min per hire",
        "description": "Open the HR system, run the new-hire wizard, enter the "
                       "employee's details, submit, and verify the record exists.",
        "instruction": "In {{hr_system}}, start the new-hire onboarding for "
                       "{{employee}} (role: {{role}}, start date: {{start_date}}). "
                       "Complete the wizard, submit it, and verify the employee "
                       "record was created.",
        "variables": [
            _var("hr_system", "HR system", "Workday", description="e.g. Workday, BambooHR"),
            _var("employee", "Employee name", description="The new hire"),
            _var("role", "Role", description="Job title"),
            _var("start_date", "Start date", description="e.g. 2026-08-01"),
        ],
        "outputs": ["Onboarding confirmation", "Record created", "Steps completed"],
    },
    {
        "id": "access-audit",
        "pack": "people",
        "name": "Audit an application setting",
        "category": "IT Operations",
        "mode": "task",
        "value": "Read a setting or permission and report it - a safe, auditable read across any app.",
        "apps": ["Any application", "Windows Settings"],
        "time_saved": "~3 min per check",
        "description": "Read a setting or permission in an application and report "
                       "its current value without changing anything.",
        "instruction": "Open {{app}}, find {{setting}} and report its current value. "
                       "Do not change anything.",
        "variables": [
            _var("app", "Application", "Windows Settings"),
            _var("setting", "Setting", "display resolution", description="What to inspect"),
        ],
        "outputs": ["Current value", "Where it was found"],
    },

    # --------------------------------------------------------- SUPPORT
    {
        "id": "ticket-triage",
        "pack": "support",
        "name": "Triage a support ticket across apps",
        "category": "Customer Support",
        "mode": "task",
        "flagship": True,
        "value": "Support reps swivel-chair between the ticket, the CRM and billing - the agent reads all three and hands back one summary.",
        "apps": ["Zendesk", "Salesforce", "Billing"],
        "time_saved": "~6 min per ticket",
        "description": "Read a support ticket, look up the customer's account in "
                       "the CRM, and summarize the situation with a recommended next "
                       "step - read-only.",
        "instruction": "Read support ticket {{ticket}} in {{helpdesk}}. Look up the "
                       "customer's account in {{crm}}. Summarize the issue, the "
                       "customer's status, and a recommended next step, citing where "
                       "each fact came from. Do not modify anything.",
        "variables": [
            _var("ticket", "Ticket", description="Ticket id or subject"),
            _var("helpdesk", "Helpdesk", "Zendesk"),
            _var("crm", "CRM", "Salesforce"),
        ],
        "outputs": ["Issue summary", "Account status", "Recommended next step", "Sources"],
    },

    # ---------------------------------------------------------- STARTER
    {
        "id": "starter-smoke-test",
        "pack": "starter",
        "name": "Safe starter: open Notepad and verify",
        "category": "First run",
        "mode": "task",
        "flagship": True,
        "value": "Prove the whole perceive -> plan -> act -> verify loop in one harmless, ~15-second run.",
        "apps": ["Notepad"],
        "time_saved": "-",
        "description": "Opens Notepad, types one line, and verifies it appeared - "
                       "harmless, and the fastest way to see the cockpit work.",
        "instruction": "Open Notepad and type '{{message}}'. Verify the text "
                       "appears on screen, then report what you see.",
        "variables": [
            _var("message", "Message", "Hello from PerceptAI", required=False,
                 description="The line to type"),
        ],
        "outputs": ["Typed confirmation", "Verification result"],
    },
]


def get_template(template_id: str) -> dict[str, Any] | None:
    return next((t for t in TEMPLATES if t["id"] == template_id), None)


def render_instruction(instruction: str, variables: list[dict[str, Any]],
                       values: dict[str, str]) -> str:
    """Substitute {{slots}} using provided values, falling back to variable
    defaults. Raises ValueError naming every missing required variable.

    A {{secret:NAME}} reference is left untouched: the slot regex only matches
    bare identifiers, so the colon excludes it, and the runtime resolves it
    out-of-band at the action layer."""
    declared = {v["name"]: v for v in variables}
    missing: list[str] = []

    def fill(match: re.Match) -> str:
        name = match.group(1)
        value = values.get(name, "").strip() if values.get(name) else ""
        if not value:
            value = str(declared.get(name, {}).get("default", "") or "").strip()
        if not value:
            if declared.get(name, {}).get("required", False) or name not in declared:
                missing.append(name)
            return ""
        return value

    rendered = _SLOT.sub(fill, instruction)
    if missing:
        raise ValueError(f"missing required variable(s): {', '.join(sorted(set(missing)))}")
    return re.sub(r"\s{2,}", " ", rendered).strip()

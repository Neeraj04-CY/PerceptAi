"""Verify the live database matches the codebase's expected schema.

Run from inside api/ (or anywhere — it fixes the path itself):

    ..\\.venv311\\Scripts\\python migrations\\verify_schema.py

Read-only: probes each expected table and sessions column through the
service client and prints a PASS/FAIL report plus which migration file
provides anything missing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os
os.chdir(Path(__file__).resolve().parent.parent)

from database import get_service_db  # noqa: E402

EXPECTED = {
    "002_platform.sql": {
        "tables": ["organizations", "organization_members", "workspaces",
                   "secrets", "workflows", "workflow_versions", "missions",
                   "approvals", "events", "audit_log"],
        "session_columns": ["org_id", "workspace_id"],
    },
    "003_runners.sql": {
        "tables": ["runners", "execution_control"],
        "session_columns": ["runner_id", "claim_expires_at", "attempts"],
    },
    "004_operations.sql": {
        "tables": ["attention_items"],
        "session_columns": ["workflow_id", "origin", "retry_of",
                            "retry_count", "target_runner_id"],
    },
    "005_production_trust.sql": {
        "tables": ["learning_consent"],
        "session_columns": [],
    },
    "006_business_memory.sql": {
        "tables": ["business_memory"],
        "session_columns": [],
    },
}


def main() -> int:
    db = get_service_db()

    def has_table(name: str) -> bool:
        try:
            db.table(name).select("*").limit(1).execute()
            return True
        except Exception:
            return False

    def has_session_col(name: str) -> bool:
        try:
            db.table("sessions").select(name).limit(1).execute()
            return True
        except Exception:
            return False

    failures = 0
    for migration, spec in EXPECTED.items():
        missing = [t for t in spec["tables"] if not has_table(t)]
        missing += [f"sessions.{c}" for c in spec["session_columns"]
                    if not has_session_col(c)]
        status = "PASS" if not missing else "MISSING"
        print(f"[{status:<7}] {migration}"
              + (f"  -> apply this file; missing: {', '.join(missing)}" if missing else ""))
        failures += bool(missing)

    print()
    if failures:
        print(f"{failures} migration(s) not fully applied. Paste the named files "
              f"into the Supabase SQL editor IN ORDER, then re-run this check.")
        return 1
    print("Database matches the codebase. All platform features are live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

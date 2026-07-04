"""Organizational experience: every mission permanently improves routing.

SQLite (the same database file as MemoryStore by default): mission
history plus per-specialist per-capability performance. Routing consumes
the measured success rates once enough samples exist, so the workforce
provably reroutes toward what works — knowledge evolution as data, not
as a promise. All writes are best-effort; experience never affects a
mission's correctness, only future efficiency.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

from .contracts import MissionResult


class ExperienceStore:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        if not self._initialized:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS missions (
                    id TEXT PRIMARY KEY,
                    instruction TEXT,
                    status TEXT,
                    duration_s REAL,
                    orders_total INTEGER,
                    orders_completed INTEGER,
                    cost REAL,
                    created_at REAL
                );
                CREATE TABLE IF NOT EXISTS specialist_stats (
                    specialist TEXT,
                    capability TEXT,
                    completed INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0,
                    total_duration_s REAL DEFAULT 0,
                    updated_at REAL,
                    PRIMARY KEY (specialist, capability)
                );
                """
            )
            conn.commit()
            self._initialized = True
        return conn

    # ------------------------------------------------------------- writing

    def record_mission(self, result: MissionResult) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO missions
                       (id, instruction, status, duration_s, orders_total,
                        orders_completed, cost, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        result.mission_id, result.instruction, result.status.value,
                        result.duration_s, result.metrics.orders_total,
                        result.metrics.orders_completed, result.metrics.cost_total,
                        time.time(),
                    ),
                )
        except Exception:
            pass

    def record_work(self, specialist: str, capability: str,
                    ok: bool, duration_s: float) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO specialist_stats
                       (specialist, capability, completed, failed, total_duration_s, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(specialist, capability) DO UPDATE SET
                         completed = completed + excluded.completed,
                         failed = failed + excluded.failed,
                         total_duration_s = total_duration_s + excluded.total_duration_s,
                         updated_at = excluded.updated_at""",
                    (specialist, capability, 1 if ok else 0, 0 if ok else 1,
                     duration_s, time.time()),
                )
        except Exception:
            pass

    # ------------------------------------------------------------- reading

    def success_rate(self, specialist: str, capability: str,
                     min_samples: int = 3) -> Optional[float]:
        """Measured rate once enough history exists; None tells routing to
        use the profile's baseline instead."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """SELECT completed, failed FROM specialist_stats
                       WHERE specialist=? AND capability=?""",
                    (specialist, capability),
                ).fetchone()
        except Exception:
            return None
        if not row:
            return None
        completed, failed = int(row[0]), int(row[1])
        attempts = completed + failed
        if attempts < min_samples:
            return None
        return completed / attempts

    def mission_history(self, limit: int = 20) -> list[dict]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT id, instruction, status, duration_s, orders_total,
                              orders_completed, cost, created_at
                       FROM missions ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        except Exception:
            return []
        return [
            {"id": r[0], "instruction": r[1], "status": r[2], "duration_s": r[3],
             "orders_total": r[4], "orders_completed": r[5], "cost": r[6],
             "created_at": r[7]}
            for r in rows
        ]

"""Persistent agent memory (SQLite).

Session-scoped access to a configurable database. Interface maps store
where elements were seen per app; task patterns store successful step
sequences per instruction. The read path (recall_*) is exposed for the
runtime and future planning integration.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional


class MemoryStore:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        if not self._initialized:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._db_path)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS interface_maps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name TEXT,
                    element_text TEXT,
                    element_type TEXT,
                    x INTEGER,
                    y INTEGER,
                    confidence REAL,
                    seen_count INTEGER DEFAULT 1,
                    last_seen REAL,
                    created_at REAL
                );
                CREATE TABLE IF NOT EXISTS task_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    instruction_hash TEXT,
                    instruction TEXT,
                    steps_json TEXT,
                    success INTEGER,
                    execution_time REAL,
                    created_at REAL
                );
                CREATE TABLE IF NOT EXISTS knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity TEXT,
                    attribute TEXT,
                    value TEXT,
                    source TEXT,
                    confidence REAL,
                    task_id TEXT,
                    created_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_entity ON knowledge(entity);
                """
            )
            conn.commit()
            self._initialized = True
            return conn
        return sqlite3.connect(self._db_path)

    def remember_interface(self, app_name: str, elements: list[dict]) -> None:
        if not app_name or not elements:
            return
        with self._connect() as conn:
            c = conn.cursor()
            for element in elements:
                x = int(element.get("x", -1))
                y = int(element.get("y", -1))
                text = str(element.get("text", ""))
                if x <= 0 or y <= 0 or not text:
                    continue
                c.execute(
                    "SELECT id, seen_count FROM interface_maps WHERE app_name=? AND element_text=?",
                    (app_name, text),
                )
                existing = c.fetchone()
                if existing:
                    c.execute(
                        "UPDATE interface_maps SET x=?, y=?, seen_count=?, last_seen=? WHERE id=?",
                        (x, y, existing[1] + 1, time.time(), existing[0]),
                    )
                else:
                    c.execute(
                        """INSERT INTO interface_maps
                           (app_name, element_text, element_type, x, y, confidence, last_seen, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            app_name,
                            text,
                            str(element.get("type", "text")),
                            x,
                            y,
                            float(element.get("confidence", 0.0)),
                            time.time(),
                            time.time(),
                        ),
                    )

    def recall_interface(self, app_name: str, limit: int = 15) -> list[dict]:
        """Perception memory read path: the most stable elements previously
        observed in this app, ranked by how often they were seen. Feeds the
        planner's world view — it never positions a click by itself."""
        if not app_name:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT element_text, element_type, seen_count, confidence
                   FROM interface_maps WHERE app_name=?
                   ORDER BY seen_count DESC, last_seen DESC LIMIT ?""",
                (app_name, limit),
            ).fetchall()
        return [
            {"text": r[0], "type": r[1], "seen_count": r[2], "confidence": r[3]}
            for r in rows
        ]

    def recall_element(self, app_name: str, element_text: str) -> Optional[dict]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """SELECT x, y, confidence, seen_count FROM interface_maps
                   WHERE app_name=? AND element_text=? COLLATE NOCASE
                   ORDER BY seen_count DESC, last_seen DESC LIMIT 1""",
                (app_name, element_text),
            )
            row = c.fetchone()
            if not row:
                c.execute(
                    """SELECT x, y, confidence, seen_count FROM interface_maps
                       WHERE app_name=? AND element_text LIKE ?
                       ORDER BY seen_count DESC LIMIT 1""",
                    (app_name, f"%{element_text}%"),
                )
                row = c.fetchone()
        if row:
            return {"x": row[0], "y": row[1], "confidence": row[2], "seen_count": row[3], "from_memory": True}
        return None

    def remember_task(self, instruction: str, steps: list[dict], success: bool, execution_time: float) -> None:
        instruction_hash = hashlib.md5(instruction.lower().encode()).hexdigest()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO task_patterns
                   (instruction_hash, instruction, steps_json, success, execution_time, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    instruction_hash,
                    instruction,
                    json.dumps(steps),
                    1 if success else 0,
                    execution_time,
                    time.time(),
                ),
            )

    def remember_evidence(self, task_id: str, evidence: list) -> None:
        """Persist collected Evidence as reusable knowledge (entity-attribute-value)."""
        if not evidence:
            return
        with self._connect() as conn:
            for item in evidence:
                if not getattr(item, "value", ""):
                    continue
                conn.execute(
                    """INSERT INTO knowledge
                       (entity, attribute, value, source, confidence, task_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.label,
                        item.kind,
                        item.value,
                        item.source,
                        float(item.confidence),
                        task_id,
                        time.time(),
                    ),
                )

    def recall_knowledge(self, terms: list[str], limit: int = 10) -> list[dict]:
        """Recall knowledge rows whose entity or value matches any term.
        Most recent first; naive term matching by design (embeddings later)."""
        terms = [t.strip() for t in terms if t and len(t.strip()) >= 3]
        if not terms:
            return []
        clauses = " OR ".join("entity LIKE ? OR value LIKE ?" for _ in terms)
        params: list = []
        for term in terms:
            like = f"%{term}%"
            params.extend([like, like])
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT entity, attribute, value, source, confidence, created_at
                    FROM knowledge WHERE {clauses}
                    ORDER BY created_at DESC LIMIT ?""",
                params,
            ).fetchall()
        return [
            {
                "entity": r[0], "attribute": r[1], "value": r[2],
                "source": r[3], "confidence": r[4], "created_at": r[5],
            }
            for r in rows
        ]

    def recall_task(self, instruction: str) -> Optional[dict]:
        instruction_hash = hashlib.md5(instruction.lower().encode()).hexdigest()
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """SELECT steps_json, execution_time FROM task_patterns
                   WHERE instruction_hash=? AND success=1
                   ORDER BY created_at DESC LIMIT 1""",
                (instruction_hash,),
            )
            row = c.fetchone()
        if row:
            return {"steps": json.loads(row[0]), "execution_time": row[1], "from_memory": True}
        return None

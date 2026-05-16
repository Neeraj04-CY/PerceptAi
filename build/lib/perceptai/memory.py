import json
import sqlite3
import time
from pathlib import Path

DB_PATH = str(Path(__file__).parent.parent / "perceptai_memory.db")


def init_db():
    """Initialize the memory database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
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
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS task_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instruction_hash TEXT,
            instruction TEXT,
            steps_json TEXT,
            success INTEGER,
            execution_time REAL,
            created_at REAL
        )
        """
    )

    conn.commit()
    conn.close()


def remember_interface(app_name, elements):
    """Store interface elements for an app."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for element in elements:
        pos = element.get("position", {})
        x = pos.get("x", -1)
        y = pos.get("y", -1)

        if x > 0 and y > 0:
            c.execute(
                """
                SELECT id, seen_count FROM interface_maps
                WHERE app_name=? AND element_text=?
                """,
                (app_name, element.get("text", "")),
            )

            existing = c.fetchone()

            if existing:
                c.execute(
                    """
                    UPDATE interface_maps
                    SET x=?, y=?, seen_count=?, last_seen=?
                    WHERE id=?
                    """,
                    (x, y, existing[1] + 1, time.time(), existing[0]),
                )
            else:
                c.execute(
                    """
                    INSERT INTO interface_maps
                    (app_name, element_text, element_type, x, y,
                     confidence, last_seen, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        app_name,
                        element.get("text", ""),
                        element.get("type", "unknown"),
                        x,
                        y,
                        element.get("confidence", 0.0),
                        time.time(),
                        time.time(),
                    ),
                )

    conn.commit()
    conn.close()


def recall_element(app_name, element_text):
    """
    Try to recall where an element was last seen in an app.
    Returns position if found in memory.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        """
        SELECT x, y, confidence, seen_count FROM interface_maps
        WHERE app_name=? AND element_text=?
        ORDER BY seen_count DESC, last_seen DESC
        LIMIT 1
        """,
        (app_name, element_text.lower()),
    )

    result = c.fetchone()

    if not result:
        c.execute(
            """
            SELECT x, y, confidence, seen_count FROM interface_maps
            WHERE app_name=? AND element_text LIKE ?
            ORDER BY seen_count DESC
            LIMIT 1
            """,
            (app_name, f"%{element_text.lower()}%"),
        )
        result = c.fetchone()

    conn.close()

    if result:
        return {
            "x": result[0],
            "y": result[1],
            "confidence": result[2],
            "seen_count": result[3],
            "from_memory": True,
        }
    return None


def remember_task(instruction, steps, success, execution_time):
    """Store a completed task pattern."""
    import hashlib

    instruction_hash = hashlib.md5(instruction.lower().encode()).hexdigest()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO task_patterns
        (instruction_hash, instruction, steps_json,
         success, execution_time, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            instruction_hash,
            instruction,
            json.dumps(steps),
            1 if success else 0,
            execution_time,
            time.time(),
        ),
    )

    conn.commit()
    conn.close()


def recall_task(instruction):
    """Check if we've done a similar task before."""
    import hashlib

    instruction_hash = hashlib.md5(instruction.lower().encode()).hexdigest()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        """
        SELECT steps_json, execution_time FROM task_patterns
        WHERE instruction_hash=? AND success=1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (instruction_hash,),
    )

    result = c.fetchone()
    conn.close()

    if result:
        return {
            "steps": json.loads(result[0]),
            "execution_time": result[1],
            "from_memory": True,
        }
    return None


init_db()

"""SQLite database for job persistence — replaces JSON file storage."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    pdk_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    gds_path TEXT,
    report_path TEXT,
    top_cell TEXT,
    total_violations INTEGER DEFAULT 0,
    error TEXT,
    iteration INTEGER DEFAULT 1
)
"""

_PROVENANCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS fix_provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    iteration INTEGER NOT NULL,
    rule_id TEXT NOT NULL,
    violation_category TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    confidence TEXT NOT NULL,
    action TEXT NOT NULL,
    flag_reason TEXT,
    before_points TEXT NOT NULL,
    after_points TEXT NOT NULL,
    cell_name TEXT NOT NULL,
    gds_layer INTEGER NOT NULL,
    gds_datatype INTEGER NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
)
"""

JOB_COLUMNS = (
    "job_id",
    "filename",
    "pdk_name",
    "status",
    "created_at",
    "updated_at",
    "gds_path",
    "report_path",
    "top_cell",
    "total_violations",
    "error",
    "iteration",
)


class Database:
    """Thread-safe SQLite database for job metadata.

    Each thread gets its own connection via thread-local storage.
    WAL mode is enabled for concurrent read/write performance.
    """

    def __init__(self, db_path: str | Path):
        self._path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        conn = self._get_conn()
        conn.execute(_SCHEMA)
        conn.execute(_PROVENANCE_SCHEMA)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def insert(self, data: dict) -> None:
        """Insert a new job row."""
        conn = self._get_conn()
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        conn.execute(
            f"INSERT INTO jobs ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        conn.commit()

    def get(self, job_id: str) -> dict | None:
        """Get a job by ID. Returns None if not found."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        """List all jobs, most recent first."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def update(self, job_id: str, updates: dict) -> None:
        """Update specific fields on a job."""
        conn = self._get_conn()
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [job_id]
        conn.execute(f"UPDATE jobs SET {sets} WHERE job_id = ?", vals)
        conn.commit()

    def delete(self, job_id: str) -> None:
        """Delete a job by ID."""
        conn = self._get_conn()
        conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        conn.commit()

    def insert_provenance(
        self,
        job_id: str,
        iteration: int,
        rule_id: str,
        violation_category: str,
        rule_type: str,
        confidence: str,
        action: str,
        before_points: list,
        after_points: list,
        cell_name: str,
        gds_layer: int,
        gds_datatype: int,
        flag_reason: str | None = None,
    ) -> int:
        """Insert a fix provenance record. Returns the new row id."""
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO fix_provenance
            (job_id, iteration, rule_id, violation_category, rule_type,
             confidence, action, flag_reason, before_points, after_points,
             cell_name, gds_layer, gds_datatype, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                iteration,
                rule_id,
                violation_category,
                rule_type,
                confidence,
                action,
                flag_reason,
                json.dumps(before_points),
                json.dumps(after_points),
                cell_name,
                gds_layer,
                gds_datatype,
                time.time(),
            ),
        )
        conn.commit()
        return cursor.lastrowid

    def get_provenance(
        self,
        job_id: str,
        iteration: int | None = None,
        action: str | None = None,
    ) -> list[dict]:
        """Get provenance records for a job, optionally filtered by iteration or action."""
        conn = self._get_conn()
        query = "SELECT * FROM fix_provenance WHERE job_id = ?"
        params: list = [job_id]
        if iteration is not None:
            query += " AND iteration = ?"
            params.append(iteration)
        if action is not None:
            query += " AND action = ?"
            params.append(action)
        query += " ORDER BY iteration, created_at"
        rows = conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["before_points"] = json.loads(d["before_points"])
            d["after_points"] = json.loads(d["after_points"])
            result.append(d)
        return result

    def update_provenance_action(
        self, provenance_id: int, new_action: str
    ) -> None:
        """Update the action field on a provenance record."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE fix_provenance SET action = ? WHERE id = ?",
            (new_action, provenance_id),
        )
        conn.commit()

    def close(self) -> None:
        """Close the thread-local connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

"""SQLite database for job persistence — replaces JSON file storage."""

from __future__ import annotations

import sqlite3
import threading
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

    def close(self) -> None:
        """Close the thread-local connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

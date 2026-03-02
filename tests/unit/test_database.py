"""Tests for SQLite database backend."""

import tempfile
import threading
from pathlib import Path

import pytest

from backend.jobs.database import Database


@pytest.fixture
def tmp_db():
    with tempfile.TemporaryDirectory() as d:
        yield Database(Path(d) / "test.db")


class TestDatabase:
    def test_insert_and_get(self, tmp_db):
        tmp_db.insert(
            {
                "job_id": "abc",
                "filename": "test.gds",
                "pdk_name": "sky130",
                "status": "created",
                "created_at": 1000.0,
                "updated_at": 1000.0,
                "total_violations": 0,
                "iteration": 1,
            }
        )
        row = tmp_db.get("abc")
        assert row is not None
        assert row["job_id"] == "abc"
        assert row["filename"] == "test.gds"
        assert row["iteration"] == 1

    def test_get_missing(self, tmp_db):
        assert tmp_db.get("nonexistent") is None

    def test_list_all(self, tmp_db):
        for i in range(3):
            tmp_db.insert(
                {
                    "job_id": f"job{i}",
                    "filename": f"test{i}.gds",
                    "pdk_name": "sky130",
                    "status": "created",
                    "created_at": 1000.0 + i,
                    "updated_at": 1000.0 + i,
                    "total_violations": 0,
                    "iteration": 1,
                }
            )
        rows = tmp_db.list_all()
        assert len(rows) == 3
        # Most recent first
        assert rows[0]["job_id"] == "job2"

    def test_update(self, tmp_db):
        tmp_db.insert(
            {
                "job_id": "abc",
                "filename": "test.gds",
                "pdk_name": "sky130",
                "status": "created",
                "created_at": 1000.0,
                "updated_at": 1000.0,
                "total_violations": 0,
                "iteration": 1,
            }
        )
        tmp_db.update("abc", {"status": "uploaded", "total_violations": 5})
        row = tmp_db.get("abc")
        assert row["status"] == "uploaded"
        assert row["total_violations"] == 5

    def test_delete(self, tmp_db):
        tmp_db.insert(
            {
                "job_id": "abc",
                "filename": "test.gds",
                "pdk_name": "sky130",
                "status": "created",
                "created_at": 1000.0,
                "updated_at": 1000.0,
                "total_violations": 0,
                "iteration": 1,
            }
        )
        tmp_db.delete("abc")
        assert tmp_db.get("abc") is None

    def test_thread_safety(self, tmp_db):
        """Each thread gets its own connection."""
        results = []

        def worker(job_id):
            tmp_db.insert(
                {
                    "job_id": job_id,
                    "filename": f"{job_id}.gds",
                    "pdk_name": "sky130",
                    "status": "created",
                    "created_at": 1000.0,
                    "updated_at": 1000.0,
                    "total_violations": 0,
                    "iteration": 1,
                }
            )
            row = tmp_db.get(job_id)
            results.append(row)

        threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 5
        assert len(tmp_db.list_all()) == 5

    def test_persistence(self):
        """Data survives new Database instance."""
        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "test.db"
            db1 = Database(db_path)
            db1.insert(
                {
                    "job_id": "persist",
                    "filename": "test.gds",
                    "pdk_name": "sky130",
                    "status": "uploaded",
                    "created_at": 1000.0,
                    "updated_at": 1000.0,
                    "total_violations": 42,
                    "iteration": 2,
                }
            )
            db1.close()

            db2 = Database(db_path)
            row = db2.get("persist")
            assert row is not None
            assert row["status"] == "uploaded"
            assert row["total_violations"] == 42
            assert row["iteration"] == 2
            db2.close()

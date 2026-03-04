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

    def test_insert_and_get_provenance(self, tmp_db):
        """Insert a provenance record and retrieve it."""
        row_id = tmp_db.insert_provenance(
            job_id="abc",
            iteration=1,
            rule_id="m1.1",
            violation_category="m1.1",
            rule_type="min_width",
            confidence="high",
            action="auto_applied",
            before_points=[[0.0, 0.0], [0.1, 0.0], [0.1, 1.0], [0.0, 1.0]],
            after_points=[[0.0, 0.0], [0.14, 0.0], [0.14, 1.0], [0.0, 1.0]],
            cell_name="TOP",
            gds_layer=68,
            gds_datatype=20,
        )
        assert row_id is not None
        records = tmp_db.get_provenance("abc")
        assert len(records) == 1
        r = records[0]
        assert r["job_id"] == "abc"
        assert r["iteration"] == 1
        assert r["rule_id"] == "m1.1"
        assert r["confidence"] == "high"
        assert r["action"] == "auto_applied"
        assert r["flag_reason"] is None
        assert r["before_points"] == [[0.0, 0.0], [0.1, 0.0], [0.1, 1.0], [0.0, 1.0]]
        assert r["after_points"] == [[0.0, 0.0], [0.14, 0.0], [0.14, 1.0], [0.0, 1.0]]
        assert r["cell_name"] == "TOP"
        assert r["gds_layer"] == 68

    def test_provenance_with_flag_reason(self, tmp_db):
        """Flagged provenance records include a reason."""
        tmp_db.insert_provenance(
            job_id="abc",
            iteration=1,
            rule_id="m1.1",
            violation_category="m1.1",
            rule_type="min_width",
            confidence="low",
            action="flagged",
            flag_reason="low_confidence",
            before_points=[[0.0, 0.0], [0.1, 0.0]],
            after_points=[[0.0, 0.0], [0.14, 0.0]],
            cell_name="TOP",
            gds_layer=68,
            gds_datatype=20,
        )
        records = tmp_db.get_provenance("abc")
        assert records[0]["action"] == "flagged"
        assert records[0]["flag_reason"] == "low_confidence"

    def test_provenance_filter_by_iteration(self, tmp_db):
        """get_provenance can filter by iteration."""
        for i in range(1, 4):
            tmp_db.insert_provenance(
                job_id="abc",
                iteration=i,
                rule_id="m1.1",
                violation_category="m1.1",
                rule_type="min_width",
                confidence="high",
                action="auto_applied",
                before_points=[[0.0, 0.0]],
                after_points=[[0.14, 0.0]],
                cell_name="TOP",
                gds_layer=68,
                gds_datatype=20,
            )
        all_records = tmp_db.get_provenance("abc")
        assert len(all_records) == 3
        iter2 = tmp_db.get_provenance("abc", iteration=2)
        assert len(iter2) == 1
        assert iter2[0]["iteration"] == 2

    def test_provenance_filter_by_action(self, tmp_db):
        """get_provenance can filter by action."""
        tmp_db.insert_provenance(
            job_id="abc", iteration=1, rule_id="m1.1",
            violation_category="m1.1", rule_type="min_width",
            confidence="high", action="auto_applied",
            before_points=[], after_points=[], cell_name="TOP",
            gds_layer=68, gds_datatype=20,
        )
        tmp_db.insert_provenance(
            job_id="abc", iteration=1, rule_id="m1.1",
            violation_category="m1.1", rule_type="min_width",
            confidence="low", action="flagged", flag_reason="low_confidence",
            before_points=[], after_points=[], cell_name="TOP",
            gds_layer=68, gds_datatype=20,
        )
        flagged = tmp_db.get_provenance("abc", action="flagged")
        assert len(flagged) == 1
        assert flagged[0]["action"] == "flagged"

    def test_update_provenance_action(self, tmp_db):
        """Can update action field on a provenance record."""
        row_id = tmp_db.insert_provenance(
            job_id="abc", iteration=1, rule_id="m1.1",
            violation_category="m1.1", rule_type="min_width",
            confidence="medium", action="flagged", flag_reason="multi_layer",
            before_points=[], after_points=[], cell_name="TOP",
            gds_layer=68, gds_datatype=20,
        )
        tmp_db.update_provenance_action(row_id, "human_approved")
        records = tmp_db.get_provenance("abc")
        assert records[0]["action"] == "human_approved"

    def test_provenance_empty_for_unknown_job(self, tmp_db):
        """No records for a job that doesn't exist."""
        records = tmp_db.get_provenance("nonexistent")
        assert records == []

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

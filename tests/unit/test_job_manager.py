"""Tests for the job manager (SQLite-backed)."""

import tempfile
from pathlib import Path

import pytest

from backend.jobs.manager import Job, JobManager, JobStatus


@pytest.fixture
def tmp_jobs_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def manager(tmp_jobs_dir):
    return JobManager(jobs_dir=tmp_jobs_dir)


class TestJob:
    def test_to_dict(self):
        job = Job(job_id="abc", filename="test.gds", pdk_name="sky130")
        d = job.to_dict()
        assert d["job_id"] == "abc"
        assert d["status"] == "created"
        assert d["filename"] == "test.gds"
        assert d["iteration"] == 1

    def test_from_dict(self):
        d = {
            "job_id": "abc",
            "filename": "test.gds",
            "pdk_name": "sky130",
            "status": "uploaded",
            "created_at": 1000.0,
            "updated_at": 1000.0,
            "gds_path": None,
            "report_path": None,
            "top_cell": None,
            "total_violations": 0,
            "error": None,
            "iteration": 1,
        }
        job = Job.from_dict(d)
        assert job.status == JobStatus.uploaded
        assert job.filename == "test.gds"

    def test_from_dict_legacy_no_iteration(self):
        """Legacy data without iteration field should default to 1."""
        d = {
            "job_id": "abc",
            "filename": "test.gds",
            "pdk_name": "sky130",
            "status": "created",
            "created_at": 1000.0,
            "updated_at": 1000.0,
            "gds_path": None,
            "report_path": None,
            "top_cell": None,
            "total_violations": 0,
            "error": None,
        }
        job = Job.from_dict(d)
        assert job.iteration == 1

    def test_roundtrip(self):
        original = Job(
            job_id="xyz",
            filename="inv.gds",
            pdk_name="sky130",
            status=JobStatus.drc_complete,
            total_violations=42,
            iteration=3,
        )
        restored = Job.from_dict(original.to_dict())
        assert restored.job_id == original.job_id
        assert restored.status == original.status
        assert restored.total_violations == 42
        assert restored.iteration == 3

    def test_fixes_applied_status(self):
        job = Job(
            job_id="abc",
            filename="test.gds",
            pdk_name="sky130",
            status=JobStatus.fixes_applied,
        )
        assert job.status == JobStatus.fixes_applied
        assert job.to_dict()["status"] == "fixes_applied"


class TestJobManager:
    def test_create(self, manager):
        job = manager.create("test.gds", "sky130")
        assert job.filename == "test.gds"
        assert job.pdk_name == "sky130"
        assert job.status == JobStatus.created
        assert len(job.job_id) == 8
        assert job.iteration == 1

    def test_get(self, manager):
        job = manager.create("test.gds", "sky130")
        retrieved = manager.get(job.job_id)
        assert retrieved.job_id == job.job_id

    def test_get_not_found(self, manager):
        with pytest.raises(KeyError, match="not found"):
            manager.get("nonexistent")

    def test_list_jobs(self, manager):
        manager.create("a.gds", "sky130")
        manager.create("b.gds", "sky130")
        jobs = manager.list_jobs()
        assert len(jobs) == 2

    def test_update_status(self, manager):
        job = manager.create("test.gds", "sky130")
        updated = manager.update_status(job.job_id, JobStatus.uploaded, gds_path="/tmp/test.gds")
        assert updated.status == JobStatus.uploaded
        assert updated.gds_path == "/tmp/test.gds"

    def test_update_status_with_error(self, manager):
        job = manager.create("test.gds", "sky130")
        updated = manager.update_status(job.job_id, JobStatus.drc_failed, error="KLayout not found")
        assert updated.status == JobStatus.drc_failed
        assert updated.error == "KLayout not found"

    def test_update_iteration(self, manager):
        job = manager.create("test.gds", "sky130")
        updated = manager.update_status(job.job_id, JobStatus.running_drc, iteration=2)
        assert updated.iteration == 2

    def test_persistence(self, tmp_jobs_dir):
        # Create a manager and add a job
        m1 = JobManager(jobs_dir=tmp_jobs_dir)
        job = m1.create("test.gds", "sky130")
        m1.update_status(job.job_id, JobStatus.drc_complete, total_violations=5)

        # Create a new manager pointing at the same dir
        m2 = JobManager(jobs_dir=tmp_jobs_dir)
        restored = m2.get(job.job_id)
        assert restored.status == JobStatus.drc_complete
        assert restored.total_violations == 5

    def test_job_dir(self, manager):
        job = manager.create("test.gds", "sky130")
        d = manager.job_dir(job.job_id)
        assert d.exists()
        assert d.name == job.job_id

    def test_sqlite_file_created(self, tmp_jobs_dir):
        JobManager(jobs_dir=tmp_jobs_dir)
        assert (tmp_jobs_dir / "jobs.db").exists()

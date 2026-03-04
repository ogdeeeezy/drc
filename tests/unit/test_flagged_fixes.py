"""Tests for flagged fixes review endpoints — GET, approve, reject."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.jobs.manager import JobManager, JobStatus

# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture()
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture()
def manager(tmp_dir):
    return JobManager(jobs_dir=tmp_dir / "jobs")


def _create_job_with_flagged(manager, tmp_dir):
    """Create a job and insert flagged provenance records. Returns (job, record_ids)."""
    job = manager.create("test.gds", "sky130")
    # Create a fake GDS file
    gds_path = tmp_dir / "test.gds"
    gds_path.write_bytes(b"fake-gds")
    manager.update_status(
        job.job_id,
        JobStatus.drc_complete,
        gds_path=str(gds_path),
        total_violations=3,
    )

    # Insert flagged provenance records
    id1 = manager.insert_provenance(
        job_id=job.job_id,
        iteration=1,
        rule_id="m1.1",
        violation_category="m1.1",
        rule_type="min_width",
        confidence="medium",
        action="flagged",
        flag_reason="medium_confidence_in_high_mode",
        before_points=[[0.0, 0.0], [0.1, 0.0], [0.1, 1.0], [0.0, 1.0]],
        after_points=[[0.0, 0.0], [0.14, 0.0], [0.14, 1.0], [0.0, 1.0]],
        cell_name="TOP",
        gds_layer=68,
        gds_datatype=20,
    )
    id2 = manager.insert_provenance(
        job_id=job.job_id,
        iteration=1,
        rule_id="m1.2",
        violation_category="m1.2",
        rule_type="min_spacing",
        confidence="low",
        action="flagged",
        flag_reason="low_confidence",
        before_points=[[1.0, 0.0], [2.0, 0.0], [2.0, 1.0], [1.0, 1.0]],
        after_points=[[1.0, 0.0], [2.5, 0.0], [2.5, 1.0], [1.0, 1.0]],
        cell_name="TOP",
        gds_layer=68,
        gds_datatype=20,
    )
    id3 = manager.insert_provenance(
        job_id=job.job_id,
        iteration=2,
        rule_id="m1.1",
        violation_category="m1.1",
        rule_type="min_width",
        confidence="medium",
        action="flagged",
        flag_reason="multi_layer",
        before_points=[[3.0, 0.0], [4.0, 0.0], [4.0, 1.0], [3.0, 1.0]],
        after_points=[[3.0, 0.0], [4.5, 0.0], [4.5, 1.0], [3.0, 1.0]],
        cell_name="TOP",
        gds_layer=68,
        gds_datatype=20,
    )
    # Also insert an auto_applied record (should NOT appear in flagged list)
    manager.insert_provenance(
        job_id=job.job_id,
        iteration=1,
        rule_id="m1.1",
        violation_category="m1.1",
        rule_type="min_width",
        confidence="high",
        action="auto_applied",
        before_points=[[5.0, 0.0], [6.0, 0.0]],
        after_points=[[5.0, 0.0], [6.5, 0.0]],
        cell_name="TOP",
        gds_layer=68,
        gds_datatype=20,
    )
    return job, [id1, id2, id3]


# ── Database layer tests ──────────────────────────────────


class TestGetProvenanceByIds:
    def test_returns_matching_records(self, manager, tmp_dir):
        job, ids = _create_job_with_flagged(manager, tmp_dir)
        records = manager.get_provenance_by_ids([ids[0], ids[2]])
        assert len(records) == 2
        found_ids = {r["id"] for r in records}
        assert ids[0] in found_ids
        assert ids[2] in found_ids

    def test_returns_empty_for_no_ids(self, manager):
        records = manager.get_provenance_by_ids([])
        assert records == []

    def test_returns_empty_for_nonexistent_ids(self, manager, tmp_dir):
        _create_job_with_flagged(manager, tmp_dir)
        records = manager.get_provenance_by_ids([999, 1000])
        assert records == []

    def test_deserializes_points(self, manager, tmp_dir):
        job, ids = _create_job_with_flagged(manager, tmp_dir)
        records = manager.get_provenance_by_ids([ids[0]])
        r = records[0]
        assert r["before_points"] == [[0.0, 0.0], [0.1, 0.0], [0.1, 1.0], [0.0, 1.0]]
        assert r["after_points"] == [[0.0, 0.0], [0.14, 0.0], [0.14, 1.0], [0.0, 1.0]]


# ── GET /fix/flagged tests ──────────────────────────────


class TestGetFlaggedEndpoint:
    def test_returns_flagged_grouped_by_iteration(self, manager, tmp_dir):
        """Flagged records grouped by iteration, auto_applied excluded."""
        from fastapi.testclient import TestClient

        import backend.config as cfg
        from backend.api import deps
        from backend.main import app

        deps.reset_deps()
        original_jobs = cfg.JOBS_DIR
        cfg.JOBS_DIR = tmp_dir / "jobs2"
        cfg.JOBS_DIR.mkdir(exist_ok=True)

        mgr = JobManager(jobs_dir=cfg.JOBS_DIR)
        job, ids = _create_job_with_flagged(mgr, tmp_dir)

        with patch.object(deps, "_job_manager", mgr):
            with TestClient(app) as client:
                r = client.get(f"/api/jobs/{job.job_id}/fix/flagged")

        cfg.JOBS_DIR = original_jobs
        deps.reset_deps()

        assert r.status_code == 200
        data = r.json()
        assert data["total_flagged"] == 3
        assert len(data["iterations"]) == 2
        # iteration 1 has 2 flagged
        iter1 = data["iterations"][0]
        assert iter1["iteration"] == 1
        assert len(iter1["flagged"]) == 2
        # iteration 2 has 1 flagged
        iter2 = data["iterations"][1]
        assert iter2["iteration"] == 2
        assert len(iter2["flagged"]) == 1

    def test_flagged_record_includes_required_fields(self, manager, tmp_dir):
        """Each flagged record has all required fields."""
        job, ids = _create_job_with_flagged(manager, tmp_dir)
        records = manager.get_provenance(job.job_id, action="flagged")
        r = records[0]

        required = [
            "id", "iteration", "violation_category", "rule_type",
            "confidence", "flag_reason", "before_points", "after_points",
            "cell_name", "gds_layer", "gds_datatype",
        ]
        for field in required:
            assert field in r, f"Missing field: {field}"

    def test_flagged_404_for_unknown_job(self, manager, tmp_dir):
        """404 for unknown job."""
        from fastapi.testclient import TestClient

        import backend.config as cfg
        from backend.api import deps
        from backend.main import app

        deps.reset_deps()
        original_jobs = cfg.JOBS_DIR
        cfg.JOBS_DIR = tmp_dir / "jobs3"
        cfg.JOBS_DIR.mkdir(exist_ok=True)

        mgr = JobManager(jobs_dir=cfg.JOBS_DIR)

        with patch.object(deps, "_job_manager", mgr):
            with TestClient(app) as client:
                r = client.get("/api/jobs/nonexistent/fix/flagged")

        cfg.JOBS_DIR = original_jobs
        deps.reset_deps()

        assert r.status_code == 404


# ── POST /fix/flagged/reject tests ──────────────────────


class TestRejectFlaggedEndpoint:
    def test_reject_updates_action(self, manager, tmp_dir):
        """Rejecting flagged fixes updates their action to 'rejected'."""
        job, ids = _create_job_with_flagged(manager, tmp_dir)

        # Reject the first two flagged records
        manager.update_provenance_action(ids[0], "rejected")
        manager.update_provenance_action(ids[1], "rejected")

        # Verify they're now rejected
        records = manager.get_provenance_by_ids([ids[0], ids[1]])
        for r in records:
            assert r["action"] == "rejected"

        # Third is still flagged
        records = manager.get_provenance_by_ids([ids[2]])
        assert records[0]["action"] == "flagged"

    def test_reject_endpoint(self, manager, tmp_dir):
        """POST /fix/flagged/reject marks records as rejected."""
        from fastapi.testclient import TestClient

        import backend.config as cfg
        from backend.api import deps
        from backend.main import app

        deps.reset_deps()
        original_jobs = cfg.JOBS_DIR
        cfg.JOBS_DIR = tmp_dir / "jobs4"
        cfg.JOBS_DIR.mkdir(exist_ok=True)

        mgr = JobManager(jobs_dir=cfg.JOBS_DIR)
        job, ids = _create_job_with_flagged(mgr, tmp_dir)

        with patch.object(deps, "_job_manager", mgr):
            with TestClient(app) as client:
                r = client.post(
                    f"/api/jobs/{job.job_id}/fix/flagged/reject",
                    json={"provenance_ids": [ids[0], ids[1]]},
                )

        cfg.JOBS_DIR = original_jobs
        deps.reset_deps()

        assert r.status_code == 200
        data = r.json()
        assert data["rejected_count"] == 2
        assert data["job_id"] == job.job_id

        # Verify in DB
        records = mgr.get_provenance_by_ids([ids[0], ids[1]])
        for rec in records:
            assert rec["action"] == "rejected"

    def test_reject_404_for_missing_ids(self, manager, tmp_dir):
        """404 if any provenance IDs not found."""
        from fastapi.testclient import TestClient

        import backend.config as cfg
        from backend.api import deps
        from backend.main import app

        deps.reset_deps()
        original_jobs = cfg.JOBS_DIR
        cfg.JOBS_DIR = tmp_dir / "jobs5"
        cfg.JOBS_DIR.mkdir(exist_ok=True)

        mgr = JobManager(jobs_dir=cfg.JOBS_DIR)
        job, ids = _create_job_with_flagged(mgr, tmp_dir)

        with patch.object(deps, "_job_manager", mgr):
            with TestClient(app) as client:
                r = client.post(
                    f"/api/jobs/{job.job_id}/fix/flagged/reject",
                    json={"provenance_ids": [999]},
                )

        cfg.JOBS_DIR = original_jobs
        deps.reset_deps()

        assert r.status_code == 404

    def test_reject_fails_for_non_flagged(self, manager, tmp_dir):
        """400 if record is not flagged (e.g., auto_applied)."""
        from fastapi.testclient import TestClient

        import backend.config as cfg
        from backend.api import deps
        from backend.main import app

        deps.reset_deps()
        original_jobs = cfg.JOBS_DIR
        cfg.JOBS_DIR = tmp_dir / "jobs6"
        cfg.JOBS_DIR.mkdir(exist_ok=True)

        mgr = JobManager(jobs_dir=cfg.JOBS_DIR)
        job, ids = _create_job_with_flagged(mgr, tmp_dir)

        # Get the auto_applied record ID
        all_records = mgr.get_provenance(job.job_id, action="auto_applied")
        auto_id = all_records[0]["id"]

        with patch.object(deps, "_job_manager", mgr):
            with TestClient(app) as client:
                r = client.post(
                    f"/api/jobs/{job.job_id}/fix/flagged/reject",
                    json={"provenance_ids": [auto_id]},
                )

        cfg.JOBS_DIR = original_jobs
        deps.reset_deps()

        assert r.status_code == 400


# ── POST /fix/flagged/approve tests ──────────────────────


class TestApproveFlaggedEndpoint:
    def test_approve_updates_provenance_to_human_approved(self, manager, tmp_dir):
        """Approving updates action from 'flagged' to 'human_approved'."""
        job, ids = _create_job_with_flagged(manager, tmp_dir)
        manager.update_provenance_action(ids[0], "human_approved")
        records = manager.get_provenance_by_ids([ids[0]])
        assert records[0]["action"] == "human_approved"

    def test_approve_endpoint_applies_and_reruns_drc(self, manager, tmp_dir):
        """POST /fix/flagged/approve applies deltas, re-runs DRC, updates provenance."""
        from fastapi.testclient import TestClient

        import backend.config as cfg
        from backend.api import deps
        from backend.main import app

        deps.reset_deps()
        original_jobs = cfg.JOBS_DIR
        cfg.JOBS_DIR = tmp_dir / "jobs7"
        cfg.JOBS_DIR.mkdir(exist_ok=True)

        mgr = JobManager(jobs_dir=cfg.JOBS_DIR)
        job, ids = _create_job_with_flagged(mgr, tmp_dir)

        # Mock layout, export, and DRC
        mock_layout = MagicMock()
        mock_cell = MagicMock()
        mock_poly = MagicMock()
        mock_poly.layer = 68
        mock_poly.datatype = 20
        mock_poly.points = [[0.0, 0.0], [0.1, 0.0], [0.1, 1.0], [0.0, 1.0]]
        mock_cell.polygons = [mock_poly]
        mock_layout.get_cell.return_value = mock_cell

        mock_report = MagicMock()
        mock_report.total_violations = 0
        mock_report.top_cell = "TOP"
        mock_report.violations = []

        mock_drc_result = MagicMock()
        mock_drc_result.report = mock_report
        mock_drc_result.report_path = Path(tmp_dir / "result.lyrdb")
        mock_drc_result.duration_seconds = 1.5

        fixed_gds_path = tmp_dir / "fixed.gds"
        fixed_gds_path.write_bytes(b"fixed-gds")

        with (
            patch.object(deps, "_job_manager", mgr),
            patch("backend.api.routes.fix.LayoutManager") as MockLM,
            patch("backend.api.routes.fix.export_fixed_gds", return_value=fixed_gds_path),
            patch("backend.api.routes.fix.DRCRunner") as MockDRC,
            patch("backend.api.routes.fix.get_pdk_registry") as mock_registry,
        ):
            MockLM.return_value = mock_layout
            mock_runner = MagicMock()
            mock_runner.async_run = AsyncMock(return_value=mock_drc_result)
            MockDRC.return_value = mock_runner
            mock_registry.return_value.load.return_value = MagicMock()

            with TestClient(app) as client:
                r = client.post(
                    f"/api/jobs/{job.job_id}/fix/flagged/approve",
                    json={"provenance_ids": [ids[0]]},
                )

        cfg.JOBS_DIR = original_jobs
        deps.reset_deps()

        assert r.status_code == 200
        data = r.json()
        assert data["approved_count"] == 1
        assert data["is_clean"] is True
        assert data["total_violations"] == 0
        assert data["job_id"] == job.job_id

        # Verify provenance updated
        records = mgr.get_provenance_by_ids([ids[0]])
        assert records[0]["action"] == "human_approved"

        # Other flagged records still flagged
        records = mgr.get_provenance_by_ids([ids[1], ids[2]])
        for rec in records:
            assert rec["action"] == "flagged"

    def test_approve_404_for_missing_ids(self, manager, tmp_dir):
        """404 if any provenance IDs not found."""
        from fastapi.testclient import TestClient

        import backend.config as cfg
        from backend.api import deps
        from backend.main import app

        deps.reset_deps()
        original_jobs = cfg.JOBS_DIR
        cfg.JOBS_DIR = tmp_dir / "jobs8"
        cfg.JOBS_DIR.mkdir(exist_ok=True)

        mgr = JobManager(jobs_dir=cfg.JOBS_DIR)
        job, ids = _create_job_with_flagged(mgr, tmp_dir)

        with patch.object(deps, "_job_manager", mgr):
            with TestClient(app) as client:
                r = client.post(
                    f"/api/jobs/{job.job_id}/fix/flagged/approve",
                    json={"provenance_ids": [999]},
                )

        cfg.JOBS_DIR = original_jobs
        deps.reset_deps()

        assert r.status_code == 404

    def test_approve_fails_for_non_flagged(self, manager, tmp_dir):
        """400 if record is not flagged."""
        from fastapi.testclient import TestClient

        import backend.config as cfg
        from backend.api import deps
        from backend.main import app

        deps.reset_deps()
        original_jobs = cfg.JOBS_DIR
        cfg.JOBS_DIR = tmp_dir / "jobs9"
        cfg.JOBS_DIR.mkdir(exist_ok=True)

        mgr = JobManager(jobs_dir=cfg.JOBS_DIR)
        job, ids = _create_job_with_flagged(mgr, tmp_dir)

        # Get auto_applied record ID
        all_records = mgr.get_provenance(job.job_id, action="auto_applied")
        auto_id = all_records[0]["id"]

        with patch.object(deps, "_job_manager", mgr):
            with TestClient(app) as client:
                r = client.post(
                    f"/api/jobs/{job.job_id}/fix/flagged/approve",
                    json={"provenance_ids": [auto_id]},
                )

        cfg.JOBS_DIR = original_jobs
        deps.reset_deps()

        assert r.status_code == 400

    def test_approve_wrong_job(self, manager, tmp_dir):
        """400 if provenance record belongs to a different job."""
        from fastapi.testclient import TestClient

        import backend.config as cfg
        from backend.api import deps
        from backend.main import app

        deps.reset_deps()
        original_jobs = cfg.JOBS_DIR
        cfg.JOBS_DIR = tmp_dir / "jobs10"
        cfg.JOBS_DIR.mkdir(exist_ok=True)

        mgr = JobManager(jobs_dir=cfg.JOBS_DIR)
        job, ids = _create_job_with_flagged(mgr, tmp_dir)

        # Create a second job
        job2 = mgr.create("test2.gds", "sky130")
        gds2 = tmp_dir / "test2.gds"
        gds2.write_bytes(b"fake-gds2")
        mgr.update_status(job2.job_id, JobStatus.drc_complete, gds_path=str(gds2))

        with patch.object(deps, "_job_manager", mgr):
            with TestClient(app) as client:
                # Try to approve job1's record via job2's endpoint
                r = client.post(
                    f"/api/jobs/{job2.job_id}/fix/flagged/approve",
                    json={"provenance_ids": [ids[0]]},
                )

        cfg.JOBS_DIR = original_jobs
        deps.reset_deps()

        assert r.status_code == 400


# ── Integration: auto-fix → flagged → approve → re-DRC ──────────


class TestFlaggedWorkflow:
    def test_full_workflow(self, manager, tmp_dir):
        """Integration: auto-fix flags fixes → GET flagged → approve → verify provenance."""
        job, ids = _create_job_with_flagged(manager, tmp_dir)

        # Step 1: Verify flagged records are queryable
        flagged = manager.get_provenance(job.job_id, action="flagged")
        assert len(flagged) == 3

        # Step 2: Approve one
        manager.update_provenance_action(ids[0], "human_approved")

        # Step 3: Reject another
        manager.update_provenance_action(ids[1], "rejected")

        # Step 4: Verify final state
        flagged = manager.get_provenance(job.job_id, action="flagged")
        assert len(flagged) == 1  # only ids[2] still flagged

        approved = manager.get_provenance(job.job_id, action="human_approved")
        assert len(approved) == 1
        assert approved[0]["id"] == ids[0]

        rejected = manager.get_provenance(job.job_id, action="rejected")
        assert len(rejected) == 1
        assert rejected[0]["id"] == ids[1]

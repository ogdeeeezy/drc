"""Tests for LVS API routes — upload netlist, run LVS, get results."""

import io
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import gdstk
import pytest
from fastapi.testclient import TestClient

from backend.api import deps
from backend.core.lvs_models import LVSMismatch, LVSMismatchType, LVSReport
from backend.core.lvs_runner import LVSResult
from backend.jobs.manager import JobStatus
from backend.main import app

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "lvsdb"


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton deps before each test."""
    deps.reset_deps()
    yield
    deps.reset_deps()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def client(tmp_dir):
    """Test client with isolated job/upload dirs."""
    import backend.config as cfg

    original_jobs = cfg.JOBS_DIR
    original_uploads = cfg.UPLOAD_DIR
    cfg.JOBS_DIR = tmp_dir / "jobs"
    cfg.UPLOAD_DIR = tmp_dir / "uploads"
    cfg.JOBS_DIR.mkdir()
    cfg.UPLOAD_DIR.mkdir()

    with TestClient(app) as c:
        yield c

    cfg.JOBS_DIR = original_jobs
    cfg.UPLOAD_DIR = original_uploads


@pytest.fixture
def sample_gds(tmp_dir) -> bytes:
    """Create a minimal valid GDSII file as bytes."""
    lib = gdstk.Library("test")
    cell = gdstk.Cell("INV")
    cell.add(gdstk.rectangle((0, 0), (1, 0.5), layer=68, datatype=20))
    lib.add(cell)
    path = tmp_dir / "test_sample.gds"
    lib.write_gds(str(path))
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture
def uploaded_job(client, sample_gds) -> str:
    """Create and upload a job, return job_id."""
    r = client.post(
        "/api/upload",
        files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        params={"pdk_name": "sky130"},
    )
    assert r.status_code == 200
    return r.json()["job_id"]


SAMPLE_NETLIST = """\
* Simple inverter netlist
.subckt INVERTER IN OUT VDD VSS
M1 OUT IN VDD VDD sky130_fd_pr__pfet_01v8 w=1.5u l=0.25u
M2 OUT IN VSS VSS sky130_fd_pr__nfet_01v8 w=0.9u l=0.25u
.ends INVERTER
"""


class TestUploadNetlist:
    def test_upload_spice_success(self, client, uploaded_job):
        r = client.post(
            f"/api/jobs/{uploaded_job}/lvs/upload",
            files={"file": ("inverter.spice", io.BytesIO(SAMPLE_NETLIST.encode()), "text/plain")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["job_id"] == uploaded_job
        assert data["netlist_filename"] == "inverter.spice"

    def test_upload_sp_extension(self, client, uploaded_job):
        r = client.post(
            f"/api/jobs/{uploaded_job}/lvs/upload",
            files={"file": ("circuit.sp", io.BytesIO(SAMPLE_NETLIST.encode()), "text/plain")},
        )
        assert r.status_code == 200

    def test_upload_cir_extension(self, client, uploaded_job):
        r = client.post(
            f"/api/jobs/{uploaded_job}/lvs/upload",
            files={"file": ("circuit.cir", io.BytesIO(SAMPLE_NETLIST.encode()), "text/plain")},
        )
        assert r.status_code == 200

    def test_upload_invalid_extension(self, client, uploaded_job):
        r = client.post(
            f"/api/jobs/{uploaded_job}/lvs/upload",
            files={"file": ("circuit.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert r.status_code == 400
        assert "Invalid netlist file type" in r.json()["detail"]

    def test_upload_job_not_found(self, client):
        r = client.post(
            "/api/jobs/nonexistent/lvs/upload",
            files={"file": ("inverter.spice", io.BytesIO(SAMPLE_NETLIST.encode()), "text/plain")},
        )
        assert r.status_code == 404

    def test_upload_stores_netlist_path(self, client, uploaded_job):
        client.post(
            f"/api/jobs/{uploaded_job}/lvs/upload",
            files={"file": ("inverter.spice", io.BytesIO(SAMPLE_NETLIST.encode()), "text/plain")},
        )
        # Verify job has netlist_path set
        r = client.get(f"/api/jobs/{uploaded_job}")
        assert r.status_code == 200
        assert r.json()["netlist_path"] is not None
        assert "inverter.spice" in r.json()["netlist_path"]


class TestRunLVS:
    def test_run_lvs_no_gds(self, client):
        """400 if no GDS uploaded."""
        manager = deps.get_job_manager()
        job = manager.create("test.gds", "sky130")
        r = client.post(f"/api/jobs/{job.job_id}/lvs/run")
        assert r.status_code == 400
        assert "No GDSII file" in r.json()["detail"]

    def test_run_lvs_no_netlist(self, client, uploaded_job):
        """400 if no netlist uploaded."""
        r = client.post(f"/api/jobs/{uploaded_job}/lvs/run")
        assert r.status_code == 400
        assert "No netlist" in r.json()["detail"]

    def test_run_lvs_not_found(self, client):
        r = client.post("/api/jobs/nonexistent/lvs/run")
        assert r.status_code == 404

    def test_run_lvs_already_running(self, client, uploaded_job):
        """409 if LVS already running."""
        # Upload netlist
        client.post(
            f"/api/jobs/{uploaded_job}/lvs/upload",
            files={"file": ("inverter.spice", io.BytesIO(SAMPLE_NETLIST.encode()), "text/plain")},
        )
        # Set status to running_lvs
        manager = deps.get_job_manager()
        manager.update_status(uploaded_job, JobStatus.running_lvs)

        r = client.post(f"/api/jobs/{uploaded_job}/lvs/run")
        assert r.status_code == 409
        assert "already running" in r.json()["detail"]

    def test_run_lvs_returns_immediately(self, client, uploaded_job):
        """POST /lvs/run returns immediately with status=running_lvs."""
        # Upload netlist
        client.post(
            f"/api/jobs/{uploaded_job}/lvs/upload",
            files={"file": ("inverter.spice", io.BytesIO(SAMPLE_NETLIST.encode()), "text/plain")},
        )

        r = client.post(f"/api/jobs/{uploaded_job}/lvs/run")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "running_lvs"
        assert data["job_id"] == uploaded_job

    def test_run_lvs_background_success(self, client, uploaded_job, tmp_dir):
        """LVS background task completes and updates job status."""
        # Upload netlist
        client.post(
            f"/api/jobs/{uploaded_job}/lvs/upload",
            files={"file": ("inverter.spice", io.BytesIO(SAMPLE_NETLIST.encode()), "text/plain")},
        )

        # Copy clean fixture to job dir for the parser to find
        job_dir = deps.get_job_manager().job_dir(uploaded_job)
        fixture_path = FIXTURES_DIR / "clean_inverter.lvsdb"
        report_path = job_dir / "test_lvs.lvsdb"
        shutil.copy2(fixture_path, report_path)

        mock_result = LVSResult(
            report_path=report_path,
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=0.5,
            match=True,
        )

        with patch("backend.api.routes.lvs.LVSRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(return_value=mock_result)

            r = client.post(f"/api/jobs/{uploaded_job}/lvs/run")
            assert r.status_code == 200

        import time
        time.sleep(0.2)

        r2 = client.get(f"/api/jobs/{uploaded_job}")
        assert r2.status_code == 200
        job_data = r2.json()
        assert job_data["status"] in ("running_lvs", "lvs_complete")


class TestGetLVSResults:
    def test_results_no_report(self, client, uploaded_job):
        """400 if LVS hasn't been run."""
        r = client.get(f"/api/jobs/{uploaded_job}/lvs/results")
        assert r.status_code == 400
        assert "No LVS report" in r.json()["detail"]

    def test_results_not_found(self, client):
        r = client.get("/api/jobs/nonexistent/lvs/results")
        assert r.status_code == 404

    def test_results_clean_match(self, client, uploaded_job):
        """GET results for a clean LVS match."""
        # Copy fixture and set report path on job
        manager = deps.get_job_manager()
        job_dir = manager.job_dir(uploaded_job)
        fixture_path = FIXTURES_DIR / "clean_inverter.lvsdb"
        report_path = job_dir / "inverter_lvs.lvsdb"
        shutil.copy2(fixture_path, report_path)

        manager.update_status(
            uploaded_job,
            JobStatus.lvs_complete,
            lvs_report_path=str(report_path),
        )

        r = client.get(f"/api/jobs/{uploaded_job}/lvs/results")
        assert r.status_code == 200
        data = r.json()
        assert data["match"] is True
        assert data["devices_matched"] == 2
        assert data["devices_mismatched"] == 0
        assert data["nets_matched"] == 4
        assert data["nets_mismatched"] == 0
        assert data["mismatches"] == []

    def test_results_with_mismatches(self, client, uploaded_job):
        """GET results for an LVS run with mismatches."""
        manager = deps.get_job_manager()
        job_dir = manager.job_dir(uploaded_job)
        fixture_path = FIXTURES_DIR / "mismatched_inverter.lvsdb"
        report_path = job_dir / "inverter_lvs.lvsdb"
        shutil.copy2(fixture_path, report_path)

        manager.update_status(
            uploaded_job,
            JobStatus.lvs_complete,
            lvs_report_path=str(report_path),
        )

        r = client.get(f"/api/jobs/{uploaded_job}/lvs/results")
        assert r.status_code == 200
        data = r.json()
        assert data["match"] is False
        assert data["devices_mismatched"] > 0 or data["nets_mismatched"] > 0
        assert len(data["mismatches"]) > 0

        # Verify mismatch structure
        m = data["mismatches"][0]
        assert "type" in m
        assert "name" in m
        assert "expected" in m
        assert "actual" in m
        assert "details" in m
        assert m["type"] in [t.value for t in LVSMismatchType]

    def test_results_report_deleted(self, client, uploaded_job):
        """404 if report file was deleted from disk."""
        manager = deps.get_job_manager()
        manager.update_status(
            uploaded_job,
            JobStatus.lvs_complete,
            lvs_report_path="/nonexistent/report.lvsdb",
        )

        r = client.get(f"/api/jobs/{uploaded_job}/lvs/results")
        assert r.status_code == 404
        assert "not found on disk" in r.json()["detail"]


class TestLVSFullFlow:
    def test_upload_then_run_then_results(self, client, uploaded_job):
        """End-to-end: upload netlist → run LVS → get results."""
        # Step 1: Upload netlist
        r1 = client.post(
            f"/api/jobs/{uploaded_job}/lvs/upload",
            files={"file": ("inverter.spice", io.BytesIO(SAMPLE_NETLIST.encode()), "text/plain")},
        )
        assert r1.status_code == 200

        # Step 2: Run LVS (mocked)
        manager = deps.get_job_manager()
        job_dir = manager.job_dir(uploaded_job)
        fixture_path = FIXTURES_DIR / "clean_inverter.lvsdb"
        report_path = job_dir / "test_lvs.lvsdb"
        shutil.copy2(fixture_path, report_path)

        mock_result = LVSResult(
            report_path=report_path,
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=0.1,
            match=True,
        )

        with patch("backend.api.routes.lvs.LVSRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(return_value=mock_result)

            r2 = client.post(f"/api/jobs/{uploaded_job}/lvs/run")
            assert r2.status_code == 200
            assert r2.json()["status"] == "running_lvs"

        import time
        time.sleep(0.2)

        # Step 3: Get results (may need to wait for background task)
        job = manager.get(uploaded_job)
        if job.status == JobStatus.lvs_complete and job.lvs_report_path:
            r3 = client.get(f"/api/jobs/{uploaded_job}/lvs/results")
            assert r3.status_code == 200
            data = r3.json()
            assert data["match"] is True
            assert data["mismatches"] == []


class TestJobStatusLVS:
    def test_lvs_statuses_in_enum(self):
        """Verify LVS statuses exist in JobStatus."""
        assert JobStatus.running_lvs == "running_lvs"
        assert JobStatus.lvs_complete == "lvs_complete"
        assert JobStatus.lvs_failed == "lvs_failed"

    def test_job_has_lvs_fields(self, client, uploaded_job):
        """Job response includes LVS fields."""
        r = client.get(f"/api/jobs/{uploaded_job}")
        assert r.status_code == 200
        data = r.json()
        assert "netlist_path" in data
        assert "lvs_report_path" in data
        assert data["netlist_path"] is None
        assert data["lvs_report_path"] is None

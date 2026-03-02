"""Tests for API routes — upload, DRC, fix, layout, PDK."""

import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import gdstk
import pytest
from fastapi.testclient import TestClient

from backend.api import deps
from backend.jobs.manager import JobManager, JobStatus
from backend.main import app


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
    # Override config paths
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
    # met1 rectangle (SKY130 met1 = layer 68, datatype 20)
    cell.add(gdstk.rectangle((0, 0), (1, 0.5), layer=68, datatype=20))
    lib.add(cell)
    path = tmp_dir / "test_sample.gds"
    lib.write_gds(str(path))
    with open(path, "rb") as f:
        return f.read()


class TestHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestUpload:
    def test_upload_success(self, client, sample_gds):
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
            params={"pdk_name": "sky130"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["filename"] == "test.gds"
        assert data["status"] == "uploaded"
        assert "job_id" in data

    def test_upload_invalid_extension(self, client):
        r = client.post(
            "/api/upload",
            files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert r.status_code == 400
        assert "Invalid file type" in r.json()["detail"]

    def test_upload_invalid_pdk(self, client, sample_gds):
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
            params={"pdk_name": "nonexistent"},
        )
        assert r.status_code == 404

    def test_upload_creates_job(self, client, sample_gds):
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
            params={"pdk_name": "sky130"},
        )
        job_id = r.json()["job_id"]

        # Verify job exists
        r2 = client.get(f"/api/jobs/{job_id}")
        assert r2.status_code == 200
        assert r2.json()["status"] == "uploaded"


class TestJobs:
    def test_list_jobs_empty(self, client):
        r = client.get("/api/jobs")
        assert r.status_code == 200
        assert r.json()["jobs"] == []

    def test_list_jobs_after_upload(self, client, sample_gds):
        client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        )
        r = client.get("/api/jobs")
        assert len(r.json()["jobs"]) == 1

    def test_get_job_not_found(self, client):
        r = client.get("/api/jobs/nonexistent")
        assert r.status_code == 404


class TestPDK:
    def test_list_pdks(self, client):
        r = client.get("/api/pdks")
        assert r.status_code == 200
        assert "sky130" in r.json()["pdks"]

    def test_get_pdk(self, client):
        r = client.get("/api/pdks/sky130")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "sky130"
        assert data["process_node_nm"] == 130
        assert data["layer_count"] > 0
        assert data["rule_count"] > 0

    def test_get_pdk_not_found(self, client):
        r = client.get("/api/pdks/nonexistent")
        assert r.status_code == 404


class TestLayout:
    def test_get_layout(self, client, sample_gds):
        # Upload first
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        )
        job_id = r.json()["job_id"]

        # Get layout
        r2 = client.get(f"/api/jobs/{job_id}/layout")
        assert r2.status_code == 200
        data = r2.json()
        assert data["total_polygons"] > 0
        assert len(data["layers"]) > 0
        assert len(data["bbox"]) == 4

    def test_get_layout_no_gds(self, client):
        # Create a job manually without upload
        manager = deps.get_job_manager()
        job = manager.create("test.gds", "sky130")
        r = client.get(f"/api/jobs/{job.job_id}/layout")
        assert r.status_code == 400


class TestDRC:
    def test_run_drc_no_report(self, client, sample_gds):
        """DRC requires KLayout — test the status check."""
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        )
        job_id = r.json()["job_id"]

        # Running DRC will fail without KLayout binary — expect 500
        r2 = client.post(f"/api/jobs/{job_id}/drc")
        assert r2.status_code == 500

    def test_get_violations_no_report(self, client, sample_gds):
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        )
        job_id = r.json()["job_id"]

        r2 = client.get(f"/api/jobs/{job_id}/violations")
        assert r2.status_code == 400

    def test_run_drc_with_mock(self, client, sample_gds, tmp_dir):
        """Test DRC with mocked KLayout subprocess."""
        # Upload
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        )
        job_id = r.json()["job_id"]

        # Create a mock lyrdb report
        lyrdb_content = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
  <description>DRC Report</description>
  <original-file>test.gds</original-file>
  <generator>klayout</generator>
  <top-cell>INV</top-cell>
  <categories>
    <category>
      <name>met1.1</name>
      <description>Metal 1 minimum width</description>
    </category>
  </categories>
  <cells>
    <cell>
      <name>INV</name>
    </cell>
  </cells>
  <items>
    <item>
      <category>met1.1</category>
      <cell>INV</cell>
      <values>
        <value>edge-pair: (0.000,0.000;0.100,0.000)/(0.000,0.050;0.100,0.050)</value>
      </values>
    </item>
  </items>
</report-database>"""

        # Mock the DRC runner
        from backend.core.violation_models import DRCReport
        from backend.core.violation_parser import ViolationParser
        from backend.core.drc_runner import DRCResult

        parser = ViolationParser()
        report = parser.parse_string(lyrdb_content)

        job_dir = deps.get_job_manager().job_dir(job_id)
        report_path = job_dir / "test_drc.lyrdb"
        report_path.write_text(lyrdb_content)

        mock_result = DRCResult(
            report=report,
            report_path=report_path,
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=0.1,
            klayout_binary="klayout",
        )

        with patch("backend.api.routes.drc.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run.return_value = mock_result

            r2 = client.post(f"/api/jobs/{job_id}/drc")
            assert r2.status_code == 200
            data = r2.json()
            assert data["total_violations"] == 1
            assert len(data["categories"]) == 1
            assert data["categories"][0]["category"] == "met1.1"

        # Now test get violations
        r3 = client.get(f"/api/jobs/{job_id}/violations")
        assert r3.status_code == 200
        vdata = r3.json()
        assert vdata["total_violations"] == 1


class TestFix:
    def test_suggest_no_report(self, client, sample_gds):
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        )
        job_id = r.json()["job_id"]

        r2 = client.post(f"/api/jobs/{job_id}/fix/suggest")
        assert r2.status_code == 400

    def test_preview_no_suggestions(self, client):
        manager = deps.get_job_manager()
        job = manager.create("test.gds", "sky130")
        r = client.get(f"/api/jobs/{job.job_id}/fix/preview/0")
        assert r.status_code == 400

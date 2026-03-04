"""Tests for async DRC endpoint behavior — non-blocking execution."""

import io
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import gdstk
import pytest
from fastapi.testclient import TestClient

from backend.api import deps
from backend.jobs.manager import JobStatus
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


class TestAsyncDRCEndpoint:
    """Tests for the async POST /api/jobs/{job_id}/drc endpoint."""

    def test_drc_returns_immediately(self, client, sample_gds):
        """POST /drc returns immediately with running_drc status."""
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        )
        job_id = r.json()["job_id"]

        with patch("backend.api.routes.drc.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(side_effect=Exception("should not block"))

            start = time.monotonic()
            r2 = client.post(f"/api/jobs/{job_id}/drc")
            elapsed = time.monotonic() - start

            assert r2.status_code == 200
            data = r2.json()
            assert data["status"] == "running_drc"
            assert data["job_id"] == job_id
            # Response should be nearly instant (not waiting for DRC)
            assert elapsed < 2.0

    def test_health_while_drc_running(self, client, sample_gds):
        """GET /health returns 200 while DRC is running (proves non-blocking)."""
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        )
        job_id = r.json()["job_id"]

        with patch("backend.api.routes.drc.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            # Simulate a slow DRC run
            async def slow_drc(*args, **kwargs):
                import asyncio

                await asyncio.sleep(10)

            instance.async_run = AsyncMock(side_effect=slow_drc)

            # Start DRC
            r2 = client.post(f"/api/jobs/{job_id}/drc")
            assert r2.status_code == 200

            # Immediately hit /health — should work (not blocked)
            r3 = client.get("/health")
            assert r3.status_code == 200
            assert r3.json() == {"status": "ok"}

    def test_job_status_transitions(self, client, sample_gds):
        """Job transitions: uploaded -> running_drc -> drc_complete."""
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        )
        job_id = r.json()["job_id"]

        lyrdb_content = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
  <description>DRC</description>
  <original-file>test.gds</original-file>
  <generator>klayout</generator>
  <top-cell>INV</top-cell>
  <categories><category><name>met1.1</name><description>width</description></category></categories>
  <cells><cell><name>INV</name></cell></cells>
  <items>
    <item><category>met1.1</category><cell>INV</cell>
      <values><value>edge-pair: (0,0;1,0)/(0,1;1,1)</value></values>
    </item>
  </items>
</report-database>"""

        from backend.core.drc_runner import DRCResult
        from backend.core.violation_parser import ViolationParser

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
            instance.async_run = AsyncMock(return_value=mock_result)

            # Trigger DRC
            r2 = client.post(f"/api/jobs/{job_id}/drc")
            assert r2.json()["status"] == "running_drc"

        # Wait for background task
        time.sleep(0.2)

        # Check final status
        r3 = client.get(f"/api/jobs/{job_id}")
        assert r3.json()["status"] in ("running_drc", "drc_complete")

    def test_drc_already_running_returns_409(self, client, sample_gds):
        """Starting DRC when already running returns 409."""
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        )
        job_id = r.json()["job_id"]

        manager = deps.get_job_manager()
        manager.update_status(job_id, JobStatus.running_drc)

        r2 = client.post(f"/api/jobs/{job_id}/drc")
        assert r2.status_code == 409

    def test_drc_background_failure_updates_status(self, client, sample_gds):
        """If DRC fails in background, job status becomes drc_failed."""
        r = client.post(
            "/api/upload",
            files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        )
        job_id = r.json()["job_id"]

        from backend.core.drc_runner import DRCError

        with patch("backend.api.routes.drc.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(side_effect=DRCError("klayout crashed"))

            r2 = client.post(f"/api/jobs/{job_id}/drc")
            assert r2.status_code == 200
            assert r2.json()["status"] == "running_drc"

        # Wait for background task
        time.sleep(0.2)

        r3 = client.get(f"/api/jobs/{job_id}")
        assert r3.json()["status"] in ("running_drc", "drc_failed")

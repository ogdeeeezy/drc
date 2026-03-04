"""Extended API route tests — covers uncovered lines in drc.py, export.py, fix.py,
layout.py, lvs.py, and upload.py.

Supplements test_api_routes.py and test_api_lvs.py with edge cases
and error paths to improve coverage.
"""

import io
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import gdstk
import pytest
from fastapi.testclient import TestClient

from backend.api import deps
from backend.core.drc_runner import DRCResult
from backend.core.violation_models import (
    DRCReport,
    EdgePair,
    GeometryType,
    Violation,
    ViolationGeometry,
)
from backend.fix.engine import FixEngineResult
from backend.fix.fix_models import FixConfidence, FixSuggestion, PolygonDelta
from backend.jobs.manager import Job, JobStatus
from backend.main import app


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_singletons():
    deps.reset_deps()
    yield
    deps.reset_deps()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def client(tmp_dir):
    import backend.config as cfg

    original_jobs = cfg.JOBS_DIR
    original_uploads = cfg.UPLOAD_DIR
    original_pcells = cfg.PCELLS_DIR
    cfg.JOBS_DIR = tmp_dir / "jobs"
    cfg.UPLOAD_DIR = tmp_dir / "uploads"
    cfg.PCELLS_DIR = tmp_dir / "pcells"
    cfg.JOBS_DIR.mkdir()
    cfg.UPLOAD_DIR.mkdir()
    cfg.PCELLS_DIR.mkdir()

    with TestClient(app) as c:
        yield c

    cfg.JOBS_DIR = original_jobs
    cfg.UPLOAD_DIR = original_uploads
    cfg.PCELLS_DIR = original_pcells


@pytest.fixture
def sample_gds(tmp_dir) -> bytes:
    lib = gdstk.Library("test")
    cell = gdstk.Cell("TOP")
    cell.add(gdstk.rectangle((0, 0), (1, 0.5), layer=68, datatype=20))
    lib.add(cell)
    path = tmp_dir / "test_sample.gds"
    lib.write_gds(str(path))
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture
def uploaded_job(client, sample_gds) -> str:
    r = client.post(
        "/api/upload",
        files={"file": ("test.gds", io.BytesIO(sample_gds), "application/octet-stream")},
        params={"pdk_name": "sky130"},
    )
    assert r.status_code == 200
    return r.json()["job_id"]


LYRDB_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
  <description>DRC Report</description>
  <original-file>test.gds</original-file>
  <generator>klayout</generator>
  <top-cell>TOP</top-cell>
  <categories>
    <category>
      <name>met1.1</name>
      <description>Metal 1 minimum width: 0.140um</description>
    </category>
  </categories>
  <cells>
    <cell>
      <name>TOP</name>
    </cell>
  </cells>
  <items>
    <item>
      <category>met1.1</category>
      <cell>TOP</cell>
      <values>
        <value>edge-pair: (0.000,0.000;0.100,0.000)/(0.000,0.050;0.100,0.050)</value>
      </values>
    </item>
  </items>
</report-database>"""


def _setup_drc_complete(client, job_id):
    """Set up a job in drc_complete state with a real report file."""
    manager = deps.get_job_manager()
    job_dir = manager.job_dir(job_id)
    report_path = job_dir / "test_drc.lyrdb"
    report_path.write_text(LYRDB_TEMPLATE)
    manager.update_status(
        job_id,
        JobStatus.drc_complete,
        report_path=str(report_path),
        top_cell="TOP",
        total_violations=1,
    )
    return report_path


# ── DRC route tests ──────────────────────────────────────────────────────


class TestDRCBackground:
    """Tests for _run_drc_background and edge cases in run_drc."""

    def test_run_drc_job_not_found(self, client):
        r = client.post("/api/jobs/nonexistent/drc")
        assert r.status_code == 404

    def test_run_drc_no_gds(self, client):
        manager = deps.get_job_manager()
        job = manager.create("test.gds", "sky130")
        r = client.post(f"/api/jobs/{job.job_id}/drc")
        assert r.status_code == 400
        assert "No GDSII" in r.json()["detail"]

    def test_run_drc_re_run_after_fixes(self, client, uploaded_job):
        """Re-DRC from fixes_applied increments iteration."""
        manager = deps.get_job_manager()
        _setup_drc_complete(client, uploaded_job)
        manager.update_status(uploaded_job, JobStatus.fixes_applied)

        r = client.post(f"/api/jobs/{uploaded_job}/drc")
        assert r.status_code == 200
        assert r.json()["status"] == "running_drc"

        # Check iteration was incremented
        job = manager.get(uploaded_job)
        assert job.iteration == 2

    def test_background_pdk_not_found(self, client, uploaded_job):
        """Background task handles FileNotFoundError from PDK registry."""
        import asyncio

        from backend.api.routes.drc import _run_drc_background

        manager = deps.get_job_manager()
        job = manager.get(uploaded_job)
        job_dir = str(manager.job_dir(uploaded_job))

        # Run background task with invalid PDK
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            _run_drc_background(uploaded_job, job.gds_path, "nonexistent_pdk", None, job_dir)
        )
        loop.close()

        # Job should be marked drc_failed
        updated = manager.get(uploaded_job)
        assert updated.status == JobStatus.drc_failed

    def test_background_drc_error(self, client, uploaded_job):
        """Background task handles DRCError."""
        import asyncio

        from backend.api.routes.drc import _run_drc_background
        from backend.core.drc_runner import DRCError

        manager = deps.get_job_manager()
        job = manager.get(uploaded_job)
        job_dir = str(manager.job_dir(uploaded_job))

        with patch("backend.api.routes.drc.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(side_effect=DRCError("klayout crashed"))

            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                _run_drc_background(uploaded_job, job.gds_path, "sky130", None, job_dir)
            )
            loop.close()

        updated = manager.get(uploaded_job)
        assert updated.status == JobStatus.drc_failed
        assert "klayout crashed" in updated.error

    def test_background_file_not_found(self, client, uploaded_job):
        """Background task handles FileNotFoundError during DRC run."""
        import asyncio

        from backend.api.routes.drc import _run_drc_background

        manager = deps.get_job_manager()
        job = manager.get(uploaded_job)
        job_dir = str(manager.job_dir(uploaded_job))

        with patch("backend.api.routes.drc.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(side_effect=FileNotFoundError("gds missing"))

            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                _run_drc_background(uploaded_job, job.gds_path, "sky130", None, job_dir)
            )
            loop.close()

        updated = manager.get(uploaded_job)
        assert updated.status == JobStatus.drc_failed

    def test_background_success_updates_job(self, client, uploaded_job):
        """Background task updates job to drc_complete on success."""
        import asyncio

        from backend.api.routes.drc import _run_drc_background
        from backend.core.violation_parser import ViolationParser

        manager = deps.get_job_manager()
        job = manager.get(uploaded_job)
        job_dir = manager.job_dir(uploaded_job)

        report_path = job_dir / "test_drc.lyrdb"
        report_path.write_text(LYRDB_TEMPLATE)

        parser = ViolationParser()
        report = parser.parse_string(LYRDB_TEMPLATE)

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

            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                _run_drc_background(
                    uploaded_job, job.gds_path, "sky130", None, str(job_dir)
                )
            )
            loop.close()

        updated = manager.get(uploaded_job)
        assert updated.status == JobStatus.drc_complete
        assert updated.total_violations == 1
        assert updated.top_cell == "TOP"


class TestGetViolations:
    """Tests for GET /violations endpoint edge cases."""

    def test_violations_not_found(self, client):
        r = client.get("/api/jobs/nonexistent/violations")
        assert r.status_code == 404

    def test_violations_report_deleted(self, client, uploaded_job):
        """404 when report file is deleted from disk."""
        manager = deps.get_job_manager()
        manager.update_status(
            uploaded_job,
            JobStatus.drc_complete,
            report_path="/nonexistent/report.lyrdb",
        )
        r = client.get(f"/api/jobs/{uploaded_job}/violations")
        assert r.status_code == 404
        assert "not found on disk" in r.json()["detail"]

    def test_violations_with_category_filter(self, client, uploaded_job):
        """GET /violations?category= filters results."""
        _setup_drc_complete(client, uploaded_job)
        r = client.get(f"/api/jobs/{uploaded_job}/violations?category=met1.1")
        assert r.status_code == 200
        data = r.json()
        assert data["total_violations"] == 1
        for v in data["violations"]:
            assert v["category"] == "met1.1"

    def test_violations_with_nonexistent_category_filter(self, client, uploaded_job):
        """Filter with no matching category returns 0 violations."""
        _setup_drc_complete(client, uploaded_job)
        r = client.get(f"/api/jobs/{uploaded_job}/violations?category=nonexistent")
        assert r.status_code == 200
        assert r.json()["total_violations"] == 0

    def test_violations_full_response_structure(self, client, uploaded_job):
        """Verify complete violation response including geometries."""
        _setup_drc_complete(client, uploaded_job)
        r = client.get(f"/api/jobs/{uploaded_job}/violations")
        assert r.status_code == 200
        data = r.json()
        v = data["violations"][0]
        assert "category" in v
        assert "description" in v
        assert "cell_name" in v
        assert "geometries" in v
        assert isinstance(v["bbox"], list)
        assert len(v["bbox"]) == 4


# ── Export route tests ────────────────────────────────────────────────────


class TestExportRoute:
    def test_export_json(self, client, uploaded_job):
        _setup_drc_complete(client, uploaded_job)
        r = client.get(f"/api/jobs/{uploaded_job}/report/json")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert "Content-Disposition" in r.headers

    def test_export_csv(self, client, uploaded_job):
        _setup_drc_complete(client, uploaded_job)
        r = client.get(f"/api/jobs/{uploaded_job}/report/csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")

    def test_export_html(self, client, uploaded_job):
        _setup_drc_complete(client, uploaded_job)
        r = client.get(f"/api/jobs/{uploaded_job}/report/html")
        assert r.status_code == 200
        body = r.text
        assert "<html" in body
        assert "DRC Report" in body

    def test_export_unsupported_format(self, client, uploaded_job):
        r = client.get(f"/api/jobs/{uploaded_job}/report/pdf")
        assert r.status_code == 400
        assert "Unsupported format" in r.json()["detail"]

    def test_export_job_not_found(self, client):
        r = client.get("/api/jobs/nonexistent/report/json")
        assert r.status_code == 404

    def test_export_no_report(self, client, uploaded_job):
        r = client.get(f"/api/jobs/{uploaded_job}/report/json")
        assert r.status_code == 400

    def test_export_report_deleted(self, client, uploaded_job):
        manager = deps.get_job_manager()
        manager.update_status(
            uploaded_job,
            JobStatus.drc_complete,
            report_path="/nonexistent/report.lyrdb",
        )
        r = client.get(f"/api/jobs/{uploaded_job}/report/json")
        assert r.status_code == 404


# ── Fix route tests ──────────────────────────────────────────────────────


class TestFixSuggest:
    def test_suggest_job_not_found(self, client):
        r = client.post("/api/jobs/nonexistent/fix/suggest")
        assert r.status_code == 404

    def test_suggest_no_gds(self, client):
        """400 if job has report but no GDS."""
        manager = deps.get_job_manager()
        job = manager.create("test.gds", "sky130")
        job_dir = manager.job_dir(job.job_id)
        report_path = job_dir / "test_drc.lyrdb"
        report_path.write_text(LYRDB_TEMPLATE)
        manager.update_status(
            job.job_id,
            JobStatus.drc_complete,
            report_path=str(report_path),
        )
        # Note: gds_path is still None
        r = client.post(f"/api/jobs/{job.job_id}/fix/suggest")
        assert r.status_code == 400
        assert "No GDSII" in r.json()["detail"]

    def test_suggest_gds_deleted(self, client, uploaded_job):
        """404 if GDS file was deleted from disk."""
        _setup_drc_complete(client, uploaded_job)
        # Delete the GDS file
        manager = deps.get_job_manager()
        job = manager.get(uploaded_job)
        Path(job.gds_path).unlink()

        r = client.post(f"/api/jobs/{uploaded_job}/fix/suggest")
        assert r.status_code == 404
        assert "GDSII file not found" in r.json()["detail"]

    def test_suggest_report_deleted(self, client, uploaded_job):
        """404 if DRC report was deleted from disk."""
        report_path = _setup_drc_complete(client, uploaded_job)
        report_path.unlink()

        r = client.post(f"/api/jobs/{uploaded_job}/fix/suggest")
        assert r.status_code == 404
        assert "report file not found" in r.json()["detail"]

    def test_suggest_success(self, client, uploaded_job):
        """Successful fix suggestion with mocked engine."""
        _setup_drc_complete(client, uploaded_job)

        suggestion = FixSuggestion(
            violation_category="met1.1",
            rule_type="min_width",
            description="Widen met1 polygon",
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=68,
                    gds_datatype=20,
                    original_points=[(0.0, 0.0), (1.0, 0.0), (1.0, 0.5), (0.0, 0.5)],
                    modified_points=[(0.0, 0.0), (1.0, 0.0), (1.0, 0.6), (0.0, 0.6)],
                )
            ],
            confidence=FixConfidence.high,
        )
        mock_result = FixEngineResult(suggestions=[suggestion], unfixable=[])

        with patch("backend.api.routes.fix.FixEngine") as MockEngine:
            MockEngine.return_value.suggest_fixes.return_value = mock_result
            r = client.post(f"/api/jobs/{uploaded_job}/fix/suggest")

        assert r.status_code == 200
        data = r.json()
        assert data["total_suggestions"] == 1
        assert data["fixable_count"] == 1
        assert data["suggestions"][0]["confidence"] == "high"
        assert data["suggestions"][0]["rule_type"] == "min_width"


class TestFixPreview:
    def _setup_fix_cache(self, job_id):
        """Populate fix cache with a mock result."""
        from backend.api.routes.fix import _fix_results_cache

        suggestion = FixSuggestion(
            violation_category="met1.1",
            rule_type="min_width",
            description="Widen met1 polygon",
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=68,
                    gds_datatype=20,
                    original_points=[(0.0, 0.0), (1.0, 0.0), (1.0, 0.5), (0.0, 0.5)],
                    modified_points=[(0.0, 0.0), (1.0, 0.0), (1.0, 0.6), (0.0, 0.6)],
                )
            ],
            confidence=FixConfidence.high,
        )
        result = FixEngineResult(suggestions=[suggestion])
        _fix_results_cache[job_id] = result
        return result

    def test_preview_success(self, client, uploaded_job):
        self._setup_fix_cache(uploaded_job)
        r = client.get(f"/api/jobs/{uploaded_job}/fix/preview/0")
        assert r.status_code == 200
        data = r.json()
        assert data["suggestion_index"] == 0
        assert data["confidence"] == "high"
        assert len(data["deltas"]) == 1
        assert data["deltas"][0]["cell_name"] == "TOP"

    def test_preview_out_of_range(self, client, uploaded_job):
        self._setup_fix_cache(uploaded_job)
        r = client.get(f"/api/jobs/{uploaded_job}/fix/preview/99")
        assert r.status_code == 404
        assert "out of range" in r.json()["detail"]

    def test_preview_negative_index(self, client, uploaded_job):
        self._setup_fix_cache(uploaded_job)
        r = client.get(f"/api/jobs/{uploaded_job}/fix/preview/-1")
        assert r.status_code == 404


class TestFixApply:
    def _setup_fix_cache(self, job_id):
        from backend.api.routes.fix import _fix_results_cache

        suggestion = FixSuggestion(
            violation_category="met1.1",
            rule_type="min_width",
            description="Widen met1 polygon",
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=68,
                    gds_datatype=20,
                    original_points=[(0.0, 0.0), (1.0, 0.0), (1.0, 0.5), (0.0, 0.5)],
                    modified_points=[(0.0, 0.0), (1.0, 0.0), (1.0, 0.6), (0.0, 0.6)],
                )
            ],
            confidence=FixConfidence.high,
        )
        result = FixEngineResult(suggestions=[suggestion])
        _fix_results_cache[job_id] = result

    def test_apply_job_not_found(self, client):
        r = client.post(
            "/api/jobs/nonexistent/fix/apply",
            json={"suggestion_indices": [0]},
        )
        assert r.status_code == 404

    def test_apply_no_suggestions_cached(self, client, uploaded_job):
        r = client.post(
            f"/api/jobs/{uploaded_job}/fix/apply",
            json={"suggestion_indices": [0]},
        )
        assert r.status_code == 400
        assert "No fix suggestions cached" in r.json()["detail"]

    def test_apply_no_gds(self, client):
        manager = deps.get_job_manager()
        job = manager.create("test.gds", "sky130")
        from backend.api.routes.fix import _fix_results_cache

        _fix_results_cache[job.job_id] = FixEngineResult(
            suggestions=[
                FixSuggestion(
                    violation_category="x", rule_type="y", description="z"
                )
            ]
        )
        r = client.post(
            f"/api/jobs/{job.job_id}/fix/apply",
            json={"suggestion_indices": [0]},
        )
        assert r.status_code == 400
        assert "No GDSII" in r.json()["detail"]

    def test_apply_index_out_of_range(self, client, uploaded_job):
        self._setup_fix_cache(uploaded_job)
        r = client.post(
            f"/api/jobs/{uploaded_job}/fix/apply",
            json={"suggestion_indices": [99]},
        )
        assert r.status_code == 400
        assert "out of range" in r.json()["detail"]

    def test_apply_success(self, client, uploaded_job):
        self._setup_fix_cache(uploaded_job)
        r = client.post(
            f"/api/jobs/{uploaded_job}/fix/apply",
            json={"suggestion_indices": [0]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "fixes_applied"
        assert data["total_requested"] == 1

    def test_apply_gds_deleted(self, client, uploaded_job):
        """404 when GDS was deleted after suggest."""
        self._setup_fix_cache(uploaded_job)
        manager = deps.get_job_manager()
        job = manager.get(uploaded_job)
        Path(job.gds_path).unlink()

        r = client.post(
            f"/api/jobs/{uploaded_job}/fix/apply",
            json={"suggestion_indices": [0]},
        )
        assert r.status_code == 404
        assert "GDSII file not found" in r.json()["detail"]


class TestFixApplyAndRecheck:
    def _setup_fix_cache(self, job_id):
        from backend.api.routes.fix import _fix_results_cache

        suggestion = FixSuggestion(
            violation_category="met1.1",
            rule_type="min_width",
            description="Widen met1 polygon",
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=68,
                    gds_datatype=20,
                    original_points=[(0.0, 0.0), (1.0, 0.0), (1.0, 0.5), (0.0, 0.5)],
                    modified_points=[(0.0, 0.0), (1.0, 0.0), (1.0, 0.6), (0.0, 0.6)],
                )
            ],
            confidence=FixConfidence.high,
        )
        result = FixEngineResult(suggestions=[suggestion])
        _fix_results_cache[job_id] = result

    def test_apply_recheck_job_not_found(self, client):
        r = client.post(
            "/api/jobs/nonexistent/fix/apply-and-recheck",
            json={"suggestion_indices": [0]},
        )
        assert r.status_code == 404

    def test_apply_recheck_no_cache(self, client, uploaded_job):
        r = client.post(
            f"/api/jobs/{uploaded_job}/fix/apply-and-recheck",
            json={"suggestion_indices": [0]},
        )
        assert r.status_code == 400

    def test_apply_recheck_no_gds(self, client):
        manager = deps.get_job_manager()
        job = manager.create("test.gds", "sky130")
        from backend.api.routes.fix import _fix_results_cache

        _fix_results_cache[job.job_id] = FixEngineResult(
            suggestions=[
                FixSuggestion(violation_category="x", rule_type="y", description="z")
            ]
        )
        r = client.post(
            f"/api/jobs/{job.job_id}/fix/apply-and-recheck",
            json={"suggestion_indices": [0]},
        )
        assert r.status_code == 400

    def test_apply_recheck_gds_deleted(self, client, uploaded_job):
        self._setup_fix_cache(uploaded_job)
        manager = deps.get_job_manager()
        job = manager.get(uploaded_job)
        Path(job.gds_path).unlink()

        r = client.post(
            f"/api/jobs/{uploaded_job}/fix/apply-and-recheck",
            json={"suggestion_indices": [0]},
        )
        assert r.status_code == 404

    def test_apply_recheck_index_out_of_range(self, client, uploaded_job):
        self._setup_fix_cache(uploaded_job)
        r = client.post(
            f"/api/jobs/{uploaded_job}/fix/apply-and-recheck",
            json={"suggestion_indices": [99]},
        )
        assert r.status_code == 400

    def test_apply_recheck_success_clean(self, client, uploaded_job):
        """Apply and re-DRC returns clean result."""
        self._setup_fix_cache(uploaded_job)

        from backend.core.violation_parser import ViolationParser

        # Create an empty report (0 violations)
        clean_lyrdb = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
  <description>DRC Report</description>
  <original-file>test.gds</original-file>
  <generator>klayout</generator>
  <top-cell>TOP</top-cell>
  <categories/>
  <cells><cell><name>TOP</name></cell></cells>
  <items/>
</report-database>"""

        manager = deps.get_job_manager()
        job_dir = manager.job_dir(uploaded_job)
        report_path = job_dir / "recheck_drc.lyrdb"
        report_path.write_text(clean_lyrdb)

        parser = ViolationParser()
        report = parser.parse_string(clean_lyrdb)

        mock_result = DRCResult(
            report=report,
            report_path=report_path,
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=0.05,
            klayout_binary="klayout",
        )

        with patch("backend.api.routes.fix.DRCRunner") as MockRunner:
            MockRunner.return_value.async_run = AsyncMock(return_value=mock_result)
            r = client.post(
                f"/api/jobs/{uploaded_job}/fix/apply-and-recheck",
                json={"suggestion_indices": [0]},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["is_clean"] is True
        assert data["total_violations"] == 0
        assert data["iteration"] == 2
        assert data["status"] == "complete"

    def test_apply_recheck_drc_error(self, client, uploaded_job):
        """500 when re-DRC fails."""
        self._setup_fix_cache(uploaded_job)
        from backend.core.drc_runner import DRCError

        with patch("backend.api.routes.fix.DRCRunner") as MockRunner:
            MockRunner.return_value.async_run = AsyncMock(
                side_effect=DRCError("klayout crashed")
            )
            r = client.post(
                f"/api/jobs/{uploaded_job}/fix/apply-and-recheck",
                json={"suggestion_indices": [0]},
            )

        assert r.status_code == 500
        assert "Re-DRC failed" in r.json()["detail"]

    def test_apply_recheck_file_not_found(self, client, uploaded_job):
        """404 when re-DRC can't find files."""
        self._setup_fix_cache(uploaded_job)

        with patch("backend.api.routes.fix.DRCRunner") as MockRunner:
            MockRunner.return_value.async_run = AsyncMock(
                side_effect=FileNotFoundError("klayout binary not found")
            )
            r = client.post(
                f"/api/jobs/{uploaded_job}/fix/apply-and-recheck",
                json={"suggestion_indices": [0]},
            )

        assert r.status_code == 404


class TestFixProvenance:
    def test_provenance_job_not_found(self, client):
        r = client.get("/api/jobs/nonexistent/fix/provenance")
        assert r.status_code == 404

    def test_provenance_empty(self, client, uploaded_job):
        r = client.get(f"/api/jobs/{uploaded_job}/fix/provenance")
        assert r.status_code == 200
        assert r.json()["total_records"] == 0

    def test_provenance_with_iteration_filter(self, client, uploaded_job):
        r = client.get(f"/api/jobs/{uploaded_job}/fix/provenance?iteration=1")
        assert r.status_code == 200
        assert r.json()["total_records"] == 0


class TestFixAuto:
    def test_auto_fix_job_not_found(self, client):
        r = client.post(
            "/api/jobs/nonexistent/fix/auto",
            json={"confidence_threshold": "high", "max_iterations": 5},
        )
        assert r.status_code == 404

    def test_auto_fix_no_gds(self, client):
        manager = deps.get_job_manager()
        job = manager.create("test.gds", "sky130")
        r = client.post(
            f"/api/jobs/{job.job_id}/fix/auto",
            json={"confidence_threshold": "high", "max_iterations": 5},
        )
        assert r.status_code == 400

    def test_auto_fix_no_report(self, client, uploaded_job):
        r = client.post(
            f"/api/jobs/{uploaded_job}/fix/auto",
            json={"confidence_threshold": "high", "max_iterations": 5},
        )
        assert r.status_code == 400

    def test_auto_fix_success(self, client, uploaded_job):
        """Auto-fix loop with mocked runner."""
        _setup_drc_complete(client, uploaded_job)

        from backend.fix.autofix import AutoFixResult

        mock_result = AutoFixResult(
            iterations_run=1,
            final_violation_count=0,
            fixes_applied_count=1,
            fixes_flagged_count=0,
            stop_reason="clean",
            iteration_history=[],
            oscillating_categories=[],
        )

        with patch("backend.api.routes.fix.AutoFixRunner") as MockRunner:
            MockRunner.return_value.run = AsyncMock(return_value=mock_result)
            r = client.post(
                f"/api/jobs/{uploaded_job}/fix/auto",
                json={"confidence_threshold": "high", "max_iterations": 5},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["stop_reason"] == "clean"
        assert data["final_violation_count"] == 0


class TestFixFlagged:
    def test_flagged_job_not_found(self, client):
        r = client.get("/api/jobs/nonexistent/fix/flagged")
        assert r.status_code == 404

    def test_flagged_empty(self, client, uploaded_job):
        r = client.get(f"/api/jobs/{uploaded_job}/fix/flagged")
        assert r.status_code == 200
        data = r.json()
        assert data["total_flagged"] == 0
        assert data["iterations"] == []


class TestFixFlaggedApprove:
    def test_approve_job_not_found(self, client):
        r = client.post(
            "/api/jobs/nonexistent/fix/flagged/approve",
            json={"provenance_ids": [1]},
        )
        assert r.status_code == 404

    def test_approve_no_gds(self, client):
        manager = deps.get_job_manager()
        job = manager.create("test.gds", "sky130")
        r = client.post(
            f"/api/jobs/{job.job_id}/fix/flagged/approve",
            json={"provenance_ids": [1]},
        )
        # Should fail with 400 (no GDS) or 404 (records not found)
        assert r.status_code in (400, 404)

    def test_approve_missing_records(self, client, uploaded_job):
        r = client.post(
            f"/api/jobs/{uploaded_job}/fix/flagged/approve",
            json={"provenance_ids": [999]},
        )
        assert r.status_code == 404
        assert "not found" in r.json()["detail"]


class TestFixFlaggedReject:
    def test_reject_job_not_found(self, client):
        r = client.post(
            "/api/jobs/nonexistent/fix/flagged/reject",
            json={"provenance_ids": [1]},
        )
        assert r.status_code == 404

    def test_reject_missing_records(self, client, uploaded_job):
        r = client.post(
            f"/api/jobs/{uploaded_job}/fix/flagged/reject",
            json={"provenance_ids": [999]},
        )
        assert r.status_code == 404


class TestClearFixCache:
    def test_clear_cache(self):
        from backend.api.routes.fix import _fix_results_cache, clear_fix_cache

        _fix_results_cache["test-job"] = FixEngineResult()
        clear_fix_cache("test-job")
        assert "test-job" not in _fix_results_cache

    def test_clear_cache_nonexistent(self):
        from backend.api.routes.fix import clear_fix_cache

        # Should not raise
        clear_fix_cache("nonexistent-job")


class TestPointsMatch:
    def test_match(self):
        from backend.api.routes.fix import _points_match

        a = [(0.0, 0.0), (1.0, 0.0)]
        b = [(0.0, 0.0), (1.0, 0.0)]
        assert _points_match(a, b) is True

    def test_no_match_different_lengths(self):
        from backend.api.routes.fix import _points_match

        assert _points_match([(0.0, 0.0)], [(0.0, 0.0), (1.0, 0.0)]) is False

    def test_no_match_different_values(self):
        from backend.api.routes.fix import _points_match

        a = [(0.0, 0.0), (1.0, 0.0)]
        b = [(0.0, 0.0), (2.0, 0.0)]
        assert _points_match(a, b) is False


# ── Layout route tests ────────────────────────────────────────────────────


class TestLayoutRoute:
    def test_layout_not_found(self, client):
        r = client.get("/api/jobs/nonexistent/layout")
        assert r.status_code == 404

    def test_layout_gds_deleted(self, client, uploaded_job):
        """404 when GDS file was deleted."""
        manager = deps.get_job_manager()
        job = manager.get(uploaded_job)
        Path(job.gds_path).unlink()

        r = client.get(f"/api/jobs/{uploaded_job}/layout")
        assert r.status_code == 404
        assert "not found on disk" in r.json()["detail"]


# ── Upload route tests ────────────────────────────────────────────────────


class TestUploadEdgeCases:
    def test_upload_no_filename(self, client):
        """Empty filename is rejected (422 from FastAPI validation or 400 from route)."""
        r = client.post(
            "/api/upload",
            files={"file": ("", io.BytesIO(b"data"), "application/octet-stream")},
        )
        assert r.status_code in (400, 422)

    def test_upload_oversized_file(self, client, tmp_dir):
        """413 when file exceeds MAX_FILE_SIZE."""
        from backend.api.routes.upload import MAX_FILE_SIZE

        # We can't actually send 500MB, so we patch MAX_FILE_SIZE
        with patch("backend.api.routes.upload.MAX_FILE_SIZE", 10):
            r = client.post(
                "/api/upload",
                files={
                    "file": (
                        "test.gds",
                        io.BytesIO(b"x" * 100),
                        "application/octet-stream",
                    )
                },
                params={"pdk_name": "sky130"},
            )
            assert r.status_code == 413


# ── LVS route edge cases ────────────────────────────────────────────────


class TestLVSBackground:
    def test_background_pdk_not_found(self, client, uploaded_job):
        """Background LVS handles PDK not found."""
        import asyncio

        from backend.api.routes.lvs import _run_lvs_background

        manager = deps.get_job_manager()
        job = manager.get(uploaded_job)
        job_dir = str(manager.job_dir(uploaded_job))

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            _run_lvs_background(
                uploaded_job, job.gds_path, "/tmp/netlist.spice", "nonexistent_pdk", job_dir
            )
        )
        loop.close()

        updated = manager.get(uploaded_job)
        assert updated.status == JobStatus.lvs_failed

    def test_background_lvs_error(self, client, uploaded_job):
        """Background LVS handles LVSError."""
        import asyncio

        from backend.api.routes.lvs import _run_lvs_background
        from backend.core.lvs_runner import LVSError

        manager = deps.get_job_manager()
        job = manager.get(uploaded_job)
        job_dir = str(manager.job_dir(uploaded_job))

        with patch("backend.api.routes.lvs.LVSRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(side_effect=LVSError("lvs crashed"))

            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                _run_lvs_background(
                    uploaded_job, job.gds_path, "/tmp/net.spice", "sky130", job_dir
                )
            )
            loop.close()

        updated = manager.get(uploaded_job)
        assert updated.status == JobStatus.lvs_failed

    def test_background_file_not_found(self, client, uploaded_job):
        """Background LVS handles FileNotFoundError."""
        import asyncio

        from backend.api.routes.lvs import _run_lvs_background

        manager = deps.get_job_manager()
        job = manager.get(uploaded_job)
        job_dir = str(manager.job_dir(uploaded_job))

        with patch("backend.api.routes.lvs.LVSRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(side_effect=FileNotFoundError("missing"))

            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                _run_lvs_background(
                    uploaded_job, job.gds_path, "/tmp/net.spice", "sky130", job_dir
                )
            )
            loop.close()

        updated = manager.get(uploaded_job)
        assert updated.status == JobStatus.lvs_failed

    def test_lvs_results_parse_error(self, client, uploaded_job):
        """500 when LVS report is malformed."""
        manager = deps.get_job_manager()
        job_dir = manager.job_dir(uploaded_job)
        report_path = job_dir / "bad_lvs.lvsdb"
        report_path.write_text("this is not a valid lvsdb file")
        manager.update_status(
            uploaded_job,
            JobStatus.lvs_complete,
            lvs_report_path=str(report_path),
        )
        r = client.get(f"/api/jobs/{uploaded_job}/lvs/results")
        assert r.status_code == 500
        assert "Failed to parse" in r.json()["detail"]


class TestLVSUploadEdgeCases:
    def test_upload_netlist_oversized(self, client, uploaded_job):
        """413 when netlist exceeds MAX_NETLIST_SIZE."""
        with patch("backend.api.routes.lvs.MAX_NETLIST_SIZE", 10):
            r = client.post(
                f"/api/jobs/{uploaded_job}/lvs/upload",
                files={
                    "file": (
                        "big.spice",
                        io.BytesIO(b"x" * 100),
                        "text/plain",
                    )
                },
            )
            assert r.status_code == 413

"""Tests for AutoFixRunner — confidence filtering, loop control, stop conditions."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.drc_runner import DRCError, DRCResult
from backend.fix.autofix import AutoFixRunner, _flag_reason, _is_auto_applicable
from backend.fix.fix_models import FixConfidence, FixSuggestion, PolygonDelta
from backend.jobs.manager import JobManager, JobStatus

# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture()
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture()
def manager(tmp_dir):
    return JobManager(jobs_dir=tmp_dir / "jobs")


@pytest.fixture()
def pdk():
    """Minimal PDK config for testing."""
    from backend.pdk.schema import (
        DesignRule,
        FixStrategyWeight,
        GDSLayer,
        PDKConfig,
        RuleType,
    )

    return PDKConfig(
        name="test",
        version="1.0",
        process_node_nm=130,
        grid_um=0.005,
        layers={
            "met1": GDSLayer(
                gds_layer=68,
                gds_datatype=20,
                description="Metal 1",
                color="#0000FF",
                is_routing=True,
            ),
        },
        rules=[
            DesignRule(
                rule_id="m1.1",
                rule_type=RuleType.min_width,
                layer="met1",
                value_um=0.140,
                severity=7,
            ),
        ],
        connectivity=[],
        fix_weights={
            "min_width": FixStrategyWeight(priority=3),
        },
        klayout_drc_deck="test.drc",
    )


def _make_suggestion(
    confidence: FixConfidence = FixConfidence.high,
    creates_new: bool = False,
    is_removal: bool = False,
    multi_layer: bool = False,
    category: str = "m1.1",
    rule_type: str = "min_width",
) -> FixSuggestion:
    """Create a FixSuggestion for testing."""
    delta_layer = 68
    delta_dt = 20
    orig = [(0.0, 0.0), (0.1, 0.0), (0.1, 1.0), (0.0, 1.0)]
    mod = [] if is_removal else [(0.0, 0.0), (0.14, 0.0), (0.14, 1.0), (0.0, 1.0)]

    deltas = [
        PolygonDelta(
            cell_name="TOP",
            gds_layer=delta_layer,
            gds_datatype=delta_dt,
            original_points=orig,
            modified_points=mod,
        )
    ]
    if multi_layer:
        deltas.append(
            PolygonDelta(
                cell_name="TOP",
                gds_layer=69,
                gds_datatype=20,
                original_points=[(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)],
                modified_points=[(1.0, 1.0), (2.5, 1.0), (2.5, 2.0), (1.0, 2.0)],
            )
        )

    return FixSuggestion(
        violation_category=category,
        rule_type=rule_type,
        description="Test fix",
        deltas=deltas,
        confidence=confidence,
        creates_new_violations=creates_new,
    )


# ── Confidence filtering tests ──────────────────────────


class TestIsAutoApplicable:
    def test_high_confidence_single_layer_no_new_violations(self):
        s = _make_suggestion(FixConfidence.high)
        assert _is_auto_applicable(s, "high") is True

    def test_low_confidence_always_flagged(self):
        s = _make_suggestion(FixConfidence.low)
        assert _is_auto_applicable(s, "high") is False
        assert _is_auto_applicable(s, "medium") is False

    def test_removal_always_flagged(self):
        s = _make_suggestion(FixConfidence.high, is_removal=True)
        assert _is_auto_applicable(s, "high") is False

    def test_creates_new_violations_always_flagged(self):
        s = _make_suggestion(FixConfidence.high, creates_new=True)
        assert _is_auto_applicable(s, "high") is False

    def test_multi_layer_always_flagged(self):
        s = _make_suggestion(FixConfidence.high, multi_layer=True)
        assert _is_auto_applicable(s, "high") is False

    def test_medium_confidence_flagged_in_high_mode(self):
        s = _make_suggestion(FixConfidence.medium)
        assert _is_auto_applicable(s, "high") is False

    def test_medium_confidence_applicable_in_medium_mode(self):
        s = _make_suggestion(FixConfidence.medium)
        assert _is_auto_applicable(s, "medium") is True


class TestFlagReason:
    def test_low_confidence(self):
        s = _make_suggestion(FixConfidence.low)
        assert _flag_reason(s, "high") == "low_confidence"

    def test_deletion(self):
        s = _make_suggestion(FixConfidence.high, is_removal=True)
        assert _flag_reason(s, "high") == "deletion_fix"

    def test_creates_new_violations(self):
        s = _make_suggestion(FixConfidence.high, creates_new=True)
        assert _flag_reason(s, "high") == "creates_new_violations"

    def test_multi_layer(self):
        s = _make_suggestion(FixConfidence.high, multi_layer=True)
        assert _flag_reason(s, "high") == "multi_layer"

    def test_medium_in_high_mode(self):
        s = _make_suggestion(FixConfidence.medium)
        assert _flag_reason(s, "high") == "medium_confidence_in_high_mode"


# ── AutoFixRunner loop tests ─────────────────────────────


def _make_lyrdb_report(violation_count: int, categories: list[str] | None = None) -> str:
    """Generate a minimal lyrdb report XML string with N violations."""
    if categories is None:
        categories = ["met1.1"] * violation_count

    cat_names = sorted(set(categories))
    cats_xml = "\n".join(
        f'    <category><name>{c}</name><description>Test</description></category>'
        for c in cat_names
    )
    items_xml = "\n".join(
        f"""    <item>
      <category>{cat}</category>
      <cell>TOP</cell>
      <values>
        <value>edge-pair: (0.000,0.000;0.100,0.000)/(0.000,0.050;0.100,0.050)</value>
      </values>
    </item>"""
        for cat in categories
    )

    return f"""<?xml version="1.0" encoding="utf-8"?>
<report-database>
  <description>DRC Report</description>
  <original-file>test.gds</original-file>
  <generator>klayout</generator>
  <top-cell>TOP</top-cell>
  <categories>
{cats_xml}
  </categories>
  <cells>
    <cell><name>TOP</name></cell>
  </cells>
  <items>
{items_xml}
  </items>
</report-database>"""


def _make_drc_result(
    report_path: Path,
    violation_count: int,
    categories: list[str] | None = None,
) -> DRCResult:
    """Build a DRCResult with a parsed report."""
    from backend.core.violation_parser import ViolationParser

    content = _make_lyrdb_report(violation_count, categories)
    report_path.write_text(content)
    parser = ViolationParser()
    report = parser.parse_file(report_path)

    return DRCResult(
        report=report,
        report_path=report_path,
        returncode=0,
        stdout="",
        stderr="",
        duration_seconds=0.1,
        klayout_binary="klayout",
    )


@pytest.fixture()
def job_with_drc(manager, tmp_dir):
    """Create a job with a GDS file and initial DRC report showing 3 violations."""
    import gdstk

    job = manager.create("test.gds", "test")
    job_dir = manager.job_dir(job.job_id)

    # Create GDS
    lib = gdstk.Library("test")
    cell = gdstk.Cell("TOP")
    cell.add(gdstk.rectangle((0, 0), (0.1, 1.0), layer=68, datatype=20))
    lib.add(cell)
    gds_path = job_dir / "test.gds"
    lib.write_gds(str(gds_path))

    # Create DRC report
    report_path = job_dir / "test_drc.lyrdb"
    report_path.write_text(_make_lyrdb_report(3))

    manager.update_status(
        job.job_id,
        JobStatus.drc_complete,
        gds_path=str(gds_path),
        report_path=str(report_path),
        total_violations=3,
    )

    return manager.get(job.job_id)


class TestAutoFixRunner:
    async def test_auto_fix_all_high_confidence_clean(
        self, manager, pdk, job_with_drc, tmp_dir
    ):
        """3 high-confidence width violations → all auto-fixed → re-DRC clean."""
        job = job_with_drc
        job_dir = manager.job_dir(job.job_id)

        suggestions = [_make_suggestion(FixConfidence.high) for _ in range(3)]

        from backend.fix.engine import FixEngineResult

        fix_result = FixEngineResult(suggestions=suggestions)

        # After fix: clean DRC (0 violations)
        clean_report_path = job_dir / "clean_drc.lyrdb"
        clean_drc_result = _make_drc_result(clean_report_path, 0)

        with (
            patch("backend.fix.autofix.FixEngine") as MockEngine,
            patch("backend.fix.autofix.DRCRunner") as MockDRCRunner,
            patch("backend.fix.autofix.LayoutManager"),
            patch("backend.fix.autofix.SpatialIndex"),
            patch("backend.fix.autofix.export_fixed_gds") as mock_export,
            patch("backend.fix.autofix._apply_deltas_from_suggestions", return_value=3),
        ):
            MockEngine.return_value.suggest_fixes.return_value = fix_result
            MockDRCRunner.return_value.async_run = AsyncMock(return_value=clean_drc_result)
            mock_export.return_value = job_dir / "test_fixed.gds"
            (job_dir / "test_fixed.gds").write_bytes(b"fake")

            runner = AutoFixRunner(manager, pdk, job)
            result = await runner.run(confidence_threshold="high", max_iterations=10)

        assert result.stop_reason == "drc_clean"
        assert result.iterations_run == 1
        assert result.final_violation_count == 0
        assert result.fixes_applied_count == 3
        assert result.fixes_flagged_count == 0
        assert len(result.iteration_history) == 1

    async def test_auto_fix_stall_all_flagged(self, manager, pdk, job_with_drc, tmp_dir):
        """All suggestions are low confidence → stall (nothing auto-applied)."""
        job = job_with_drc

        suggestions = [_make_suggestion(FixConfidence.low) for _ in range(3)]
        from backend.fix.engine import FixEngineResult

        fix_result = FixEngineResult(suggestions=suggestions)

        with (
            patch("backend.fix.autofix.FixEngine") as MockEngine,
            patch("backend.fix.autofix.LayoutManager"),
            patch("backend.fix.autofix.SpatialIndex"),
        ):
            MockEngine.return_value.suggest_fixes.return_value = fix_result

            runner = AutoFixRunner(manager, pdk, job)
            result = await runner.run(confidence_threshold="high", max_iterations=10)

        assert result.stop_reason == "stall"
        assert result.fixes_applied_count == 0
        assert result.fixes_flagged_count == 3

    async def test_auto_fix_medium_threshold_includes_medium(
        self, manager, pdk, job_with_drc, tmp_dir
    ):
        """With threshold='medium', medium-confidence fixes are auto-applied."""
        job = job_with_drc
        job_dir = manager.job_dir(job.job_id)

        suggestions = [_make_suggestion(FixConfidence.medium) for _ in range(2)]
        from backend.fix.engine import FixEngineResult

        fix_result = FixEngineResult(suggestions=suggestions)

        clean_report_path = job_dir / "clean_drc.lyrdb"
        clean_drc_result = _make_drc_result(clean_report_path, 0)

        with (
            patch("backend.fix.autofix.FixEngine") as MockEngine,
            patch("backend.fix.autofix.DRCRunner") as MockDRCRunner,
            patch("backend.fix.autofix.LayoutManager"),
            patch("backend.fix.autofix.SpatialIndex"),
            patch("backend.fix.autofix.export_fixed_gds") as mock_export,
            patch("backend.fix.autofix._apply_deltas_from_suggestions", return_value=2),
        ):
            MockEngine.return_value.suggest_fixes.return_value = fix_result
            MockDRCRunner.return_value.async_run = AsyncMock(return_value=clean_drc_result)
            mock_export.return_value = job_dir / "test_fixed.gds"
            (job_dir / "test_fixed.gds").write_bytes(b"fake")

            runner = AutoFixRunner(manager, pdk, job)
            result = await runner.run(confidence_threshold="medium", max_iterations=10)

        assert result.stop_reason == "drc_clean"
        assert result.fixes_applied_count == 2
        assert result.fixes_flagged_count == 0

    async def test_auto_fix_max_iterations(self, manager, pdk, job_with_drc, tmp_dir):
        """Loop respects max_iterations hard cap."""
        job = job_with_drc
        job_dir = manager.job_dir(job.job_id)

        suggestions = [_make_suggestion(FixConfidence.high)]
        from backend.fix.engine import FixEngineResult

        fix_result = FixEngineResult(suggestions=suggestions)

        # DRC always returns 2 violations (never clean, never increases — stays same)
        report_path = job_dir / "still_violations.lyrdb"
        drc_result = _make_drc_result(report_path, 2)

        with (
            patch("backend.fix.autofix.FixEngine") as MockEngine,
            patch("backend.fix.autofix.DRCRunner") as MockDRCRunner,
            patch("backend.fix.autofix.LayoutManager"),
            patch("backend.fix.autofix.SpatialIndex"),
            patch("backend.fix.autofix.export_fixed_gds") as mock_export,
            patch("backend.fix.autofix._apply_deltas_from_suggestions", return_value=1),
            patch("backend.fix.autofix.ViolationParser") as MockParser,
        ):
            MockEngine.return_value.suggest_fixes.return_value = fix_result
            MockDRCRunner.return_value.async_run = AsyncMock(return_value=drc_result)
            mock_export.return_value = job_dir / "test_fixed.gds"
            (job_dir / "test_fixed.gds").write_bytes(b"fake")

            # Mock the parser to return consistent reports
            mock_report = MagicMock()
            mock_report.violations = [
                MagicMock(category="met1.1", description="Test", violation_count=2)
            ]
            mock_report.total_violations = 2
            MockParser.return_value.parse_file.return_value = mock_report
            MockParser.return_value.map_to_pdk.return_value = None

            runner = AutoFixRunner(manager, pdk, job)
            result = await runner.run(confidence_threshold="high", max_iterations=3)

        assert result.stop_reason == "max_iterations"
        assert result.iterations_run == 3

    async def test_auto_fix_regression_detected(self, manager, pdk, job_with_drc, tmp_dir):
        """Loop stops when violations increase after a fix."""
        job = job_with_drc
        job_dir = manager.job_dir(job.job_id)

        suggestions = [_make_suggestion(FixConfidence.high)]
        from backend.fix.engine import FixEngineResult

        fix_result = FixEngineResult(suggestions=suggestions)

        # DRC returns MORE violations (5 > 3 initial)
        report_path = job_dir / "worse_drc.lyrdb"
        drc_result = _make_drc_result(report_path, 5)

        with (
            patch("backend.fix.autofix.FixEngine") as MockEngine,
            patch("backend.fix.autofix.DRCRunner") as MockDRCRunner,
            patch("backend.fix.autofix.LayoutManager"),
            patch("backend.fix.autofix.SpatialIndex"),
            patch("backend.fix.autofix.export_fixed_gds") as mock_export,
            patch("backend.fix.autofix._apply_deltas_from_suggestions", return_value=1),
        ):
            MockEngine.return_value.suggest_fixes.return_value = fix_result
            MockDRCRunner.return_value.async_run = AsyncMock(return_value=drc_result)
            mock_export.return_value = job_dir / "test_fixed.gds"
            (job_dir / "test_fixed.gds").write_bytes(b"fake")

            runner = AutoFixRunner(manager, pdk, job)
            result = await runner.run(confidence_threshold="high", max_iterations=10)

        assert result.stop_reason == "regression"
        assert result.iterations_run == 1
        assert result.final_violation_count == 5

    async def test_auto_fix_no_gds(self, manager, pdk, tmp_dir):
        """Early exit if no GDS file."""
        job = manager.create("test.gds", "test")

        runner = AutoFixRunner(manager, pdk, job)
        result = await runner.run()

        assert result.stop_reason == "no_gds_file"

    async def test_auto_fix_no_report(self, manager, pdk, tmp_dir):
        """Early exit if no DRC report."""
        import gdstk

        job = manager.create("test.gds", "test")
        job_dir = manager.job_dir(job.job_id)

        lib = gdstk.Library("test")
        cell = gdstk.Cell("TOP")
        cell.add(gdstk.rectangle((0, 0), (1, 1), layer=68, datatype=20))
        lib.add(cell)
        gds_path = job_dir / "test.gds"
        lib.write_gds(str(gds_path))

        manager.update_status(
            job.job_id, JobStatus.uploaded, gds_path=str(gds_path)
        )
        job = manager.get(job.job_id)

        runner = AutoFixRunner(manager, pdk, job)
        result = await runner.run()

        assert result.stop_reason == "no_drc_report"

    async def test_auto_fix_drc_error_stops_loop(
        self, manager, pdk, job_with_drc, tmp_dir
    ):
        """DRC error during re-check stops the loop."""
        job = job_with_drc
        job_dir = manager.job_dir(job.job_id)

        suggestions = [_make_suggestion(FixConfidence.high)]
        from backend.fix.engine import FixEngineResult

        fix_result = FixEngineResult(suggestions=suggestions)

        with (
            patch("backend.fix.autofix.FixEngine") as MockEngine,
            patch("backend.fix.autofix.DRCRunner") as MockDRCRunner,
            patch("backend.fix.autofix.LayoutManager"),
            patch("backend.fix.autofix.SpatialIndex"),
            patch("backend.fix.autofix.export_fixed_gds") as mock_export,
            patch("backend.fix.autofix._apply_deltas_from_suggestions", return_value=1),
        ):
            MockEngine.return_value.suggest_fixes.return_value = fix_result
            MockDRCRunner.return_value.async_run = AsyncMock(
                side_effect=DRCError("KLayout crashed")
            )
            mock_export.return_value = job_dir / "test_fixed.gds"
            (job_dir / "test_fixed.gds").write_bytes(b"fake")

            runner = AutoFixRunner(manager, pdk, job)
            result = await runner.run(confidence_threshold="high", max_iterations=10)

        assert result.stop_reason == "drc_error"

    async def test_auto_fix_mixed_confidence(
        self, manager, pdk, job_with_drc, tmp_dir
    ):
        """Mix of high and low confidence → high applied, low flagged."""
        job = job_with_drc
        job_dir = manager.job_dir(job.job_id)

        suggestions = [
            _make_suggestion(FixConfidence.high),
            _make_suggestion(FixConfidence.high),
            _make_suggestion(FixConfidence.low),
        ]
        from backend.fix.engine import FixEngineResult

        fix_result = FixEngineResult(suggestions=suggestions)

        clean_report_path = job_dir / "clean_drc.lyrdb"
        clean_drc_result = _make_drc_result(clean_report_path, 0)

        with (
            patch("backend.fix.autofix.FixEngine") as MockEngine,
            patch("backend.fix.autofix.DRCRunner") as MockDRCRunner,
            patch("backend.fix.autofix.LayoutManager"),
            patch("backend.fix.autofix.SpatialIndex"),
            patch("backend.fix.autofix.export_fixed_gds") as mock_export,
            patch("backend.fix.autofix._apply_deltas_from_suggestions", return_value=2),
        ):
            MockEngine.return_value.suggest_fixes.return_value = fix_result
            MockDRCRunner.return_value.async_run = AsyncMock(return_value=clean_drc_result)
            mock_export.return_value = job_dir / "test_fixed.gds"
            (job_dir / "test_fixed.gds").write_bytes(b"fake")

            runner = AutoFixRunner(manager, pdk, job)
            result = await runner.run(confidence_threshold="high", max_iterations=10)

        assert result.stop_reason == "drc_clean"
        assert result.fixes_flagged_count == 1  # low-confidence one

    async def test_iteration_history_recorded(
        self, manager, pdk, job_with_drc, tmp_dir
    ):
        """Iteration history records each iteration's stats."""
        job = job_with_drc
        job_dir = manager.job_dir(job.job_id)

        suggestions = [_make_suggestion(FixConfidence.high)]
        from backend.fix.engine import FixEngineResult

        fix_result = FixEngineResult(suggestions=suggestions)

        clean_report_path = job_dir / "clean_drc.lyrdb"
        clean_drc_result = _make_drc_result(clean_report_path, 0)

        with (
            patch("backend.fix.autofix.FixEngine") as MockEngine,
            patch("backend.fix.autofix.DRCRunner") as MockDRCRunner,
            patch("backend.fix.autofix.LayoutManager"),
            patch("backend.fix.autofix.SpatialIndex"),
            patch("backend.fix.autofix.export_fixed_gds") as mock_export,
            patch("backend.fix.autofix._apply_deltas_from_suggestions", return_value=1),
        ):
            MockEngine.return_value.suggest_fixes.return_value = fix_result
            MockDRCRunner.return_value.async_run = AsyncMock(return_value=clean_drc_result)
            mock_export.return_value = job_dir / "test_fixed.gds"
            (job_dir / "test_fixed.gds").write_bytes(b"fake")

            runner = AutoFixRunner(manager, pdk, job)
            result = await runner.run(confidence_threshold="high", max_iterations=10)

        assert len(result.iteration_history) == 1
        rec = result.iteration_history[0]
        assert rec.iteration == 1
        assert rec.total_violations == 0
        assert rec.flagged_count == 0

    async def test_no_suggestions_stops(self, manager, pdk, job_with_drc, tmp_dir):
        """If no suggestions at all, stop with no_suggestions."""
        job = job_with_drc

        from backend.fix.engine import FixEngineResult

        fix_result = FixEngineResult(suggestions=[])

        with (
            patch("backend.fix.autofix.FixEngine") as MockEngine,
            patch("backend.fix.autofix.LayoutManager"),
            patch("backend.fix.autofix.SpatialIndex"),
        ):
            MockEngine.return_value.suggest_fixes.return_value = fix_result

            runner = AutoFixRunner(manager, pdk, job)
            result = await runner.run(confidence_threshold="high", max_iterations=10)

        assert result.stop_reason == "no_suggestions"
        assert result.iterations_run == 0


# ── API Route test ────────────────────────────────────────


class TestAutoFixEndpoint:
    def test_auto_fix_no_gds(self):
        """Auto-fix returns 400 if no GDS file."""
        from fastapi.testclient import TestClient

        from backend.api import deps
        from backend.main import app

        deps.reset_deps()

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            import backend.config as cfg

            original_jobs = cfg.JOBS_DIR
            original_uploads = cfg.UPLOAD_DIR
            cfg.JOBS_DIR = tmp / "jobs"
            cfg.UPLOAD_DIR = tmp / "uploads"
            cfg.JOBS_DIR.mkdir()
            cfg.UPLOAD_DIR.mkdir()

            try:
                with TestClient(app) as client:
                    manager = deps.get_job_manager()
                    job = manager.create("test.gds", "sky130")

                    r = client.post(
                        f"/api/jobs/{job.job_id}/fix/auto",
                        json={"confidence_threshold": "high", "max_iterations": 5},
                    )
                    assert r.status_code == 400
            finally:
                cfg.JOBS_DIR = original_jobs
                cfg.UPLOAD_DIR = original_uploads
                deps.reset_deps()

    def test_auto_fix_not_found(self):
        """Auto-fix returns 404 for unknown job."""
        from fastapi.testclient import TestClient

        from backend.api import deps
        from backend.main import app

        deps.reset_deps()

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            import backend.config as cfg

            original_jobs = cfg.JOBS_DIR
            original_uploads = cfg.UPLOAD_DIR
            cfg.JOBS_DIR = tmp / "jobs"
            cfg.UPLOAD_DIR = tmp / "uploads"
            cfg.JOBS_DIR.mkdir()
            cfg.UPLOAD_DIR.mkdir()

            try:
                with TestClient(app) as client:
                    r = client.post(
                        "/api/jobs/nonexistent/fix/auto",
                        json={"confidence_threshold": "high"},
                    )
                    assert r.status_code == 404
            finally:
                cfg.JOBS_DIR = original_jobs
                cfg.UPLOAD_DIR = original_uploads
                deps.reset_deps()

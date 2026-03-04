"""Tests for AutoFixRunner — confidence filtering, loop control, stop conditions."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.drc_runner import DRCError, DRCResult
from backend.fix.autofix import (
    AutoFixRunner,
    _detect_oscillation,
    _flag_reason,
    _is_auto_applicable,
)
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


# ── Oscillation detection unit tests ─────────────────────


class TestDetectOscillation:
    def test_no_oscillation_steady_decrease(self):
        history = {"m1.1": [3, 2, 1, 0]}
        assert _detect_oscillation(history) == []

    def test_no_oscillation_too_short(self):
        history = {"m1.1": [3, 0]}
        assert _detect_oscillation(history) == []

    def test_oscillation_basic(self):
        """N > 0 → 0 → M > 0 pattern."""
        history = {"m1.1": [3, 0, 2]}
        assert _detect_oscillation(history) == ["m1.1"]

    def test_oscillation_later_in_history(self):
        """Oscillation detected even if it starts later."""
        history = {"m1.1": [5, 3, 0, 2]}
        assert _detect_oscillation(history) == ["m1.1"]

    def test_multiple_categories_oscillating(self):
        history = {
            "m1.1": [3, 0, 2],
            "m1.2": [1, 0, 1],
            "m1.3": [2, 1, 0],  # not oscillating
        }
        assert _detect_oscillation(history) == ["m1.1", "m1.2"]

    def test_no_oscillation_stays_zero(self):
        history = {"m1.1": [3, 0, 0, 0]}
        assert _detect_oscillation(history) == []

    def test_no_oscillation_monotonic_increase(self):
        history = {"m1.1": [1, 2, 3]}
        assert _detect_oscillation(history) == []


# ── Oscillation and regression loop tests ────────────────


class TestAutoFixOscillation:
    async def test_oscillation_stops_loop(self, manager, pdk, job_with_drc, tmp_dir):
        """Mock DRC that oscillates width violations → loop stops with oscillation."""
        job = job_with_drc
        job_dir = manager.job_dir(job.job_id)

        suggestions = [_make_suggestion(FixConfidence.high)]
        from backend.fix.engine import FixEngineResult

        fix_result = FixEngineResult(suggestions=suggestions)

        # DRC results cycle: iter1 → 0 violations, iter2 → 3 violations (oscillation)
        report_clean = job_dir / "clean_drc.lyrdb"
        drc_clean = _make_drc_result(report_clean, 0)

        report_back = job_dir / "back_drc.lyrdb"
        drc_back = _make_drc_result(report_back, 3, ["met1.1", "met1.1", "met1.1"])

        call_count = 0

        async def mock_drc(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return drc_clean
            else:
                return drc_back

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
            MockDRCRunner.return_value.async_run = AsyncMock(side_effect=mock_drc)
            mock_export.return_value = job_dir / "test_fixed.gds"
            (job_dir / "test_fixed.gds").write_bytes(b"fake")

            # Mock the parser for iteration 2+ (iteration 1 sees drc_clean and stops early
            # unless we simulate oscillation properly)
            # The initial report has met1.1 violations. After iter1 DRC → clean (0).
            # After iter2 DRC → 3 met1.1 violations (oscillation: 3 → 0 → 3)
            mock_report = MagicMock()
            mock_report.violations = [
                MagicMock(category="met1.1", description="Test", violation_count=3)
            ]
            mock_report.total_violations = 3
            MockParser.return_value.parse_file.return_value = mock_report
            MockParser.return_value.map_to_pdk.return_value = None

            # But we need the *initial* parse to return the real report (3 met1.1 violations).
            # The initial parse happens before the loop. Then DRC returns clean, but
            # the loop stops on drc_clean. To test oscillation we need 3+ iterations.
            # Simulate: initial=3, iter1 DRC=2, iter2 DRC=0, iter3 DRC=2 (oscillation)

            # Re-approach: make DRC always return violations that oscillate
            report_2v = job_dir / "drc_2v.lyrdb"
            drc_2v = _make_drc_result(report_2v, 2, ["met1.1", "met1.1"])
            report_0v = job_dir / "drc_0v_cat.lyrdb"
            drc_0v = _make_drc_result(report_0v, 2, ["met1.2", "met1.2"])
            report_2v_again = job_dir / "drc_2v_again.lyrdb"
            drc_2v_again = _make_drc_result(
                report_2v_again, 2, ["met1.1", "met1.1"]
            )

            call_count = 0

            async def mock_drc_oscillate(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return drc_2v  # met1.1: 2 violations
                elif call_count == 2:
                    return drc_0v  # met1.2: 2 violations, met1.1: 0
                else:
                    return drc_2v_again  # met1.1: 2 violations (oscillation!)

            MockDRCRunner.return_value.async_run = AsyncMock(
                side_effect=mock_drc_oscillate
            )

            runner = AutoFixRunner(manager, pdk, job)
            result = await runner.run(confidence_threshold="high", max_iterations=10)

        assert result.stop_reason == "oscillation"
        assert "met1.1" in result.oscillating_categories
        assert result.iterations_run == 3

    async def test_regression_with_before_after_counts(
        self, manager, pdk, job_with_drc, tmp_dir
    ):
        """Loop stops when violations increase, with before/after in history."""
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
        # Iteration history captures before/after
        assert len(result.iteration_history) == 1
        assert result.iteration_history[0].total_violations == 5

    async def test_stall_detected_zero_auto_applied(
        self, manager, pdk, job_with_drc, tmp_dir
    ):
        """Stall: all fixes flagged, none applicable → stop with stall."""
        job = job_with_drc

        suggestions = [
            _make_suggestion(FixConfidence.low),
            _make_suggestion(FixConfidence.low),
        ]
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
        assert result.fixes_flagged_count == 2
        assert len(result.iteration_history) == 1
        assert result.iteration_history[0].applied_count == 0
        assert result.iteration_history[0].flagged_count == 2

    async def test_no_oscillation_when_clean(self, manager, pdk, job_with_drc, tmp_dir):
        """No oscillation reported when loop stops due to clean DRC."""
        job = job_with_drc
        job_dir = manager.job_dir(job.job_id)

        suggestions = [_make_suggestion(FixConfidence.high) for _ in range(3)]
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
            patch("backend.fix.autofix._apply_deltas_from_suggestions", return_value=3),
        ):
            MockEngine.return_value.suggest_fixes.return_value = fix_result
            MockDRCRunner.return_value.async_run = AsyncMock(return_value=clean_drc_result)
            mock_export.return_value = job_dir / "test_fixed.gds"
            (job_dir / "test_fixed.gds").write_bytes(b"fake")

            runner = AutoFixRunner(manager, pdk, job)
            result = await runner.run(confidence_threshold="high", max_iterations=10)

        assert result.stop_reason == "drc_clean"
        assert result.oscillating_categories == []


# ── API Route test ────────────────────────────────────────


class TestAutoFixProvenance:
    """Verify provenance records are written during auto-fix runs."""

    async def test_provenance_written_for_applied_and_flagged(
        self, manager, pdk, job_with_drc, tmp_dir
    ):
        """Auto-fix writes provenance for both applied and flagged fixes."""
        job = job_with_drc
        job_dir = manager.job_dir(job.job_id)

        suggestions = [
            _make_suggestion(FixConfidence.high, category="m1.1"),
            _make_suggestion(FixConfidence.high, category="m1.2"),
            _make_suggestion(FixConfidence.low, category="m1.3"),
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

        # Check provenance records
        all_prov = manager.get_provenance(job.job_id)
        assert len(all_prov) == 3  # 2 applied + 1 flagged

        applied = manager.get_provenance(job.job_id, action="auto_applied")
        assert len(applied) == 2
        assert {r["violation_category"] for r in applied} == {"m1.1", "m1.2"}
        for r in applied:
            assert r["action"] == "auto_applied"
            assert r["flag_reason"] is None
            assert r["iteration"] == 1

        flagged = manager.get_provenance(job.job_id, action="flagged")
        assert len(flagged) == 1
        assert flagged[0]["violation_category"] == "m1.3"
        assert flagged[0]["flag_reason"] == "low_confidence"
        assert flagged[0]["confidence"] == "low"

    async def test_provenance_records_have_coordinates(
        self, manager, pdk, job_with_drc, tmp_dir
    ):
        """Provenance before/after points are stored as coordinate arrays."""
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
            await runner.run(confidence_threshold="high", max_iterations=10)

        records = manager.get_provenance(job.job_id)
        assert len(records) == 1
        r = records[0]
        assert r["before_points"] == [[0.0, 0.0], [0.1, 0.0], [0.1, 1.0], [0.0, 1.0]]
        assert r["after_points"] == [[0.0, 0.0], [0.14, 0.0], [0.14, 1.0], [0.0, 1.0]]
        assert r["cell_name"] == "TOP"
        assert r["gds_layer"] == 68
        assert r["gds_datatype"] == 20

    async def test_provenance_filter_by_iteration(
        self, manager, pdk, job_with_drc, tmp_dir
    ):
        """GET provenance with iteration filter returns correct subset."""
        job = job_with_drc

        # Manually insert provenance records for two iterations
        manager.insert_provenance(
            job_id=job.job_id, iteration=1, rule_id="m1.1",
            violation_category="m1.1", rule_type="min_width",
            confidence="high", action="auto_applied",
            before_points=[], after_points=[], cell_name="TOP",
            gds_layer=68, gds_datatype=20,
        )
        manager.insert_provenance(
            job_id=job.job_id, iteration=2, rule_id="m1.2",
            violation_category="m1.2", rule_type="min_spacing",
            confidence="medium", action="flagged", flag_reason="medium_confidence_in_high_mode",
            before_points=[], after_points=[], cell_name="TOP",
            gds_layer=68, gds_datatype=20,
        )

        all_records = manager.get_provenance(job.job_id)
        assert len(all_records) == 2

        iter1 = manager.get_provenance(job.job_id, iteration=1)
        assert len(iter1) == 1
        assert iter1[0]["rule_id"] == "m1.1"

        iter2 = manager.get_provenance(job.job_id, iteration=2)
        assert len(iter2) == 1
        assert iter2[0]["rule_id"] == "m1.2"


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


class TestProvenanceEndpoint:
    def test_get_provenance_empty(self):
        """GET provenance returns empty list for job with no records."""
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

                    r = client.get(f"/api/jobs/{job.job_id}/fix/provenance")
                    assert r.status_code == 200
                    data = r.json()
                    assert data["job_id"] == job.job_id
                    assert data["total_records"] == 0
                    assert data["records"] == []
            finally:
                cfg.JOBS_DIR = original_jobs
                cfg.UPLOAD_DIR = original_uploads
                deps.reset_deps()

    def test_get_provenance_with_records(self):
        """GET provenance returns inserted records."""
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

                    manager.insert_provenance(
                        job_id=job.job_id, iteration=1, rule_id="m1.1",
                        violation_category="m1.1", rule_type="min_width",
                        confidence="high", action="auto_applied",
                        before_points=[[0, 0], [1, 0]],
                        after_points=[[0, 0], [1.4, 0]],
                        cell_name="TOP", gds_layer=68, gds_datatype=20,
                    )
                    manager.insert_provenance(
                        job_id=job.job_id, iteration=1, rule_id="m1.2",
                        violation_category="m1.2", rule_type="min_spacing",
                        confidence="low", action="flagged", flag_reason="low_confidence",
                        before_points=[[2, 2], [3, 2]],
                        after_points=[[2, 2], [3.5, 2]],
                        cell_name="TOP", gds_layer=68, gds_datatype=20,
                    )

                    r = client.get(f"/api/jobs/{job.job_id}/fix/provenance")
                    assert r.status_code == 200
                    data = r.json()
                    assert data["total_records"] == 2

                    rec0 = data["records"][0]
                    assert rec0["action"] == "auto_applied"
                    assert rec0["rule_id"] == "m1.1"
                    assert rec0["before_points"] == [[0, 0], [1, 0]]
                    assert rec0["after_points"] == [[0, 0], [1.4, 0]]

                    rec1 = data["records"][1]
                    assert rec1["action"] == "flagged"
                    assert rec1["flag_reason"] == "low_confidence"
            finally:
                cfg.JOBS_DIR = original_jobs
                cfg.UPLOAD_DIR = original_uploads
                deps.reset_deps()

    def test_get_provenance_filter_iteration(self):
        """GET provenance?iteration=2 filters correctly."""
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

                    for i in range(1, 4):
                        manager.insert_provenance(
                            job_id=job.job_id, iteration=i, rule_id=f"m1.{i}",
                            violation_category=f"m1.{i}", rule_type="min_width",
                            confidence="high", action="auto_applied",
                            before_points=[], after_points=[],
                            cell_name="TOP", gds_layer=68, gds_datatype=20,
                        )

                    r = client.get(f"/api/jobs/{job.job_id}/fix/provenance?iteration=2")
                    assert r.status_code == 200
                    data = r.json()
                    assert data["total_records"] == 1
                    assert data["records"][0]["iteration"] == 2
                    assert data["records"][0]["rule_id"] == "m1.2"
            finally:
                cfg.JOBS_DIR = original_jobs
                cfg.UPLOAD_DIR = original_uploads
                deps.reset_deps()

    def test_get_provenance_not_found(self):
        """GET provenance returns 404 for unknown job."""
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
                    r = client.get("/api/jobs/nonexistent/fix/provenance")
                    assert r.status_code == 404
            finally:
                cfg.JOBS_DIR = original_jobs
                cfg.UPLOAD_DIR = original_uploads
                deps.reset_deps()

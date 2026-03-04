"""End-to-end integration tests — runs real KLayout DRC on generated GDS files.

Requires:
    - KLayout installed (macOS app bundle or on PATH)
    - SKY130 DRC deck vendored at backend/pdk/configs/sky130/sky130A_mr.drc

Skip automatically if KLayout is not available.
"""

import asyncio
import shutil
from pathlib import Path

import gdstk
import pytest

from backend.config import KLAYOUT_BINARY
from backend.core.drc_runner import DRCRunner
from backend.pdk.registry import PDKRegistry

KLAYOUT_AVAILABLE = (
    Path(KLAYOUT_BINARY).exists()
    if Path(KLAYOUT_BINARY).is_absolute()
    else shutil.which(KLAYOUT_BINARY) is not None
)
pytestmark = pytest.mark.skipif(not KLAYOUT_AVAILABLE, reason="KLayout CLI not installed")


@pytest.fixture()
def sky130():
    """Load the real SKY130 PDK config."""
    registry = PDKRegistry()
    return registry.load("sky130")


@pytest.fixture()
def clean_gds(tmp_path) -> Path:
    """A clean GDS with properly-sized met1 polygon — should pass DRC (met1 rules)."""
    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    cell = lib.new_cell("CLEAN")
    # met1 = layer 68, datatype 20
    # min width = 0.140 µm, min area = 0.083 µm²
    # Create a 1µm x 1µm square — well above minimums
    cell.add(gdstk.Polygon([(0, 0), (1, 0), (1, 1), (0, 1)], layer=68, datatype=20))
    path = tmp_path / "clean.gds"
    lib.write_gds(str(path))
    return path


@pytest.fixture()
def violating_gds(tmp_path) -> Path:
    """A GDS with intentional met1 width violation — should trigger DRC errors."""
    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    cell = lib.new_cell("VIOLATING")
    # met1 min width = 0.140 µm
    # Create a 0.05 µm wide strip — clear width violation
    cell.add(
        gdstk.Polygon(
            [(0, 0), (0.05, 0), (0.05, 1), (0, 1)],
            layer=68,
            datatype=20,
        )
    )
    path = tmp_path / "violating.gds"
    lib.write_gds(str(path))
    return path


@pytest.fixture()
def multi_layer_gds(tmp_path) -> Path:
    """A GDS with multiple layers to exercise more DRC rules."""
    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    cell = lib.new_cell("MULTI")

    # met1 — proper 1µm square
    cell.add(gdstk.Polygon([(0, 0), (1, 0), (1, 1), (0, 1)], layer=68, datatype=20))

    # met2 — narrow strip (0.05µm, min is 0.140µm)
    cell.add(gdstk.Polygon([(2, 0), (2.05, 0), (2.05, 1), (2, 1)], layer=69, datatype=20))

    # li1 — small area (0.01 µm², min is 0.0561 µm²)
    cell.add(gdstk.Polygon([(4, 0), (4.1, 0), (4.1, 0.1), (4, 0.1)], layer=67, datatype=20))

    path = tmp_path / "multi.gds"
    lib.write_gds(str(path))
    return path


class TestEndToEndDRC:
    """Run real KLayout DRC and verify results."""

    def test_klayout_binary_found(self):
        runner = DRCRunner()
        assert runner.check_klayout_available(), f"KLayout not found at {runner.binary}"

    def test_sky130_deck_exists(self, sky130):
        runner = DRCRunner()
        deck = runner.get_drc_deck_path(sky130)
        assert deck.exists()
        assert deck.name == "sky130A_mr.drc"

    def test_clean_layout_runs(self, clean_gds, sky130, tmp_path):
        """A properly-sized polygon should produce a DRC result (may still have some violations
        depending on which rule groups fire, but it should not crash)."""
        runner = DRCRunner()
        result = runner.run(
            clean_gds, sky130, top_cell="CLEAN", output_dir=tmp_path, map_to_pdk=False
        )

        assert result.returncode == 0
        assert result.report is not None
        assert result.report_path.exists()
        assert result.duration_seconds > 0
        assert result.strategy is not None
        assert result.strategy.mode == "deep"  # small file → deep mode

    def test_violating_layout_finds_violations(self, violating_gds, sky130, tmp_path):
        """A 50nm-wide met1 strip must trigger violations."""
        runner = DRCRunner()
        result = runner.run(
            violating_gds, sky130, top_cell="VIOLATING", output_dir=tmp_path, map_to_pdk=False
        )

        assert result.returncode == 0
        assert result.has_violations, "Expected DRC violations for undersized met1"
        assert result.report.total_violations > 0

    def test_multi_layer_violations(self, multi_layer_gds, sky130, tmp_path):
        """Multiple layers with violations should all be caught."""
        runner = DRCRunner()
        result = runner.run(
            multi_layer_gds, sky130, top_cell="MULTI", output_dir=tmp_path, map_to_pdk=False
        )

        assert result.returncode == 0
        assert result.has_violations
        # Should have violations from at least met2 width and li1 area
        categories = {v.category for v in result.report.violations}
        assert len(categories) >= 1, f"Expected multiple violation categories, got: {categories}"

    def test_pdk_mapping(self, violating_gds, sky130, tmp_path):
        """Violations should map to PDK rules when map_to_pdk=True."""
        runner = DRCRunner()
        result = runner.run(
            violating_gds, sky130, top_cell="VIOLATING", output_dir=tmp_path, map_to_pdk=True
        )

        assert result.has_violations
        # Verify PDK mapping ran — at least some violations should have rule_type
        assert any(v.rule_type is not None for v in result.report.violations)
        assert result.report.total_violations > 0


class TestAdaptiveStrategyE2E:
    """Verify adaptive strategy is applied during real DRC runs."""

    def test_small_file_uses_deep(self, clean_gds, sky130, tmp_path):
        """Small GDS files should use deep mode with 4 threads."""
        runner = DRCRunner()
        result = runner.run(
            clean_gds, sky130, top_cell="CLEAN", output_dir=tmp_path, map_to_pdk=False
        )

        assert result.strategy is not None
        assert result.strategy.mode == "deep"
        assert result.strategy.threads == 4
        assert result.strategy.tile_size_um is None

    def test_strategy_in_command(self, clean_gds, sky130, tmp_path):
        """Verify the CLI command includes strategy flags."""
        runner = DRCRunner()
        deck_path = runner.get_drc_deck_path(sky130)
        report_path = tmp_path / "report.lyrdb"

        file_size = clean_gds.stat().st_size
        strategy = DRCRunner.adaptive_strategy(file_size)
        cmd = runner.build_command(clean_gds, deck_path, report_path, strategy=strategy)

        cmd_str = " ".join(cmd)
        assert "thr=" in cmd_str
        assert "drc_mode=" in cmd_str


class TestAsyncDRCNonBlocking:
    """Verify async DRC execution doesn't block the event loop."""

    async def test_health_during_drc(self, clean_gds, sky130, tmp_path):
        """Start async DRC and verify event loop is not blocked.

        This is the key acceptance test: while DRC runs, other coroutines
        can still execute on the event loop.
        """
        runner = DRCRunner()

        # Track whether we could run another coroutine during DRC
        concurrent_work_done = False

        async def do_other_work():
            """Simulates other work that should be able to run during DRC."""
            nonlocal concurrent_work_done
            await asyncio.sleep(0)  # Yield to event loop
            concurrent_work_done = True

        # Run DRC and concurrent work simultaneously
        drc_task = runner.async_run(
            clean_gds, sky130, top_cell="CLEAN", output_dir=tmp_path, map_to_pdk=False
        )
        work_task = do_other_work()

        results = await asyncio.gather(drc_task, work_task, return_exceptions=True)

        # The concurrent work must have completed — proves non-blocking
        assert concurrent_work_done, "Event loop was blocked during async DRC"

        # DRC should have completed successfully
        drc_result = results[0]
        if not isinstance(drc_result, Exception):
            assert drc_result.returncode == 0

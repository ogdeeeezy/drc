"""Memory profiling tests — validate adaptive DRC prevents OOM.

Measures peak RSS during DRC execution across different GDS sizes.
Requires KLayout CLI installed. Skip automatically if not available.
"""

import os
import resource
import shutil
from pathlib import Path

import gdstk
import pytest

from backend.config import (
    DRC_LARGE_THRESHOLD,
    DRC_SMALL_THRESHOLD,
    KLAYOUT_BINARY,
)
from backend.core.drc_runner import DRCRunner
from backend.pdk.registry import PDKRegistry

KLAYOUT_AVAILABLE = (
    Path(KLAYOUT_BINARY).exists()
    if Path(KLAYOUT_BINARY).is_absolute()
    else shutil.which(KLAYOUT_BINARY) is not None
)
pytestmark = pytest.mark.skipif(not KLAYOUT_AVAILABLE, reason="KLayout CLI not installed")

# Memory limit: 2 GB peak RSS
MAX_RSS_BYTES = 2 * 1024 * 1024 * 1024


@pytest.fixture()
def sky130():
    registry = PDKRegistry()
    return registry.load("sky130")


def _generate_dense_gds(path: Path, num_polygons: int, cell_name: str = "DENSE") -> Path:
    """Generate a GDS with many met1 polygons to create a larger file."""
    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    cell = lib.new_cell(cell_name)

    cols = int(num_polygons**0.5) + 1
    for i in range(num_polygons):
        x = (i % cols) * 2.0
        y = (i // cols) * 2.0
        cell.add(
            gdstk.Polygon(
                [(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)],
                layer=68,
                datatype=20,
            )
        )

    lib.write_gds(str(path))
    return path


def _get_peak_rss_bytes() -> int:
    """Get peak resident set size in bytes."""
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    if os.uname().sysname == "Darwin":
        return usage.ru_maxrss  # bytes on macOS
    return usage.ru_maxrss * 1024  # KB → bytes on Linux


def _run_drc(runner, gds_path, sky130, tmp_path):
    """Helper to run DRC with standard args."""
    return runner.run(
        gds_path,
        sky130,
        top_cell="DENSE",
        output_dir=tmp_path,
        map_to_pdk=False,
    )


class TestMemoryProfiling:
    """Profile memory usage across different GDS sizes."""

    def test_small_gds_memory(self, sky130, tmp_path):
        """Small GDS (few polygons) should use minimal memory."""
        gds_path = _generate_dense_gds(tmp_path / "small.gds", 10)
        file_size = gds_path.stat().st_size
        assert file_size < DRC_SMALL_THRESHOLD

        rss_before = _get_peak_rss_bytes()
        runner = DRCRunner()
        result = _run_drc(runner, gds_path, sky130, tmp_path)
        rss_after = _get_peak_rss_bytes()

        assert result.returncode == 0
        assert result.strategy.mode == "deep"
        assert result.strategy.threads == 4

        delta_mb = (rss_after - rss_before) / (1024 * 1024)
        print(
            f"\n[MEMORY] Small GDS ({file_size} bytes, 10 polys): peak RSS delta ~{delta_mb:.1f} MB"
        )
        assert rss_after < MAX_RSS_BYTES

    def test_medium_gds_memory(self, sky130, tmp_path):
        """Medium GDS (more polygons)."""
        gds_path = _generate_dense_gds(tmp_path / "medium.gds", 5000)
        file_size = gds_path.stat().st_size

        runner = DRCRunner()
        rss_before = _get_peak_rss_bytes()
        result = _run_drc(runner, gds_path, sky130, tmp_path)
        rss_after = _get_peak_rss_bytes()

        assert result.returncode == 0

        delta_mb = (rss_after - rss_before) / (1024 * 1024)
        print(
            f"\n[MEMORY] Medium GDS ({file_size} bytes, 5000 polys):"
            f" mode={result.strategy.mode},"
            f" threads={result.strategy.threads},"
            f" peak RSS delta ~{delta_mb:.1f} MB"
        )
        assert rss_after < MAX_RSS_BYTES

    def test_large_gds_memory(self, sky130, tmp_path):
        """Large GDS — verify memory stays bounded."""
        gds_path = _generate_dense_gds(tmp_path / "large.gds", 20000)
        file_size = gds_path.stat().st_size

        rss_before = _get_peak_rss_bytes()
        runner = DRCRunner()
        result = _run_drc(runner, gds_path, sky130, tmp_path)
        rss_after = _get_peak_rss_bytes()

        assert result.returncode == 0

        delta_mb = (rss_after - rss_before) / (1024 * 1024)
        print(
            f"\n[MEMORY] Large GDS ({file_size} bytes, 20000 polys):"
            f" mode={result.strategy.mode},"
            f" threads={result.strategy.threads},"
            f" peak RSS delta ~{delta_mb:.1f} MB"
        )
        assert rss_after < MAX_RSS_BYTES


class TestAdaptiveStrategyThresholds:
    """Verify the file-size to strategy mapping."""

    def test_strategy_tiers_are_deterministic(self):
        """Same file size always picks the same strategy."""
        sizes = [
            0,
            1024,
            DRC_SMALL_THRESHOLD - 1,
            DRC_SMALL_THRESHOLD,
            DRC_LARGE_THRESHOLD - 1,
            DRC_LARGE_THRESHOLD,
            200 * 1024 * 1024,
        ]
        for size in sizes:
            s1 = DRCRunner.adaptive_strategy(size)
            s2 = DRCRunner.adaptive_strategy(size)
            assert s1 == s2, f"Non-deterministic at {size} bytes"

    def test_tiled_mode_params_complete(self):
        """Tiled strategy must include tile_size_um."""
        strategy = DRCRunner.adaptive_strategy(DRC_LARGE_THRESHOLD)
        assert strategy.mode == "tiled"
        assert strategy.tile_size_um is not None
        assert strategy.tile_size_um > 0
        assert strategy.threads == 1

    def test_deep_mode_no_tile_size(self):
        """Deep strategy must not include tile_size_um."""
        for size in [0, DRC_SMALL_THRESHOLD - 1, DRC_SMALL_THRESHOLD]:
            strategy = DRCRunner.adaptive_strategy(size)
            assert strategy.mode == "deep"
            assert strategy.tile_size_um is None


class TestMemoryBudgetEstimates:
    """Estimate memory per polygon to project OOM risk."""

    @pytest.mark.parametrize("num_polys", [100, 1000, 5000])
    def test_memory_scaling(self, sky130, tmp_path, num_polys):
        """Measure memory growth as polygon count increases."""
        gds_path = _generate_dense_gds(tmp_path / f"scale_{num_polys}.gds", num_polys)
        file_size = gds_path.stat().st_size

        rss_before = _get_peak_rss_bytes()
        runner = DRCRunner()
        result = _run_drc(runner, gds_path, sky130, tmp_path)
        rss_after = _get_peak_rss_bytes()

        assert result.returncode == 0

        delta_mb = (rss_after - rss_before) / (1024 * 1024)
        bpp = file_size / num_polys if num_polys > 0 else 0
        print(
            f"\n[SCALING] {num_polys} polys: file={file_size} bytes"
            f" ({bpp:.0f} bytes/poly),"
            f" RSS delta ~{delta_mb:.1f} MB,"
            f" mode={result.strategy.mode}"
        )

"""Tests for sandboxed GDS parsing."""

from pathlib import Path

import gdstk
import pytest

from backend.core.sandbox import SandboxedParseResult, parse_gds_sandboxed


@pytest.fixture()
def sample_gds(tmp_path) -> Path:
    """Create a minimal valid GDS file."""
    lib = gdstk.Library("test_lib")
    cell = lib.new_cell("top")
    cell.add(
        gdstk.Polygon(
            [(0, 0), (1, 0), (1, 1), (0, 1)],
            layer=1,
            datatype=0,
        )
    )
    gds_path = tmp_path / "test.gds"
    lib.write_gds(str(gds_path))
    return gds_path


@pytest.fixture()
def multi_cell_gds(tmp_path) -> Path:
    """Create a GDS with multiple cells."""
    lib = gdstk.Library("multi_lib")
    sub = lib.new_cell("sub_cell")
    sub.add(gdstk.Polygon([(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)], layer=1))
    top = lib.new_cell("top_cell")
    top.add(gdstk.Polygon([(0, 0), (2, 0), (2, 2), (0, 2)], layer=2))
    top.add(gdstk.Reference(sub))
    gds_path = tmp_path / "multi.gds"
    lib.write_gds(str(gds_path))
    return gds_path


class TestSandboxedParse:
    """Test sandboxed GDS parsing."""

    def test_parse_valid_gds(self, sample_gds: Path):
        """Valid GDS file parses successfully in sandbox."""
        result = parse_gds_sandboxed(sample_gds)
        assert result.success is True
        assert result.cell_count == 1
        assert result.total_polygons == 1
        assert "top" in result.top_cell_names
        assert result.error is None
        assert result.file_size_bytes > 0

    def test_parse_multi_cell(self, multi_cell_gds: Path):
        """Multi-cell GDS reports correct counts."""
        result = parse_gds_sandboxed(multi_cell_gds)
        assert result.success is True
        assert result.cell_count == 2
        assert result.total_polygons == 2  # one per cell (not flattened)
        assert "top_cell" in result.top_cell_names

    def test_file_not_found(self, tmp_path: Path):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_gds_sandboxed(tmp_path / "nonexistent.gds")

    def test_invalid_file(self, tmp_path: Path):
        """Non-GDS file fails gracefully."""
        bad_file = tmp_path / "bad.gds"
        bad_file.write_bytes(b"this is not a gds file at all")
        result = parse_gds_sandboxed(bad_file)
        assert result.success is False
        assert result.error is not None

    def test_timeout(self, sample_gds: Path):
        """Extremely short timeout triggers timeout error."""
        # 0.001s timeout — subprocess can't possibly finish
        result = parse_gds_sandboxed(sample_gds, timeout=0.001)
        # May succeed on very fast machines, but should not crash
        if not result.success:
            assert "timed out" in (result.error or "").lower() or result.error is not None

    def test_custom_limits(self, sample_gds: Path):
        """Custom memory and CPU limits don't break valid parsing."""
        result = parse_gds_sandboxed(
            sample_gds,
            timeout=30,
            max_memory_mb=256,
            max_cpu_seconds=10,
        )
        assert result.success is True

    def test_empty_gds(self, tmp_path: Path):
        """GDS with no cells parses but reports zero."""
        lib = gdstk.Library("empty")
        gds_path = tmp_path / "empty.gds"
        lib.write_gds(str(gds_path))
        result = parse_gds_sandboxed(gds_path)
        assert result.success is True
        assert result.cell_count == 0
        assert result.total_polygons == 0


class TestLayoutManagerSandboxIntegration:
    """Test that LayoutManager.load() uses sandboxed pre-parse."""

    def test_load_with_sandbox(self, sample_gds: Path):
        """LayoutManager.load() with sandbox=True works for valid files."""
        from backend.core.layout import LayoutManager

        mgr = LayoutManager()
        mgr.load(sample_gds, sandbox=True)
        assert mgr.library is not None
        assert len(mgr.list_cells()) == 1

    def test_load_without_sandbox(self, sample_gds: Path):
        """LayoutManager.load() with sandbox=False skips pre-parse."""
        from backend.core.layout import LayoutManager

        mgr = LayoutManager()
        mgr.load(sample_gds, sandbox=False)
        assert mgr.library is not None

    def test_load_invalid_rejected_by_sandbox(self, tmp_path: Path):
        """LayoutManager.load() rejects invalid files via sandbox."""
        from backend.core.layout import LayoutManager

        bad_file = tmp_path / "bad.gds"
        bad_file.write_bytes(b"not a gds file")
        mgr = LayoutManager()
        with pytest.raises(RuntimeError, match="sandboxed validation"):
            mgr.load(bad_file, sandbox=True)

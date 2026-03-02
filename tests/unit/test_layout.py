"""Tests for GDSII layout manager."""

from pathlib import Path

import gdstk
import pytest

from backend.core.layout import LayoutManager, PolygonInfo


@pytest.fixture()
def sample_gds(tmp_path) -> Path:
    """Create a minimal GDSII file with known geometry."""
    lib = gdstk.Library("test_lib")
    cell = lib.new_cell("top")

    # met1 rectangle: 0.14um x 1.0um
    cell.add(gdstk.Polygon(
        [(0, 0), (0.14, 0), (0.14, 1.0), (0, 1.0)],
        layer=68, datatype=20,
    ))

    # met2 rectangle
    cell.add(gdstk.Polygon(
        [(0.5, 0), (1.0, 0), (1.0, 0.5), (0.5, 0.5)],
        layer=69, datatype=20,
    ))

    # via
    cell.add(gdstk.Polygon(
        [(0, 0), (0.15, 0), (0.15, 0.15), (0, 0.15)],
        layer=68, datatype=44,
    ))

    gds_path = tmp_path / "test.gds"
    lib.write_gds(str(gds_path))
    return gds_path


@pytest.fixture()
def hierarchical_gds(tmp_path) -> Path:
    """Create a GDSII with cell hierarchy."""
    lib = gdstk.Library("hier_lib")

    sub_cell = lib.new_cell("sub")
    sub_cell.add(gdstk.Polygon(
        [(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)],
        layer=68, datatype=20,
    ))

    top = lib.new_cell("top")
    top.add(gdstk.Reference(sub_cell, origin=(0, 0)))
    top.add(gdstk.Reference(sub_cell, origin=(1.0, 0)))

    gds_path = tmp_path / "hier.gds"
    lib.write_gds(str(gds_path))
    return gds_path


class TestLayoutManager:
    def test_load(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        assert lm.source_path == sample_gds

    def test_load_missing_file(self):
        lm = LayoutManager()
        with pytest.raises(FileNotFoundError):
            lm.load("/nonexistent/file.gds")

    def test_no_library_raises(self):
        lm = LayoutManager()
        with pytest.raises(RuntimeError, match="No layout loaded"):
            _ = lm.library

    def test_list_cells(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        cells = lm.list_cells()
        assert len(cells) == 1
        assert cells[0].name == "top"
        assert cells[0].polygon_count == 3

    def test_get_cell(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        cell = lm.get_cell("top")
        assert cell.name == "top"

    def test_get_cell_missing(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        with pytest.raises(KeyError, match="not found"):
            lm.get_cell("nonexistent")

    def test_get_top_cells(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        top = lm.get_top_cells()
        assert len(top) == 1
        assert top[0].name == "top"

    def test_get_all_polygons(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        polys = lm.get_polygons()
        assert len(polys) == 3

    def test_get_polygons_by_layer(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        met1 = lm.get_polygons(layer=68, datatype=20)
        assert len(met1) == 1
        met2 = lm.get_polygons(layer=69, datatype=20)
        assert len(met2) == 1

    def test_polygon_points(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        met1 = lm.get_polygons(layer=68, datatype=20)
        assert len(met1[0].points) == 4
        assert met1[0].gds_layer == 68
        assert met1[0].gds_datatype == 20

    def test_save_roundtrip(self, sample_gds, tmp_path):
        lm = LayoutManager()
        lm.load(sample_gds)
        output = tmp_path / "output.gds"
        lm.save(output)
        assert output.exists()

        # Reload and verify
        lm2 = LayoutManager()
        lm2.load(output)
        assert len(lm2.get_polygons()) == 3

    def test_new_library(self):
        lm = LayoutManager()
        lm.new_library("test")
        assert lm.source_path is None
        assert len(lm.list_cells()) == 0

    def test_hierarchical_get_polygons(self, hierarchical_gds):
        lm = LayoutManager()
        lm.load(hierarchical_gds)
        # Direct polygons on top cell (no references resolved)
        polys = lm.get_polygons(cell_name="top")
        assert len(polys) == 0

    def test_hierarchical_flatten(self, hierarchical_gds):
        lm = LayoutManager()
        lm.load(hierarchical_gds)
        flat = lm.get_flattened_polygons(cell_name="top")
        assert len(flat) == 2  # Two instances of sub_cell's polygon

    def test_add_polygon(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        before = len(lm.get_polygons())
        lm.add_polygon("top", [(0, 0), (1, 0), (1, 1), (0, 1)], layer=70, datatype=20)
        after = len(lm.get_polygons())
        assert after == before + 1

    def test_remove_polygon(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        before = len(lm.get_polygons())
        lm.remove_polygon("top", 0)
        after = len(lm.get_polygons())
        assert after == before - 1

    def test_remove_polygon_out_of_range(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        with pytest.raises(IndexError):
            lm.remove_polygon("top", 99)

    def test_replace_polygon(self, sample_gds):
        lm = LayoutManager()
        lm.load(sample_gds)
        new_pts = [(0, 0), (0.2, 0), (0.2, 0.5), (0, 0.5)]
        lm.replace_polygon("top", 0, new_pts)
        polys = lm.get_polygons()
        # Check the replacement happened (polygon count unchanged)
        assert len(polys) == 3

"""Tests for geometry utilities."""

import math

import pytest

from backend.core.geometry_utils import (
    bbox_height,
    bbox_width,
    bboxes_overlap,
    is_on_grid,
    min_edge_width,
    point_distance,
    polygon_area,
    polygon_bbox,
    snap_point_to_grid,
    snap_to_grid,
)


class TestSnapToGrid:
    def test_already_on_grid(self):
        assert snap_to_grid(0.140, 0.005) == pytest.approx(0.140)

    def test_snap_up(self):
        assert snap_to_grid(0.142, 0.005) == pytest.approx(0.140)

    def test_snap_down(self):
        assert snap_to_grid(0.143, 0.005) == pytest.approx(0.145)

    def test_zero(self):
        assert snap_to_grid(0.0) == pytest.approx(0.0)

    def test_negative(self):
        assert snap_to_grid(-0.143, 0.005) == pytest.approx(-0.145)

    def test_custom_grid(self):
        assert snap_to_grid(0.007, 0.01) == pytest.approx(0.01)


class TestSnapPointToGrid:
    def test_snap_point(self):
        x, y = snap_point_to_grid(0.142, 0.143, 0.005)
        assert x == pytest.approx(0.140)
        assert y == pytest.approx(0.145)


class TestPolygonArea:
    def test_unit_square(self):
        pts = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert polygon_area(pts) == pytest.approx(1.0)

    def test_rectangle(self):
        pts = [(0, 0), (0.14, 0), (0.14, 0.5), (0, 0.5)]
        assert polygon_area(pts) == pytest.approx(0.07)

    def test_triangle(self):
        pts = [(0, 0), (4, 0), (0, 3)]
        assert polygon_area(pts) == pytest.approx(6.0)

    def test_empty(self):
        assert polygon_area([]) == 0.0

    def test_two_points(self):
        assert polygon_area([(0, 0), (1, 1)]) == 0.0


class TestPolygonBbox:
    def test_rectangle(self):
        pts = [(1, 2), (3, 2), (3, 5), (1, 5)]
        assert polygon_bbox(pts) == (1, 2, 3, 5)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            polygon_bbox([])


class TestBboxDimensions:
    def test_width(self):
        assert bbox_width((0, 0, 3, 5)) == 3

    def test_height(self):
        assert bbox_height((0, 0, 3, 5)) == 5


class TestBboxesOverlap:
    def test_overlap(self):
        assert bboxes_overlap((0, 0, 2, 2), (1, 1, 3, 3)) is True

    def test_no_overlap(self):
        assert bboxes_overlap((0, 0, 1, 1), (2, 2, 3, 3)) is False

    def test_touching(self):
        assert bboxes_overlap((0, 0, 1, 1), (1, 0, 2, 1)) is True


class TestPointDistance:
    def test_horizontal(self):
        assert point_distance((0, 0), (3, 0)) == pytest.approx(3.0)

    def test_diagonal(self):
        assert point_distance((0, 0), (3, 4)) == pytest.approx(5.0)

    def test_same_point(self):
        assert point_distance((1, 1), (1, 1)) == pytest.approx(0.0)


class TestMinEdgeWidth:
    def test_wide_rectangle(self):
        pts = [(0, 0), (1.0, 0), (1.0, 0.14), (0, 0.14)]
        assert min_edge_width(pts) == pytest.approx(0.14)

    def test_tall_rectangle(self):
        pts = [(0, 0), (0.14, 0), (0.14, 1.0), (0, 1.0)]
        assert min_edge_width(pts) == pytest.approx(0.14)

    def test_square(self):
        pts = [(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)]
        assert min_edge_width(pts) == pytest.approx(0.5)


class TestIsOnGrid:
    def test_on_grid(self):
        assert is_on_grid(0.140) is True
        assert is_on_grid(0.005) is True
        assert is_on_grid(0.0) is True

    def test_off_grid(self):
        assert is_on_grid(0.003) is False
        assert is_on_grid(0.141) is False

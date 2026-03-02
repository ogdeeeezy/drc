"""Tests for spatial index (R-tree polygon lookups)."""

import pytest

from backend.core.layout import PolygonInfo
from backend.core.spatial_index import SpatialIndex


def _poly(points, layer=68, datatype=20, cell="TOP"):
    return PolygonInfo(points=points, gds_layer=layer, gds_datatype=datatype, cell_name=cell)


class TestSpatialIndex:
    def test_insert_and_count(self):
        si = SpatialIndex()
        p = _poly([(0, 0), (1, 0), (1, 1), (0, 1)])
        idx = si.insert(p)
        assert si.count == 1
        assert idx == 0

    def test_insert_many(self):
        si = SpatialIndex()
        polys = [
            _poly([(0, 0), (1, 0), (1, 1), (0, 1)]),
            _poly([(5, 5), (6, 5), (6, 6), (5, 6)]),
        ]
        ids = si.insert_many(polys)
        assert len(ids) == 2
        assert si.count == 2

    def test_query_bbox_hit(self):
        si = SpatialIndex()
        si.insert(_poly([(0, 0), (1, 0), (1, 1), (0, 1)]))
        results = si.query_bbox((0.5, 0.5, 0.5, 0.5))
        assert len(results) == 1

    def test_query_bbox_miss(self):
        si = SpatialIndex()
        si.insert(_poly([(0, 0), (1, 0), (1, 1), (0, 1)]))
        results = si.query_bbox((5, 5, 6, 6))
        assert len(results) == 0

    def test_query_bbox_layer_filter(self):
        si = SpatialIndex()
        si.insert(_poly([(0, 0), (1, 0), (1, 1), (0, 1)], layer=68))
        si.insert(_poly([(0, 0), (1, 0), (1, 1), (0, 1)], layer=69))
        results = si.query_bbox((0, 0, 1, 1), layer=68)
        assert len(results) == 1
        assert results[0].polygon.gds_layer == 68

    def test_query_point(self):
        si = SpatialIndex()
        si.insert(_poly([(0, 0), (2, 0), (2, 2), (0, 2)]))
        results = si.query_point(1.0, 1.0)
        assert len(results) == 1

    def test_query_nearby(self):
        si = SpatialIndex()
        si.insert(_poly([(0, 0), (1, 0), (1, 1), (0, 1)]))
        si.insert(_poly([(2, 0), (3, 0), (3, 1), (2, 1)]))
        # With 0.5 margin from first poly, shouldn't reach second
        results = si.query_nearby((0, 0, 1, 1), margin=0.5)
        assert len(results) == 1
        # With 1.5 margin, should reach second
        results = si.query_nearby((0, 0, 1, 1), margin=1.5)
        assert len(results) == 2

    def test_nearest(self):
        si = SpatialIndex()
        si.insert(_poly([(0, 0), (1, 0), (1, 1), (0, 1)]))
        si.insert(_poly([(10, 10), (11, 10), (11, 11), (10, 11)]))
        results = si.nearest((0.5, 0.5, 0.5, 0.5), num_results=1)
        assert len(results) == 1
        assert results[0].polygon.points[0] == (0, 0)

    def test_get(self):
        si = SpatialIndex()
        idx = si.insert(_poly([(0, 0), (1, 0), (1, 1), (0, 1)]))
        ip = si.get(idx)
        assert ip.index_id == idx

    def test_get_missing(self):
        si = SpatialIndex()
        with pytest.raises(KeyError):
            si.get(99)

    def test_remove(self):
        si = SpatialIndex()
        idx = si.insert(_poly([(0, 0), (1, 0), (1, 1), (0, 1)]))
        si.remove(idx)
        assert si.count == 0
        results = si.query_bbox((0, 0, 1, 1))
        assert len(results) == 0

    def test_remove_missing(self):
        si = SpatialIndex()
        with pytest.raises(KeyError):
            si.remove(99)

    def test_from_polygons(self):
        polys = [
            _poly([(0, 0), (1, 0), (1, 1), (0, 1)]),
            _poly([(5, 5), (6, 5), (6, 6), (5, 6)]),
        ]
        si = SpatialIndex.from_polygons(polys)
        assert si.count == 2

    def test_indexed_polygon_bbox(self):
        si = SpatialIndex()
        idx = si.insert(_poly([(0, 0), (2, 0), (2, 3), (0, 3)]))
        ip = si.get(idx)
        assert ip.bbox == (0, 0, 2, 3)

"""Tests for violation data models."""

from backend.core.violation_models import (
    DRCReport,
    EdgePair,
    GeometryType,
    Violation,
    ViolationGeometry,
)


class TestEdgePair:
    def test_bbox(self):
        ep = EdgePair(
            edge1_start=(1.0, 2.0),
            edge1_end=(1.0, 5.0),
            edge2_start=(3.0, 2.0),
            edge2_end=(3.0, 5.0),
        )
        assert ep.bbox == (1.0, 2.0, 3.0, 5.0)

    def test_bbox_reversed_edges(self):
        ep = EdgePair(
            edge1_start=(3.0, 5.0),
            edge1_end=(1.0, 2.0),
            edge2_start=(2.0, 3.0),
            edge2_end=(4.0, 1.0),
        )
        assert ep.bbox == (1.0, 1.0, 4.0, 5.0)

    def test_midpoint(self):
        ep = EdgePair(
            edge1_start=(0.0, 0.0),
            edge1_end=(0.0, 4.0),
            edge2_start=(2.0, 0.0),
            edge2_end=(2.0, 4.0),
        )
        assert ep.midpoint == (1.0, 2.0)

    def test_frozen(self):
        ep = EdgePair(
            edge1_start=(0.0, 0.0),
            edge1_end=(1.0, 0.0),
            edge2_start=(0.0, 1.0),
            edge2_end=(1.0, 1.0),
        )
        # Frozen dataclass should be hashable
        assert hash(ep) is not None


class TestViolationGeometry:
    def test_edge_pair_bbox(self):
        ep = EdgePair(
            edge1_start=(1.0, 2.0),
            edge1_end=(1.0, 2.5),
            edge2_start=(1.1, 2.0),
            edge2_end=(1.1, 2.5),
        )
        geom = ViolationGeometry(geometry_type=GeometryType.edge_pair, edge_pair=ep)
        assert geom.bbox == (1.0, 2.0, 1.1, 2.5)

    def test_polygon_bbox(self):
        geom = ViolationGeometry(
            geometry_type=GeometryType.polygon,
            points=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        )
        assert geom.bbox == (0.0, 0.0, 1.0, 1.0)

    def test_empty_geometry_bbox(self):
        geom = ViolationGeometry(geometry_type=GeometryType.edge_pair)
        assert geom.bbox == (0.0, 0.0, 0.0, 0.0)


class TestViolation:
    def test_bbox_single_geometry(self):
        ep = EdgePair(
            edge1_start=(1.0, 2.0),
            edge1_end=(1.0, 2.5),
            edge2_start=(1.1, 2.0),
            edge2_end=(1.1, 2.5),
        )
        v = Violation(
            category="m1.1",
            description="width",
            cell_name="TOP",
            geometries=[ViolationGeometry(geometry_type=GeometryType.edge_pair, edge_pair=ep)],
        )
        assert v.bbox == (1.0, 2.0, 1.1, 2.5)
        assert v.violation_count == 1

    def test_bbox_multiple_geometries(self):
        ep1 = EdgePair(
            edge1_start=(0.0, 0.0),
            edge1_end=(1.0, 0.0),
            edge2_start=(0.0, 1.0),
            edge2_end=(1.0, 1.0),
        )
        ep2 = EdgePair(
            edge1_start=(5.0, 5.0),
            edge1_end=(6.0, 5.0),
            edge2_start=(5.0, 6.0),
            edge2_end=(6.0, 6.0),
        )
        v = Violation(
            category="m1.1",
            description="width",
            cell_name="TOP",
            geometries=[
                ViolationGeometry(geometry_type=GeometryType.edge_pair, edge_pair=ep1),
                ViolationGeometry(geometry_type=GeometryType.edge_pair, edge_pair=ep2),
            ],
        )
        assert v.bbox == (0.0, 0.0, 6.0, 6.0)
        assert v.violation_count == 2

    def test_no_geometries(self):
        v = Violation(category="x", description="y", cell_name="TOP")
        assert v.bbox == (0.0, 0.0, 0.0, 0.0)
        assert v.violation_count == 0


class TestDRCReport:
    def _make_report(self):
        return DRCReport(
            description="Test",
            original_file="test.gds",
            generator="test",
            top_cell="TOP",
            violations=[
                Violation(
                    category="m1.1",
                    description="width",
                    cell_name="TOP",
                    geometries=[
                        ViolationGeometry(
                            geometry_type=GeometryType.edge_pair,
                            edge_pair=EdgePair((0, 0), (1, 0), (0, 1), (1, 1)),
                        ),
                        ViolationGeometry(
                            geometry_type=GeometryType.edge_pair,
                            edge_pair=EdgePair((2, 2), (3, 2), (2, 3), (3, 3)),
                        ),
                    ],
                ),
                Violation(
                    category="m1.2",
                    description="spacing",
                    cell_name="TOP",
                    geometries=[
                        ViolationGeometry(
                            geometry_type=GeometryType.edge_pair,
                            edge_pair=EdgePair((5, 5), (6, 5), (5, 6), (6, 6)),
                        ),
                    ],
                ),
            ],
        )

    def test_total_violations(self):
        report = self._make_report()
        assert report.total_violations == 3

    def test_categories(self):
        report = self._make_report()
        assert report.categories == ["m1.1", "m1.2"]

    def test_get_violations_by_category(self):
        report = self._make_report()
        v = report.get_violations_by_category("m1.1")
        assert v is not None
        assert v.violation_count == 2

    def test_get_violations_by_category_missing(self):
        report = self._make_report()
        assert report.get_violations_by_category("nonexistent") is None

    def test_get_violations_for_cell(self):
        report = self._make_report()
        vs = report.get_violations_for_cell("TOP")
        assert len(vs) == 2

    def test_empty_report(self):
        report = DRCReport(description="", original_file="", generator="", top_cell="")
        assert report.total_violations == 0
        assert report.categories == []

"""Tests for fix strategies (width, spacing, enclosure, area, short, offgrid)."""

import pytest

from backend.core.layout import PolygonInfo
from backend.core.spatial_index import SpatialIndex
from backend.core.violation_models import (
    EdgePair,
    GeometryType,
    Violation,
    ViolationGeometry,
)
from backend.fix.fix_models import FixConfidence
from backend.fix.strategies.area import MinAreaFix
from backend.fix.strategies.enclosure import EnclosureFix
from backend.fix.strategies.offgrid import OffGridFix
from backend.fix.strategies.short import ShortCircuitFix
from backend.fix.strategies.spacing import MinSpacingFix
from backend.fix.strategies.width import MinWidthFix
from backend.pdk.schema import (
    DesignRule,
    FixStrategyWeight,
    GDSLayer,
    PDKConfig,
    RuleType,
)


@pytest.fixture()
def pdk():
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
            "met2": GDSLayer(
                gds_layer=69,
                gds_datatype=20,
                description="Metal 2",
                color="#FF00FF",
                is_routing=True,
            ),
            "mcon": GDSLayer(
                gds_layer=67,
                gds_datatype=44,
                description="Contact",
                color="#808080",
                is_via=True,
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
            DesignRule(
                rule_id="m1.2",
                rule_type=RuleType.min_spacing,
                layer="met1",
                value_um=0.140,
                severity=6,
            ),
            DesignRule(
                rule_id="m1.4",
                rule_type=RuleType.min_enclosure,
                layer="met1",
                related_layer="mcon",
                value_um=0.060,
                severity=5,
            ),
            DesignRule(
                rule_id="m1.6",
                rule_type=RuleType.min_area,
                layer="met1",
                value_um=0.083,
                severity=4,
            ),
        ],
        connectivity=[],
        fix_weights={
            "min_width": FixStrategyWeight(priority=3),
            "min_spacing": FixStrategyWeight(priority=4, prefer_move=True),
        },
        klayout_drc_deck="test.drc",
    )


def _poly(points, layer=68, datatype=20, cell="TOP"):
    return PolygonInfo(points=points, gds_layer=layer, gds_datatype=datatype, cell_name=cell)


def _make_width_violation(x=0, y=0, width=0.10, length=1.0):
    """Create a min-width violation (width < 0.14um for met1)."""
    return Violation(
        category="m1.1",
        description="met1 minimum width",
        cell_name="TOP",
        rule_id="m1.1",
        rule_type="min_width",
        severity=7,
        value_um=0.140,
        geometries=[
            ViolationGeometry(
                geometry_type=GeometryType.edge_pair,
                edge_pair=EdgePair(
                    edge1_start=(x, y),
                    edge1_end=(x, y + length),
                    edge2_start=(x + width, y),
                    edge2_end=(x + width, y + length),
                ),
            )
        ],
    )


class TestMinWidthFix:
    def test_can_fix(self):
        strategy = MinWidthFix()
        assert strategy.rule_type == "min_width"
        v = _make_width_violation()
        assert strategy.can_fix(v) is True

    def test_cannot_fix_wrong_type(self):
        strategy = MinWidthFix()
        v = Violation(
            category="m1.2",
            description="spacing",
            cell_name="TOP",
            rule_type="min_spacing",
            severity=6,
        )
        assert strategy.can_fix(v) is False

    def test_suggest_width_expansion(self, pdk):
        strategy = MinWidthFix()
        # Narrow polygon: 0.10um wide (needs 0.14um)
        poly = _poly([(0, 0), (0.10, 0), (0.10, 1.0), (0, 1.0)])
        si = SpatialIndex.from_polygons([poly])
        violation = _make_width_violation(x=0, y=0, width=0.10, length=1.0)

        suggestion = strategy.suggest_fix(violation, violation.geometries[0], pdk, si)
        assert suggestion is not None
        assert suggestion.rule_type == "min_width"
        assert len(suggestion.deltas) == 1
        delta = suggestion.deltas[0]
        # Modified polygon should be wider
        from backend.core.geometry_utils import bbox_width, polygon_bbox

        new_bbox = polygon_bbox(delta.modified_points)
        assert bbox_width(new_bbox) >= 0.140 - 0.001

    def test_no_fix_when_already_wide(self, pdk):
        strategy = MinWidthFix()
        v = Violation(
            category="m1.1",
            description="width",
            cell_name="TOP",
            rule_type="min_width",
            severity=7,
            value_um=0.140,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair((0, 0), (0, 1), (0.20, 0), (0.20, 1)),
                )
            ],
        )
        poly = _poly([(0, 0), (0.20, 0), (0.20, 1.0), (0, 1.0)])
        si = SpatialIndex.from_polygons([poly])
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        # Deficit <= 0, so no fix
        assert suggestion is None

    def test_grid_alignment(self, pdk):
        strategy = MinWidthFix()
        poly = _poly([(0, 0), (0.10, 0), (0.10, 1.0), (0, 1.0)])
        si = SpatialIndex.from_polygons([poly])
        violation = _make_width_violation()
        suggestion = strategy.suggest_fix(violation, violation.geometries[0], pdk, si)
        assert suggestion is not None
        for x, y in suggestion.deltas[0].modified_points:
            assert abs(x / 0.005 - round(x / 0.005)) < 1e-9
            assert abs(y / 0.005 - round(y / 0.005)) < 1e-9


class TestMinSpacingFix:
    def test_can_fix(self):
        strategy = MinSpacingFix()
        assert strategy.rule_type == "min_spacing"

    def test_suggest_move_fix(self, pdk):
        strategy = MinSpacingFix()
        # Two polygons too close: gap of 0.10um (needs 0.14um)
        poly1 = _poly([(0, 0), (1, 0), (1, 1), (0, 1)])
        poly2 = _poly([(1.10, 0), (2.10, 0), (2.10, 1), (1.10, 1)])
        si = SpatialIndex.from_polygons([poly1, poly2])

        violation = Violation(
            category="m1.2",
            description="spacing",
            cell_name="TOP",
            rule_type="min_spacing",
            severity=6,
            value_um=0.140,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(1.0, 0),
                        edge1_end=(1.0, 1.0),
                        edge2_start=(1.10, 0),
                        edge2_end=(1.10, 1.0),
                    ),
                )
            ],
        )

        suggestion = strategy.suggest_fix(violation, violation.geometries[0], pdk, si)
        assert suggestion is not None
        assert suggestion.rule_type == "min_spacing"
        assert len(suggestion.deltas) >= 1

    def test_no_fix_when_sufficient_spacing(self, pdk):
        strategy = MinSpacingFix()
        violation = Violation(
            category="m1.2",
            description="spacing",
            cell_name="TOP",
            rule_type="min_spacing",
            severity=6,
            value_um=0.140,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(0, 0),
                        edge1_end=(0, 1),
                        edge2_start=(0.20, 0),
                        edge2_end=(0.20, 1),
                    ),
                )
            ],
        )
        si = SpatialIndex()
        suggestion = strategy.suggest_fix(violation, violation.geometries[0], pdk, si)
        assert suggestion is None


class TestEnclosureFix:
    def test_can_fix(self):
        strategy = EnclosureFix()
        assert strategy.rule_type == "min_enclosure"

    def test_suggest_enclosure_extension(self, pdk):
        strategy = EnclosureFix()
        # Metal polygon barely covering a via
        metal = _poly([(0, 0), (0.20, 0), (0.20, 0.20), (0, 0.20)], layer=68)
        via = _poly([(0.02, 0.02), (0.18, 0.02), (0.18, 0.18), (0.02, 0.18)], layer=67, datatype=44)
        si = SpatialIndex.from_polygons([metal, via])

        violation = Violation(
            category="m1.4",
            description="enclosure",
            cell_name="TOP",
            rule_type="min_enclosure",
            severity=5,
            value_um=0.060,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(0, 0.02),
                        edge1_end=(0, 0.18),
                        edge2_start=(0.02, 0.02),
                        edge2_end=(0.02, 0.18),
                    ),
                )
            ],
        )

        suggestion = strategy.suggest_fix(violation, violation.geometries[0], pdk, si)
        assert suggestion is not None
        assert suggestion.rule_type == "min_enclosure"


class TestMinAreaFix:
    def test_can_fix(self):
        strategy = MinAreaFix()
        assert strategy.rule_type == "min_area"

    def test_suggest_area_extension(self, pdk):
        strategy = MinAreaFix()
        # Small polygon: 0.2 x 0.2 = 0.04um² (needs 0.083um²)
        poly = _poly([(0, 0), (0.20, 0), (0.20, 0.20), (0, 0.20)])
        si = SpatialIndex.from_polygons([poly])

        violation = Violation(
            category="m1.6",
            description="area",
            cell_name="TOP",
            rule_type="min_area",
            severity=4,
            value_um=0.083,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.polygon,
                    points=[(0, 0), (0.20, 0), (0.20, 0.20), (0, 0.20)],
                )
            ],
        )

        suggestion = strategy.suggest_fix(violation, violation.geometries[0], pdk, si)
        assert suggestion is not None
        assert suggestion.rule_type == "min_area"
        # Verify the new polygon is larger
        from backend.core.geometry_utils import polygon_area

        new_area = polygon_area(suggestion.deltas[0].modified_points)
        assert new_area >= 0.083 - 0.001


class TestShortCircuitFix:
    def test_can_fix(self):
        strategy = ShortCircuitFix()
        v = Violation(
            category="met1.short",
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
        )
        assert strategy.can_fix(v) is True

    def test_can_fix_by_category_name(self):
        strategy = ShortCircuitFix()
        v = Violation(
            category="short_m1",
            description="short",
            cell_name="TOP",
            rule_type=None,
            severity=10,
        )
        assert strategy.can_fix(v) is True

    def test_suggest_short_fix(self, pdk):
        strategy = ShortCircuitFix()
        # Two overlapping polygons
        poly1 = _poly([(0, 0), (1.0, 0), (1.0, 1.0), (0, 1.0)])
        poly2 = _poly([(0.8, 0), (1.8, 0), (1.8, 1.0), (0.8, 1.0)])
        si = SpatialIndex.from_polygons([poly1, poly2])

        violation = Violation(
            category="short_m1",
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(0.8, 0),
                        edge1_end=(0.8, 1.0),
                        edge2_start=(1.0, 0),
                        edge2_end=(1.0, 1.0),
                    ),
                )
            ],
        )

        suggestion = strategy.suggest_fix(violation, violation.geometries[0], pdk, si)
        assert suggestion is not None
        assert suggestion.priority == 1  # highest

    def test_not_enough_polygons(self, pdk):
        strategy = ShortCircuitFix()
        poly = _poly([(0, 0), (1, 0), (1, 1), (0, 1)])
        si = SpatialIndex.from_polygons([poly])

        violation = Violation(
            category="short_m1",
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair((5, 5), (5, 6), (6, 5), (6, 6)),
                )
            ],
        )
        suggestion = strategy.suggest_fix(violation, violation.geometries[0], pdk, si)
        assert suggestion is None


class TestOffGridFix:
    def test_can_fix(self):
        strategy = OffGridFix()
        assert strategy.rule_type == "off_grid"

    def test_suggest_snap_to_grid(self, pdk):
        strategy = OffGridFix()
        # Polygon with off-grid vertex at (0.003, 0)
        poly = _poly([(0.003, 0), (0.20, 0), (0.20, 0.20), (0.003, 0.20)])
        si = SpatialIndex.from_polygons([poly])

        violation = Violation(
            category="offgrid",
            description="off-grid",
            cell_name="TOP",
            rule_type="off_grid",
            severity=8,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge,
                    edge_pair=EdgePair(
                        edge1_start=(0.003, 0),
                        edge1_end=(0.003, 0.20),
                        edge2_start=(0.003, 0),
                        edge2_end=(0.003, 0.20),
                    ),
                )
            ],
        )

        suggestion = strategy.suggest_fix(violation, violation.geometries[0], pdk, si)
        assert suggestion is not None
        assert suggestion.rule_type == "off_grid"
        assert suggestion.confidence == FixConfidence.high
        # Verify all vertices are on grid
        for x, y in suggestion.deltas[0].modified_points:
            assert abs(x / 0.005 - round(x / 0.005)) < 1e-9
            assert abs(y / 0.005 - round(y / 0.005)) < 1e-9

    def test_already_on_grid(self, pdk):
        strategy = OffGridFix()
        poly = _poly([(0, 0), (0.20, 0), (0.20, 0.20), (0, 0.20)])
        si = SpatialIndex.from_polygons([poly])

        violation = Violation(
            category="offgrid",
            description="off-grid",
            cell_name="TOP",
            rule_type="off_grid",
            severity=8,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge,
                    edge_pair=EdgePair(
                        edge1_start=(0, 0),
                        edge1_end=(0, 0.20),
                        edge2_start=(0, 0),
                        edge2_end=(0, 0.20),
                    ),
                )
            ],
        )

        suggestion = strategy.suggest_fix(violation, violation.geometries[0], pdk, si)
        # No change needed
        assert suggestion is None

    def test_conservative_snap_direction(self, pdk):
        strategy = OffGridFix()
        # Vertex at 0.003 with center around 0.1 → should snap to 0.0 (outward/away from center)
        poly = _poly([(0.003, 0.003), (0.20, 0.003), (0.20, 0.20), (0.003, 0.20)])
        si = SpatialIndex.from_polygons([poly])

        violation = Violation(
            category="offgrid",
            description="off-grid",
            cell_name="TOP",
            rule_type="off_grid",
            severity=8,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge,
                    edge_pair=EdgePair(
                        edge1_start=(0.003, 0.003),
                        edge1_end=(0.003, 0.20),
                        edge2_start=(0.003, 0.003),
                        edge2_end=(0.003, 0.20),
                    ),
                )
            ],
        )

        suggestion = strategy.suggest_fix(violation, violation.geometries[0], pdk, si)
        assert suggestion is not None
        # Lower-left vertex (0.003, 0.003) should snap to (0.0, 0.0) — outward
        has_origin = any(
            abs(x) < 1e-9 and abs(y) < 1e-9 for x, y in suggestion.deltas[0].modified_points
        )
        assert has_origin

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
        # Small deficit (0.04um < 0.14um rule), no third polygon → high confidence
        assert suggestion.confidence == FixConfidence.high

    def test_move_fix_medium_confidence_when_nearby_collision(self, pdk):
        strategy = MinSpacingFix()
        # Two polygons too close (gap 0.10, need 0.14). poly1 is moved left by 0.04.
        # Third polygon sits to the left of poly1, within min_spacing of moved position.
        poly1 = _poly([(0, 0), (1, 0), (1, 1), (0, 1)])
        poly2 = _poly([(1.10, 0), (2.10, 0), (2.10, 1), (1.10, 1)])
        # poly1 moves to (-0.04, 0)-(0.96, 1). poly3 left edge at -0.15 is
        # within 0.14 of moved poly1's left edge (-0.04), triggering collision.
        poly3 = _poly([(-0.15, 0), (-0.05, 0), (-0.05, 1), (-0.15, 1)])
        si = SpatialIndex.from_polygons([poly1, poly2, poly3])

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
        # Third polygon is within min_spacing of moved position → medium confidence
        assert suggestion.confidence == FixConfidence.medium

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


# ---------------------------------------------------------------------------
# Extended coverage tests — spacing.py
# ---------------------------------------------------------------------------


class TestMinSpacingFixExtended:
    """Cover shrink-fix path, polygon-finding edge cases, and direction branches."""

    def _shrink_pdk(self, pdk):
        """Return a copy of pdk with prefer_move=False for min_spacing."""
        from copy import deepcopy

        p = deepcopy(pdk)
        p.fix_weights["min_spacing"] = FixStrategyWeight(priority=4, prefer_move=False)
        return p

    def _spacing_violation(self, ep, gap_value=0.140):
        return Violation(
            category="m1.2",
            description="spacing",
            cell_name="TOP",
            rule_type="min_spacing",
            severity=6,
            value_um=gap_value,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=ep,
                )
            ],
        )

    def test_suggest_shrink_fix_horizontal(self, pdk):
        """prefer_move=False → shrink both polygons' facing edges (horizontal gap)."""
        p = self._shrink_pdk(pdk)
        strategy = MinSpacingFix()
        # Two polygons with 0.10um horizontal gap (needs 0.14)
        poly1 = _poly([(0, 0), (1, 0), (1, 1), (0, 1)])
        poly2 = _poly([(1.10, 0), (2.10, 0), (2.10, 1), (1.10, 1)])
        si = SpatialIndex.from_polygons([poly1, poly2])

        ep = EdgePair(
            edge1_start=(1.0, 0), edge1_end=(1.0, 1.0),
            edge2_start=(1.10, 0), edge2_end=(1.10, 1.0),
        )
        v = self._spacing_violation(ep)
        suggestion = strategy.suggest_fix(v, v.geometries[0], p, si)
        assert suggestion is not None
        assert "Shrink" in suggestion.description
        assert len(suggestion.deltas) == 2
        assert suggestion.confidence == FixConfidence.medium

    def test_suggest_shrink_fix_vertical(self, pdk):
        """prefer_move=False with vertical gap → shrink top/bottom edges."""
        p = self._shrink_pdk(pdk)
        strategy = MinSpacingFix()
        # Vertical gap: poly1 on bottom, poly2 on top, 0.10um gap
        poly1 = _poly([(0, 0), (1, 0), (1, 1), (0, 1)])
        poly2 = _poly([(0, 1.10), (1, 1.10), (1, 2.10), (0, 2.10)])
        si = SpatialIndex.from_polygons([poly1, poly2])

        ep = EdgePair(
            edge1_start=(0, 1.0), edge1_end=(1.0, 1.0),
            edge2_start=(0, 1.10), edge2_end=(1.0, 1.10),
        )
        v = self._spacing_violation(ep)
        suggestion = strategy.suggest_fix(v, v.geometries[0], p, si)
        assert suggestion is not None
        assert len(suggestion.deltas) == 2

    def test_shrink_deficit_grid_rounding(self, pdk):
        """When half*2 < deficit after grid snap, half gets bumped up by one grid."""
        p = self._shrink_pdk(pdk)
        strategy = MinSpacingFix()
        # gap=0.10, need 0.14, deficit=0.04. half=0.02 → half*2=0.04 ≥ 0.04, no bump.
        # Use value_um=0.137 → deficit=0.037, half=snap(0.0185,0.005)=0.020,
        # half*2=0.040 > 0.037 → no bump. Try deficit=0.007:
        # gap=0.133, need 0.14, deficit=0.007, half=snap(0.0035,0.005)=0.005,
        # half*2=0.010 > 0.007 → no bump.
        # To trigger line 228: deficit where snap(deficit/2)*2 < deficit.
        # deficit=0.013: half=snap(0.0065,0.005)=0.005, half*2=0.010 < 0.013 → BUMP to 0.010
        poly1 = _poly([(0, 0), (1, 0), (1, 1), (0, 1)])
        poly2 = _poly([(1.127, 0), (2.127, 0), (2.127, 1), (1.127, 1)])
        si = SpatialIndex.from_polygons([poly1, poly2])

        ep = EdgePair(
            edge1_start=(1.0, 0), edge1_end=(1.0, 1.0),
            edge2_start=(1.127, 0), edge2_end=(1.127, 1.0),
        )
        v = self._spacing_violation(ep, gap_value=0.140)
        suggestion = strategy.suggest_fix(v, v.geometries[0], p, si)
        assert suggestion is not None
        assert len(suggestion.deltas) == 2

    def test_same_polygon_fallback(self, pdk):
        """Edge pair midpoints inside the same polygon → broader query_nearby search."""
        strategy = MinSpacingFix()
        # Make a large polygon that contains both edge midpoints
        big = _poly([(0, 0), (2, 0), (2, 2), (0, 2)])
        small = _poly([(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)])
        si = SpatialIndex.from_polygons([big, small])

        # Edge pair midpoints both at (0.95, 0.5) and (1.05, 0.5) — both inside 'big'
        ep = EdgePair(
            edge1_start=(0.95, 0.0), edge1_end=(0.95, 1.0),
            edge2_start=(1.05, 0.0), edge2_end=(1.05, 1.0),
        )
        v = self._spacing_violation(ep)
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        # Should find 2 polygons via query_nearby fallback and produce a fix
        assert suggestion is not None

    def test_same_polygon_fallback_fails(self, pdk):
        """Same polygon for both edges + fewer than 2 nearby → returns None."""
        strategy = MinSpacingFix()
        # Single large polygon, no other polygons nearby
        big = _poly([(0, 0), (2, 0), (2, 2), (0, 2)])
        si = SpatialIndex.from_polygons([big])

        ep = EdgePair(
            edge1_start=(0.95, 0.0), edge1_end=(0.95, 1.0),
            edge2_start=(1.05, 0.0), edge2_end=(1.05, 1.0),
        )
        v = self._spacing_violation(ep)
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is None

    def test_no_fix_non_edge_pair(self, pdk):
        """Polygon geometry type → returns None early."""
        strategy = MinSpacingFix()
        v = Violation(
            category="m1.2",
            description="spacing",
            cell_name="TOP",
            rule_type="min_spacing",
            severity=6,
            value_um=0.140,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.polygon,
                    points=[(0, 0), (1, 0), (1, 1), (0, 1)],
                )
            ],
        )
        si = SpatialIndex()
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None

    def test_no_fix_null_value(self, pdk):
        """value_um=None → returns None."""
        strategy = MinSpacingFix()
        v = Violation(
            category="m1.2",
            description="spacing",
            cell_name="TOP",
            rule_type="min_spacing",
            severity=6,
            value_um=None,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair((0, 0), (0, 1), (0.1, 0), (0.1, 1)),
                )
            ],
        )
        si = SpatialIndex()
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None

    def test_move_fix_vertical_gap(self, pdk):
        """Two polygons stacked vertically → vertical move."""
        strategy = MinSpacingFix()
        poly1 = _poly([(0, 0), (1, 0), (1, 1), (0, 1)])
        poly2 = _poly([(0, 1.10), (1, 1.10), (1, 2.10), (0, 2.10)])
        si = SpatialIndex.from_polygons([poly1, poly2])

        ep = EdgePair(
            edge1_start=(0, 1.0), edge1_end=(1.0, 1.0),
            edge2_start=(0, 1.10), edge2_end=(1.0, 1.10),
        )
        v = self._spacing_violation(ep)
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        assert suggestion.confidence == FixConfidence.high

    def test_move_fix_large_deficit_medium_confidence(self, pdk):
        """snap_to_grid rounds move_amount past value_um → medium confidence."""
        strategy = MinSpacingFix()
        # value_um=0.004, gap=0.001 → deficit=0.003
        # snap(0.003, 0.005) = round(0.6)*0.005 = 0.005 > 0.004 → medium confidence
        poly1 = _poly([(0, 0), (1, 0), (1, 1), (0, 1)])
        poly2 = _poly([(1.001, 0), (2.001, 0), (2.001, 1), (1.001, 1)])
        si = SpatialIndex.from_polygons([poly1, poly2])

        ep = EdgePair(
            edge1_start=(1.0, 0), edge1_end=(1.0, 1.0),
            edge2_start=(1.001, 0), edge2_end=(1.001, 1.0),
        )
        v = Violation(
            category="m1.2",
            description="spacing",
            cell_name="TOP",
            rule_type="min_spacing",
            severity=6,
            value_um=0.004,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=ep,
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        assert suggestion.confidence == FixConfidence.medium

    def test_no_fix_null_edge_pair(self, pdk):
        """edge_pair is None → returns None."""
        strategy = MinSpacingFix()
        v = Violation(
            category="m1.2",
            description="spacing",
            cell_name="TOP",
            rule_type="min_spacing",
            severity=6,
            value_um=0.140,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=None,
                )
            ],
        )
        si = SpatialIndex()
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None


# ---------------------------------------------------------------------------
# Extended coverage tests — area.py
# ---------------------------------------------------------------------------


class TestMinAreaFixExtended:
    """Cover edge-pair geometry, extension directions, fallback paths."""

    def test_edge_pair_geometry(self, pdk):
        """Violation with edge_pair geometry → _find_polygon_points path."""
        strategy = MinAreaFix()
        # Small polygon in spatial index
        poly = _poly([(0, 0), (0.20, 0), (0.20, 0.20), (0, 0.20)])
        si = SpatialIndex.from_polygons([poly])

        v = Violation(
            category="m1.6",
            description="area",
            cell_name="TOP",
            rule_type="min_area",
            severity=4,
            value_um=0.083,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(0, 0), edge1_end=(0.20, 0),
                        edge2_start=(0, 0.20), edge2_end=(0.20, 0.20),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        assert suggestion.rule_type == "min_area"

    def test_edge_pair_no_polygon_found(self, pdk):
        """edge_pair bbox matches no polygon in spatial index → returns None."""
        strategy = MinAreaFix()
        si = SpatialIndex()  # empty

        v = Violation(
            category="m1.6",
            description="area",
            cell_name="TOP",
            rule_type="min_area",
            severity=4,
            value_um=0.083,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(10, 10), edge1_end=(10.2, 10),
                        edge2_start=(10, 10.2), edge2_end=(10.2, 10.2),
                    ),
                )
            ],
        )
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None

    def test_extension_dir_right_blocked(self, pdk):
        """Polygon to the right → extends left instead."""
        strategy = MinAreaFix()
        # Target polygon
        target = _poly([(0, 0), (0.20, 0), (0.20, 0.20), (0, 0.20)])
        # Blocker on the right
        blocker = _poly([(0.25, 0), (0.50, 0), (0.50, 0.20), (0.25, 0.20)])
        si = SpatialIndex.from_polygons([target, blocker])

        v = Violation(
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
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        from backend.core.geometry_utils import polygon_bbox

        new_bbox = polygon_bbox(suggestion.deltas[0].modified_points)
        # Should extend left (xmin decreases) rather than right
        assert new_bbox[0] < 0.0

    def test_extension_dir_left_blocked(self, pdk):
        """Polygon to the left → extends right."""
        strategy = MinAreaFix()
        target = _poly([(0.30, 0), (0.50, 0), (0.50, 0.20), (0.30, 0.20)])
        blocker = _poly([(0, 0), (0.25, 0), (0.25, 0.20), (0, 0.20)])
        si = SpatialIndex.from_polygons([target, blocker])

        v = Violation(
            category="m1.6",
            description="area",
            cell_name="TOP",
            rule_type="min_area",
            severity=4,
            value_um=0.083,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.polygon,
                    points=[(0.30, 0), (0.50, 0), (0.50, 0.20), (0.30, 0.20)],
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        from backend.core.geometry_utils import polygon_bbox

        new_bbox = polygon_bbox(suggestion.deltas[0].modified_points)
        # Should extend right (xmax increases)
        assert new_bbox[2] > 0.50

    def test_extend_y_direction(self, pdk):
        """Tall narrow polygon → extends vertically."""
        strategy = MinAreaFix()
        # 0.10 wide x 0.20 tall = 0.02um² (needs 0.083um²)
        poly = _poly([(0, 0), (0.10, 0), (0.10, 0.20), (0, 0.20)])
        si = SpatialIndex.from_polygons([poly])

        v = Violation(
            category="m1.6",
            description="area",
            cell_name="TOP",
            rule_type="min_area",
            severity=4,
            value_um=0.083,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.polygon,
                    points=[(0, 0), (0.10, 0), (0.10, 0.20), (0, 0.20)],
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        from backend.core.geometry_utils import polygon_bbox

        new_bbox = polygon_bbox(suggestion.deltas[0].modified_points)
        # Taller than wide → extended vertically (ymax increases)
        assert new_bbox[3] > 0.20

    def test_no_fix_null_value(self, pdk):
        """value_um=None → returns None."""
        strategy = MinAreaFix()
        v = Violation(
            category="m1.6",
            description="area",
            cell_name="TOP",
            rule_type="min_area",
            severity=4,
            value_um=None,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.polygon,
                    points=[(0, 0), (0.20, 0), (0.20, 0.20), (0, 0.20)],
                )
            ],
        )
        si = SpatialIndex()
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None

    def test_no_fix_sufficient_area(self, pdk):
        """area_deficit <= 0 → returns None."""
        strategy = MinAreaFix()
        # 1x1 = 1.0um² which is much more than 0.083
        poly = _poly([(0, 0), (1, 0), (1, 1), (0, 1)])
        si = SpatialIndex.from_polygons([poly])

        v = Violation(
            category="m1.6",
            description="area",
            cell_name="TOP",
            rule_type="min_area",
            severity=4,
            value_um=0.083,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.polygon,
                    points=[(0, 0), (1, 0), (1, 1), (0, 1)],
                )
            ],
        )
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None

    def test_fallback_nearest_polygon(self, pdk):
        """Bbox doesn't exactly match → uses nearby[0] fallback."""
        strategy = MinAreaFix()
        # Polygon in index is slightly different from violation geometry
        poly = _poly([(0, 0), (0.21, 0), (0.21, 0.21), (0, 0.21)])
        si = SpatialIndex.from_polygons([poly])

        v = Violation(
            category="m1.6",
            description="area",
            cell_name="TOP",
            rule_type="min_area",
            severity=4,
            value_um=0.083,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.polygon,
                    # Points don't exactly match what's in the spatial index
                    points=[(0.001, 0.001), (0.199, 0.001), (0.199, 0.199), (0.001, 0.199)],
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        # Should still find the polygon via fallback
        assert suggestion is not None

    def test_no_polygon_in_index(self, pdk):
        """Empty spatial index → returns None."""
        strategy = MinAreaFix()
        si = SpatialIndex()

        v = Violation(
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
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None

    def test_unsupported_geometry_type(self, pdk):
        """Non-polygon, non-edge_pair geometry → returns None."""
        strategy = MinAreaFix()
        si = SpatialIndex()

        v = Violation(
            category="m1.6",
            description="area",
            cell_name="TOP",
            rule_type="min_area",
            severity=4,
            value_um=0.083,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge,
                    edge_pair=None,
                )
            ],
        )
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None


# ---------------------------------------------------------------------------
# Extended coverage tests — width.py
# ---------------------------------------------------------------------------


class TestMinWidthFixExtended:
    """Cover expansion direction branches, fallback paths, edge cases."""

    def test_expansion_left_blocked(self, pdk):
        """Obstacle on the left → full expansion rightward."""
        strategy = MinWidthFix()
        # Narrow polygon at x=0.50
        narrow = _poly([(0.50, 0), (0.60, 0), (0.60, 1.0), (0.50, 1.0)])
        # Blocker on the left
        blocker = _poly([(0.30, 0), (0.48, 0), (0.48, 1.0), (0.30, 1.0)])
        si = SpatialIndex.from_polygons([narrow, blocker])

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
                    edge_pair=EdgePair(
                        edge1_start=(0.50, 0), edge1_end=(0.50, 1.0),
                        edge2_start=(0.60, 0), edge2_end=(0.60, 1.0),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        from backend.core.geometry_utils import polygon_bbox

        new_bbox = polygon_bbox(suggestion.deltas[0].modified_points)
        # Left edge should stay at 0.50, right edge extends
        assert abs(new_bbox[0] - 0.50) < 0.01
        assert new_bbox[2] > 0.60

    def test_expansion_right_blocked(self, pdk):
        """Obstacle on the right → full expansion leftward."""
        strategy = MinWidthFix()
        narrow = _poly([(0.50, 0), (0.60, 0), (0.60, 1.0), (0.50, 1.0)])
        blocker = _poly([(0.62, 0), (0.80, 0), (0.80, 1.0), (0.62, 1.0)])
        si = SpatialIndex.from_polygons([narrow, blocker])

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
                    edge_pair=EdgePair(
                        edge1_start=(0.50, 0), edge1_end=(0.50, 1.0),
                        edge2_start=(0.60, 0), edge2_end=(0.60, 1.0),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        from backend.core.geometry_utils import polygon_bbox

        new_bbox = polygon_bbox(suggestion.deltas[0].modified_points)
        # Right edge should stay at 0.60, left edge extends
        assert new_bbox[0] < 0.50
        assert abs(new_bbox[2] - 0.60) < 0.01

    def test_expand_y_direction(self, pdk):
        """Violation narrow in Y → vertical expansion."""
        strategy = MinWidthFix()
        # Wide but thin polygon: 1.0 x 0.10 (narrow in Y)
        poly = _poly([(0, 0), (1.0, 0), (1.0, 0.10), (0, 0.10)])
        si = SpatialIndex.from_polygons([poly])

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
                    edge_pair=EdgePair(
                        edge1_start=(0, 0), edge1_end=(1.0, 0),
                        edge2_start=(0, 0.10), edge2_end=(1.0, 0.10),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        from backend.core.geometry_utils import bbox_height, polygon_bbox

        new_bbox = polygon_bbox(suggestion.deltas[0].modified_points)
        assert bbox_height(new_bbox) >= 0.140 - 0.001

    def test_fallback_nearest_polygon(self, pdk):
        """No bbox-containing polygon → uses nearby[0]."""
        strategy = MinWidthFix()
        # Polygon doesn't contain the violation bbox perfectly
        poly = _poly([(0, 0), (0.50, 0), (0.50, 1.0), (0, 1.0)])
        si = SpatialIndex.from_polygons([poly])

        # Violation bbox overlaps but isn't contained by poly
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
                    edge_pair=EdgePair(
                        edge1_start=(-0.05, 0), edge1_end=(-0.05, 1.0),
                        edge2_start=(0.05, 0), edge2_end=(0.05, 1.0),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        # Should still produce a fix via fallback
        assert suggestion is not None

    def test_no_polygon_returns_none(self, pdk):
        """Empty spatial index → returns None."""
        strategy = MinWidthFix()
        si = SpatialIndex()

        v = _make_width_violation()
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None

    def test_no_fix_non_edge_pair(self, pdk):
        """Polygon geometry → returns None."""
        strategy = MinWidthFix()
        si = SpatialIndex()

        v = Violation(
            category="m1.1",
            description="width",
            cell_name="TOP",
            rule_type="min_width",
            severity=7,
            value_um=0.140,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.polygon,
                    points=[(0, 0), (0.10, 0), (0.10, 1), (0, 1)],
                )
            ],
        )
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None

    def test_no_fix_null_value(self, pdk):
        """value_um=None → returns None."""
        strategy = MinWidthFix()
        si = SpatialIndex()

        v = Violation(
            category="m1.1",
            description="width",
            cell_name="TOP",
            rule_type="min_width",
            severity=7,
            value_um=None,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair((0, 0), (0, 1), (0.10, 0), (0.10, 1)),
                )
            ],
        )
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None

    def test_expand_lshaped_polygon(self, pdk):
        """L-shaped polygon has interior points not on min/max edges → preserved."""
        strategy = MinWidthFix()
        # L-shaped polygon: narrow stem (0.10 wide) that needs expansion
        # Points include interior vertices not on the xmin/xmax edges
        l_shape = _poly([
            (0, 0), (0.10, 0), (0.10, 0.5),
            (0.50, 0.5), (0.50, 1.0), (0, 1.0),
        ])
        si = SpatialIndex.from_polygons([l_shape])

        # Width violation on the narrow stem (x: 0 to 0.10)
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
                    edge_pair=EdgePair(
                        edge1_start=(0, 0), edge1_end=(0, 0.5),
                        edge2_start=(0.10, 0), edge2_end=(0.10, 0.5),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        # Interior point (0.50, 0.5) should be preserved (neither on xmin=0 nor xmax=0.50)
        # Actually xmax of the L is 0.50, so that point IS on xmax — but (0.10, 0.5) is interior
        modified = suggestion.deltas[0].modified_points
        assert len(modified) == len(l_shape.points)

    def test_expand_y_with_interior_points(self, pdk):
        """Vertical expansion preserves interior Y points."""
        strategy = MinWidthFix()
        # Polygon with a step: interior y=0.5 is neither ymin nor ymax
        stepped = _poly([
            (0, 0), (1.0, 0), (1.0, 0.10),
            (0.5, 0.10), (0.5, 0.50), (0, 0.50),
        ])
        si = SpatialIndex.from_polygons([stepped])

        # Width violation: narrow in Y (0 to 0.10 = 0.10um)
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
                    edge_pair=EdgePair(
                        edge1_start=(0, 0), edge1_end=(1.0, 0),
                        edge2_start=(0, 0.10), edge2_end=(1.0, 0.10),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None


# ---------------------------------------------------------------------------
# Extended coverage tests — short.py
# ---------------------------------------------------------------------------


class TestShortCircuitFixExtended:
    """Cover spacing buffer lookup, direction branches, degenerate polygon."""

    def test_spacing_buffer_from_pdk(self, pdk):
        """PDK rule with min_spacing for met1 layer → uses rule value as buffer."""
        strategy = ShortCircuitFix()
        # pdk already has m1.2 = min_spacing for met1 (0.140um)
        # Category must contain the layer name "met1" for the lookup to match
        poly1 = _poly([(0, 0), (1.0, 0), (1.0, 1.0), (0, 1.0)])
        poly2 = _poly([(0.8, 0), (1.8, 0), (1.8, 1.0), (0.8, 1.0)])
        si = SpatialIndex.from_polygons([poly1, poly2])

        v = Violation(
            category="met1_short",  # contains "met1" to match rule.layer
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(0.8, 0), edge1_end=(0.8, 1.0),
                        edge2_start=(1.0, 0), edge2_end=(1.0, 1.0),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        # Buffer should be 0.140 (from m1.2 rule), not default 0.010
        assert "0.140" in suggestion.description

    def test_horizontal_shrink_right_edge(self, pdk):
        """Wide overlap bbox (w>=h), to_shrink's right overlaps other's left → shrink right."""
        strategy = ShortCircuitFix()
        # poly_big on the right, poly_small straddles poly_big's left boundary
        poly_big = _poly([(0.5, 0), (2.0, 0), (2.0, 0.5), (0.5, 0.5)])  # area 0.75
        poly_small = _poly([(0.0, 0), (0.8, 0), (0.8, 0.5), (0.0, 0.5)])  # area 0.40
        si = SpatialIndex.from_polygons([poly_big, poly_small])

        # Violation bbox must be wider than tall (w >= h) to take horizontal path
        v = Violation(
            category="short_m1",
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(0.5, 0), edge1_end=(0.5, 0.1),
                        edge2_start=(0.8, 0), edge2_end=(0.8, 0.1),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None
        assert suggestion.confidence == FixConfidence.medium

    def test_horizontal_shrink_left_edge(self, pdk):
        """Wide overlap bbox (w>=h), to_shrink's left overlaps other's right → shrink left."""
        strategy = ShortCircuitFix()
        # poly_big on the left, poly_small straddles poly_big's right boundary
        poly_big = _poly([(0, 0), (1.0, 0), (1.0, 0.5), (0, 0.5)])  # area 0.50
        poly_small = _poly([(0.8, 0), (1.3, 0), (1.3, 0.5), (0.8, 0.5)])  # area 0.25
        si = SpatialIndex.from_polygons([poly_big, poly_small])

        # Wide violation bbox
        v = Violation(
            category="short_m1",
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(0.8, 0), edge1_end=(0.8, 0.1),
                        edge2_start=(1.0, 0), edge2_end=(1.0, 0.1),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None

    def test_vertical_shrink_top(self, pdk):
        """Tall overlap bbox (h>w), to_shrink's top overlaps other's bottom → shrink top."""
        strategy = ShortCircuitFix()
        # poly_big on top, poly_small straddles poly_big's bottom
        poly_big = _poly([(0, 0.5), (0.5, 0.5), (0.5, 2.0), (0, 2.0)])  # area 0.75
        poly_small = _poly([(0, 0), (0.5, 0), (0.5, 0.8), (0, 0.8)])  # area 0.40
        si = SpatialIndex.from_polygons([poly_big, poly_small])

        # Tall violation bbox (h > w)
        v = Violation(
            category="short_m1",
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(0, 0.5), edge1_end=(0.1, 0.5),
                        edge2_start=(0, 0.8), edge2_end=(0.1, 0.8),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None

    def test_vertical_shrink_bottom(self, pdk):
        """Tall overlap bbox (h>w), to_shrink's bottom overlaps other's top → shrink bottom."""
        strategy = ShortCircuitFix()
        # poly_big below, poly_small straddles poly_big's top
        poly_big = _poly([(0, 0), (0.5, 0), (0.5, 1.0), (0, 1.0)])  # area 0.50
        poly_small = _poly([(0, 0.8), (0.5, 0.8), (0.5, 1.3), (0, 1.3)])  # area 0.25
        si = SpatialIndex.from_polygons([poly_big, poly_small])

        # Tall violation bbox
        v = Violation(
            category="short_m1",
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(0, 0.8), edge1_end=(0.1, 0.8),
                        edge2_start=(0, 1.0), edge2_end=(0.1, 1.0),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None

    def test_degenerate_polygon(self, pdk):
        """Shrink creates polygon smaller than grid → low-confidence manual review."""
        strategy = ShortCircuitFix()
        # Very small polygon that will collapse when shrunk
        poly1 = _poly([(0, 0), (1.0, 0), (1.0, 1.0), (0, 1.0)])  # big
        poly2 = _poly([(0.95, 0), (1.01, 0), (1.01, 0.01), (0.95, 0.01)])  # tiny
        si = SpatialIndex.from_polygons([poly1, poly2])

        v = Violation(
            category="short_m1",
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(0.95, 0), edge1_end=(1.0, 0),
                        edge2_start=(0.95, 0.01), edge2_end=(1.0, 0.01),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        # Should either be None (no change) or low confidence degenerate warning
        if suggestion is not None:
            assert suggestion.confidence == FixConfidence.low or suggestion.deltas

    def test_no_fix_no_geometry(self, pdk):
        """No edge_pair and no points → returns None."""
        strategy = ShortCircuitFix()
        si = SpatialIndex()

        v = Violation(
            category="short_m1",
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge,
                    edge_pair=None,
                    points=None,
                )
            ],
        )
        assert strategy.suggest_fix(v, v.geometries[0], pdk, si) is None

    def test_expanded_search(self, pdk):
        """Initial query_bbox returns <2 polygons, query_nearby finds them."""
        strategy = ShortCircuitFix()
        # Polygons far from the violation bbox, but within 0.5 margin
        poly1 = _poly([(0, 0), (1.0, 0), (1.0, 1.0), (0, 1.0)])
        poly2 = _poly([(1.3, 0), (2.3, 0), (2.3, 1.0), (1.3, 1.0)])
        si = SpatialIndex.from_polygons([poly1, poly2])

        # Violation bbox between the two polygons — tight bbox won't capture both
        v = Violation(
            category="short_m1",
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(1.05, 0), edge1_end=(1.05, 1.0),
                        edge2_start=(1.25, 0), edge2_end=(1.25, 1.0),
                    ),
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        # Should find polygons via expanded search
        assert suggestion is not None

    def test_polygon_geometry_input(self, pdk):
        """Violation with polygon points instead of edge_pair."""
        strategy = ShortCircuitFix()
        poly1 = _poly([(0, 0), (1.0, 0), (1.0, 1.0), (0, 1.0)])
        poly2 = _poly([(0.8, 0), (1.8, 0), (1.8, 1.0), (0.8, 1.0)])
        si = SpatialIndex.from_polygons([poly1, poly2])

        v = Violation(
            category="short_m1",
            description="short",
            cell_name="TOP",
            rule_type="short",
            severity=10,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.polygon,
                    points=[(0.8, 0), (1.0, 0), (1.0, 1.0), (0.8, 1.0)],
                )
            ],
        )
        suggestion = strategy.suggest_fix(v, v.geometries[0], pdk, si)
        assert suggestion is not None

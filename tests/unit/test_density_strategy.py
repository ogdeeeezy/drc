"""Tests for the density fill fix strategy."""

import pytest

from backend.core.layout import PolygonInfo
from backend.core.spatial_index import SpatialIndex
from backend.core.violation_models import (
    GeometryType,
    Violation,
    ViolationGeometry,
)
from backend.fix.strategies.density import DensityFillFix
from backend.pdk.schema import (
    DesignRule,
    GDSLayer,
    PDKConfig,
    RuleType,
)


@pytest.fixture
def pdk():
    return PDKConfig(
        name="test_pdk",
        version="1.0",
        process_node_nm=130,
        grid_um=0.005,
        layers={
            "met1": GDSLayer(
                gds_layer=68,
                gds_datatype=20,
                description="Metal 1",
                color="#0000ff",
                is_routing=True,
            ),
        },
        rules=[
            DesignRule(
                rule_id="m1.w",
                rule_type=RuleType.min_width,
                layer="met1",
                value_um=0.14,
                severity=8,
            ),
            DesignRule(
                rule_id="m1.s",
                rule_type=RuleType.min_spacing,
                layer="met1",
                value_um=0.14,
                severity=7,
            ),
        ],
        connectivity=[],
        fix_weights={},
        klayout_drc_deck="test.drc",
    )


@pytest.fixture
def empty_spatial_index():
    """Spatial index with no polygons — simulates an empty region."""
    return SpatialIndex()


@pytest.fixture
def sparse_spatial_index():
    """Spatial index with one small polygon in a large region."""
    si = SpatialIndex()
    si.insert(
        PolygonInfo(
            points=[(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)],
            gds_layer=68,
            gds_datatype=20,
            cell_name="TOP",
        )
    )
    return si


def _make_density_violation(
    bbox: tuple[float, float, float, float],
    cell_name: str = "TOP",
) -> Violation:
    return Violation(
        category="met1.density",
        description="Metal 1 minimum density violation",
        cell_name=cell_name,
        rule_type="min_density",
        severity=3,
        geometries=[
            ViolationGeometry(
                geometry_type=GeometryType.box,
                points=[
                    (bbox[0], bbox[1]),
                    (bbox[2], bbox[1]),
                    (bbox[2], bbox[3]),
                    (bbox[0], bbox[3]),
                ],
            ),
        ],
    )


class TestDensityFillFix:
    def test_can_fix_by_rule_type(self):
        fix = DensityFillFix()
        v = Violation(
            category="met1.d",
            description="Something",
            cell_name="TOP",
            rule_type="min_density",
        )
        assert fix.can_fix(v)

    def test_can_fix_by_description(self):
        fix = DensityFillFix()
        v = Violation(
            category="met1.d",
            description="Metal density check",
            cell_name="TOP",
        )
        assert fix.can_fix(v)

    def test_cannot_fix_width(self):
        fix = DensityFillFix()
        v = Violation(
            category="met1.1",
            description="Metal 1 minimum width",
            cell_name="TOP",
            rule_type="min_width",
        )
        assert not fix.can_fix(v)

    def test_suggest_fill_empty_region(self, pdk, empty_spatial_index):
        fix = DensityFillFix()
        violation = _make_density_violation((0, 0, 10, 10))
        geom = violation.geometries[0]

        suggestion = fix.suggest_fix(violation, geom, pdk, empty_spatial_index)
        assert suggestion is not None
        assert len(suggestion.deltas) > 0
        assert suggestion.rule_type == "min_density"

        # All deltas should be additions (no originals)
        for d in suggestion.deltas:
            assert d.is_addition
            assert d.gds_layer == 68
            assert d.gds_datatype == 20
            assert len(d.modified_points) == 4

    def test_fill_respects_grid(self, pdk, empty_spatial_index):
        fix = DensityFillFix()
        violation = _make_density_violation((0, 0, 5, 5))
        geom = violation.geometries[0]

        suggestion = fix.suggest_fix(violation, geom, pdk, empty_spatial_index)
        assert suggestion is not None

        # All points should be on the 0.005um grid
        for d in suggestion.deltas:
            for x, y in d.modified_points:
                assert abs(x / 0.005 - round(x / 0.005)) < 1e-9
                assert abs(y / 0.005 - round(y / 0.005)) < 1e-9

    def test_no_fix_for_zero_area(self, pdk, empty_spatial_index):
        fix = DensityFillFix()
        violation = _make_density_violation((0, 0, 0, 0))
        geom = violation.geometries[0]

        suggestion = fix.suggest_fix(violation, geom, pdk, empty_spatial_index)
        assert suggestion is None

    def test_description_includes_density(self, pdk, empty_spatial_index):
        fix = DensityFillFix()
        violation = _make_density_violation((0, 0, 10, 10))
        geom = violation.geometries[0]

        suggestion = fix.suggest_fix(violation, geom, pdk, empty_spatial_index)
        assert suggestion is not None
        desc = suggestion.description.lower()
        assert "density" in desc or "fill" in desc

    def test_name_property(self):
        fix = DensityFillFix()
        assert fix.name == "DensityFillFix"
        assert fix.rule_type == "min_density"

    def test_fill_stops_at_target(self, pdk, empty_spatial_index):
        """Verify fill doesn't produce excessive polygons."""
        fix = DensityFillFix()
        violation = _make_density_violation((0, 0, 100, 100))
        geom = violation.geometries[0]

        suggestion = fix.suggest_fix(violation, geom, pdk, empty_spatial_index)
        assert suggestion is not None

        # Total fill area should approximate target density * region area
        fill_area = sum(
            abs(d.modified_points[1][0] - d.modified_points[0][0])
            * abs(d.modified_points[2][1] - d.modified_points[1][1])
            for d in suggestion.deltas
        )
        region_area = 100 * 100
        density = fill_area / region_area
        # Should be close to 25% target (within one fill square)
        assert 0.20 <= density <= 0.30

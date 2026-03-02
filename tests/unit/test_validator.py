"""Tests for fix pre-validator."""

import pytest

from backend.core.layout import PolygonInfo
from backend.core.spatial_index import SpatialIndex
from backend.fix.fix_models import FixConfidence, FixSuggestion, PolygonDelta
from backend.fix.validator import FixValidator
from backend.pdk.schema import (
    DesignRule,
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
                rule_id="m1.6",
                rule_type=RuleType.min_area,
                layer="met1",
                value_um=0.083,
                severity=4,
            ),
        ],
        connectivity=[],
        fix_weights={},
        klayout_drc_deck="test.drc",
    )


@pytest.fixture()
def spatial_index():
    """Spatial index with a polygon far from the test polygons."""
    polys = [
        PolygonInfo(
            points=[(100, 100), (101, 100), (101, 101), (100, 101)],
            gds_layer=68,
            gds_datatype=20,
            cell_name="TOP",
        ),
    ]
    return SpatialIndex.from_polygons(polys)


class TestFixValidator:
    def test_valid_fix_passes(self, pdk, spatial_index):
        validator = FixValidator(pdk, spatial_index)
        suggestion = FixSuggestion(
            violation_category="m1.1",
            rule_type="min_width",
            description="test",
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=68,
                    gds_datatype=20,
                    original_points=[(0, 0), (0.10, 0), (0.10, 1), (0, 1)],
                    modified_points=[(0, 0), (0.20, 0), (0.20, 1), (0, 1)],
                )
            ],
        )
        result = validator.validate(suggestion)
        assert not result.creates_new_violations
        assert result.confidence in (FixConfidence.high, FixConfidence.medium)

    def test_off_grid_detected(self, pdk, spatial_index):
        validator = FixValidator(pdk, spatial_index)
        suggestion = FixSuggestion(
            violation_category="m1.1",
            rule_type="min_width",
            description="test",
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=68,
                    gds_datatype=20,
                    original_points=[(0, 0), (0.10, 0), (0.10, 1), (0, 1)],
                    modified_points=[(0, 0), (0.143, 0), (0.143, 1), (0, 1)],  # off-grid
                )
            ],
        )
        result = validator.validate(suggestion)
        assert result.creates_new_violations
        assert "off-grid" in result.validation_notes

    def test_degenerate_polygon_detected(self, pdk, spatial_index):
        validator = FixValidator(pdk, spatial_index)
        suggestion = FixSuggestion(
            violation_category="m1.1",
            rule_type="min_width",
            description="test",
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=68,
                    gds_datatype=20,
                    original_points=[(0, 0), (1, 0), (1, 1), (0, 1)],
                    modified_points=[(0, 0), (0, 0), (0, 0)],  # zero area
                )
            ],
        )
        result = validator.validate(suggestion)
        assert result.creates_new_violations

    def test_too_few_vertices_detected(self, pdk, spatial_index):
        validator = FixValidator(pdk, spatial_index)
        suggestion = FixSuggestion(
            violation_category="m1.1",
            rule_type="min_width",
            description="test",
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=68,
                    gds_datatype=20,
                    original_points=[(0, 0), (1, 0), (1, 1), (0, 1)],
                    modified_points=[(0, 0), (1, 0)],
                )
            ],
        )
        result = validator.validate(suggestion)
        assert result.creates_new_violations
        assert "fewer than 3" in result.validation_notes

    def test_width_violation_detected(self, pdk, spatial_index):
        validator = FixValidator(pdk, spatial_index)
        suggestion = FixSuggestion(
            violation_category="test",
            rule_type="min_spacing",
            description="test",
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=68,
                    gds_datatype=20,
                    original_points=[(0, 0), (0.20, 0), (0.20, 1), (0, 1)],
                    # Shrunk too narrow
                    modified_points=[(0, 0), (0.10, 0), (0.10, 1), (0, 1)],
                )
            ],
        )
        result = validator.validate(suggestion)
        assert result.creates_new_violations
        assert "Width" in result.validation_notes or "min" in result.validation_notes.lower()

    def test_removal_always_valid(self, pdk, spatial_index):
        validator = FixValidator(pdk, spatial_index)
        suggestion = FixSuggestion(
            violation_category="test",
            rule_type="short",
            description="test",
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=68,
                    gds_datatype=20,
                    original_points=[(0, 0), (1, 0), (1, 1), (0, 1)],
                    modified_points=[],
                )
            ],
        )
        result = validator.validate(suggestion)
        assert not result.creates_new_violations

    def test_confidence_upgraded(self, pdk, spatial_index):
        validator = FixValidator(pdk, spatial_index)
        suggestion = FixSuggestion(
            violation_category="m1.1",
            rule_type="min_width",
            description="test",
            confidence=FixConfidence.medium,
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=68,
                    gds_datatype=20,
                    original_points=[(0, 0), (0.10, 0), (0.10, 1), (0, 1)],
                    modified_points=[(0, 0), (0.20, 0), (0.20, 1), (0, 1)],
                )
            ],
        )
        result = validator.validate(suggestion)
        assert result.confidence == FixConfidence.high

    def test_unknown_layer(self, pdk, spatial_index):
        """Delta on unknown layer should still pass basic validation."""
        validator = FixValidator(pdk, spatial_index)
        suggestion = FixSuggestion(
            violation_category="test",
            rule_type="min_width",
            description="test",
            deltas=[
                PolygonDelta(
                    cell_name="TOP",
                    gds_layer=999,
                    gds_datatype=0,
                    original_points=[(0, 0), (1, 0), (1, 1), (0, 1)],
                    modified_points=[(0, 0), (2, 0), (2, 1), (0, 1)],
                )
            ],
        )
        result = validator.validate(suggestion)
        assert not result.creates_new_violations

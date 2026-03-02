"""Tests for fix engine orchestrator."""

import pytest

from backend.core.layout import PolygonInfo
from backend.core.spatial_index import SpatialIndex
from backend.core.violation_models import (
    DRCReport,
    EdgePair,
    GeometryType,
    Violation,
    ViolationGeometry,
)
from backend.fix.engine import DEFAULT_PRIORITY, FixEngine, FixEngineResult
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
        fix_weights={
            "min_width": FixStrategyWeight(priority=3),
            "min_spacing": FixStrategyWeight(priority=4),
        },
        klayout_drc_deck="test.drc",
    )


@pytest.fixture()
def spatial_index():
    polys = [
        # A narrow polygon (width violation)
        PolygonInfo(
            points=[(0, 0), (0.10, 0), (0.10, 1.0), (0, 1.0)],
            gds_layer=68,
            gds_datatype=20,
            cell_name="TOP",
        ),
        # A small polygon (area violation)
        PolygonInfo(
            points=[(5, 5), (5.20, 5), (5.20, 5.20), (5, 5.20)],
            gds_layer=68,
            gds_datatype=20,
            cell_name="TOP",
        ),
    ]
    return SpatialIndex.from_polygons(polys)


def _make_report():
    """Create a DRC report with multiple violation types."""
    return DRCReport(
        description="test",
        original_file="test.gds",
        generator="test",
        top_cell="TOP",
        violations=[
            Violation(
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
                            edge1_start=(0, 0),
                            edge1_end=(0, 1.0),
                            edge2_start=(0.10, 0),
                            edge2_end=(0.10, 1.0),
                        ),
                    ),
                ],
            ),
            Violation(
                category="m1.6",
                description="met1 minimum area",
                cell_name="TOP",
                rule_id="m1.6",
                rule_type="min_area",
                severity=4,
                value_um=0.083,
                geometries=[
                    ViolationGeometry(
                        geometry_type=GeometryType.polygon,
                        points=[(5, 5), (5.20, 5), (5.20, 5.20), (5, 5.20)],
                    ),
                ],
            ),
        ],
    )


class TestFixEngine:
    def test_suggest_fixes(self, pdk, spatial_index):
        engine = FixEngine(pdk, spatial_index)
        report = _make_report()
        result = engine.suggest_fixes(report)
        assert isinstance(result, FixEngineResult)
        assert result.total_suggestions > 0

    def test_suggestions_sorted_by_priority(self, pdk, spatial_index):
        engine = FixEngine(pdk, spatial_index)
        report = _make_report()
        result = engine.suggest_fixes(report)
        priorities = [s.priority for s in result.suggestions]
        assert priorities == sorted(priorities)

    def test_clusters_created(self, pdk, spatial_index):
        engine = FixEngine(pdk, spatial_index)
        report = _make_report()
        result = engine.suggest_fixes(report)
        assert len(result.clusters) > 0

    def test_unfixable_tracked(self, pdk, spatial_index):
        engine = FixEngine(pdk, spatial_index)
        # Violation with no matching strategy
        report = DRCReport(
            description="test",
            original_file="",
            generator="",
            top_cell="TOP",
            violations=[
                Violation(
                    category="unknown_rule",
                    description="unknown",
                    cell_name="TOP",
                    rule_type="nonexistent_type",
                    severity=5,
                ),
            ],
        )
        result = engine.suggest_fixes(report)
        assert len(result.unfixable) == 1

    def test_validation_applied(self, pdk, spatial_index):
        engine = FixEngine(pdk, spatial_index)
        report = _make_report()
        result = engine.suggest_fixes(report, validate=True)
        for s in result.suggestions:
            assert s.validation_notes != ""  # Should be set by validator

    def test_no_validation(self, pdk, spatial_index):
        engine = FixEngine(pdk, spatial_index)
        report = _make_report()
        result = engine.suggest_fixes(report, validate=False)
        for s in result.suggestions:
            assert s.validation_notes == ""  # Not validated

    def test_empty_report(self, pdk, spatial_index):
        engine = FixEngine(pdk, spatial_index)
        report = DRCReport(description="clean", original_file="", generator="", top_cell="TOP")
        result = engine.suggest_fixes(report)
        assert result.total_suggestions == 0
        assert result.fixable_count == 0

    def test_by_rule_type(self, pdk, spatial_index):
        engine = FixEngine(pdk, spatial_index)
        report = _make_report()
        result = engine.suggest_fixes(report)
        by_type = result.by_rule_type
        assert isinstance(by_type, dict)

    def test_suggest_for_single_violation(self, pdk, spatial_index):
        engine = FixEngine(pdk, spatial_index)
        violation = Violation(
            category="m1.1",
            description="width",
            cell_name="TOP",
            rule_id="m1.1",
            rule_type="min_width",
            severity=7,
            value_um=0.140,
            geometries=[
                ViolationGeometry(
                    geometry_type=GeometryType.edge_pair,
                    edge_pair=EdgePair(
                        edge1_start=(0, 0),
                        edge1_end=(0, 1.0),
                        edge2_start=(0.10, 0),
                        edge2_end=(0.10, 1.0),
                    ),
                ),
            ],
        )
        suggestions = engine.suggest_for_violation(violation)
        assert len(suggestions) > 0


class TestFixEngineResult:
    def test_empty_result(self):
        result = FixEngineResult()
        assert result.total_suggestions == 0
        assert result.fixable_count == 0
        assert result.by_rule_type == {}


class TestDefaultPriority:
    def test_shorts_highest(self):
        assert DEFAULT_PRIORITY["short"] == 1

    def test_offgrid_second(self):
        assert DEFAULT_PRIORITY["off_grid"] == 2

    def test_ordering(self):
        order = sorted(DEFAULT_PRIORITY.items(), key=lambda x: x[1])
        types_in_order = [t for t, _ in order]
        assert types_in_order[0] == "short"
        assert types_in_order[1] == "off_grid"

"""Tests for fix suggestion models."""

from backend.fix.fix_models import FixConfidence, FixSuggestion, PolygonDelta


class TestPolygonDelta:
    def test_normal_delta(self):
        d = PolygonDelta(
            cell_name="TOP",
            gds_layer=68,
            gds_datatype=20,
            original_points=[(0, 0), (1, 0), (1, 1), (0, 1)],
            modified_points=[(0, 0), (1.5, 0), (1.5, 1), (0, 1)],
        )
        assert not d.is_removal
        assert not d.is_addition

    def test_removal(self):
        d = PolygonDelta(
            cell_name="TOP",
            gds_layer=68,
            gds_datatype=20,
            original_points=[(0, 0), (1, 0), (1, 1), (0, 1)],
            modified_points=[],
        )
        assert d.is_removal
        assert not d.is_addition

    def test_addition(self):
        d = PolygonDelta(
            cell_name="TOP",
            gds_layer=68,
            gds_datatype=20,
            original_points=[],
            modified_points=[(0, 0), (1, 0), (1, 1), (0, 1)],
        )
        assert d.is_addition
        assert not d.is_removal


class TestFixSuggestion:
    def test_delta_count(self):
        s = FixSuggestion(
            violation_category="m1.1",
            rule_type="min_width",
            description="test",
            deltas=[
                PolygonDelta("TOP", 68, 20, [(0, 0)], [(0, 0)]),
                PolygonDelta("TOP", 69, 20, [(0, 0)], [(0, 0)]),
            ],
        )
        assert s.delta_count == 2

    def test_affected_layers(self):
        s = FixSuggestion(
            violation_category="m1.1",
            rule_type="min_width",
            description="test",
            deltas=[
                PolygonDelta("TOP", 68, 20, [(0, 0)], [(0, 0)]),
                PolygonDelta("TOP", 69, 20, [(0, 0)], [(0, 0)]),
                PolygonDelta("TOP", 68, 20, [(1, 1)], [(1, 1)]),
            ],
        )
        assert s.affected_layers == {(68, 20), (69, 20)}

    def test_default_confidence(self):
        s = FixSuggestion(
            violation_category="m1.1",
            rule_type="min_width",
            description="test",
        )
        assert s.confidence == FixConfidence.medium
        assert s.creates_new_violations is False

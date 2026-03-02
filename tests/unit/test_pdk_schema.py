"""Tests for PDK config schema and validation."""

import pytest
from pydantic import ValidationError

from backend.pdk.schema import (
    ConnectivityRule,
    DesignRule,
    FixStrategyWeight,
    GDSLayer,
    PDKConfig,
    RuleType,
)


class TestGDSLayer:
    def test_valid_layer(self):
        layer = GDSLayer(
            gds_layer=68, gds_datatype=20, description="Metal 1", color="#0000FF"
        )
        assert layer.layer_pair == (68, 20)
        assert layer.is_routing is False

    def test_routing_layer(self):
        layer = GDSLayer(
            gds_layer=68,
            gds_datatype=20,
            description="Metal 1",
            color="#0000FF",
            is_routing=True,
        )
        assert layer.is_routing is True

    def test_invalid_color(self):
        with pytest.raises(ValidationError):
            GDSLayer(
                gds_layer=68, gds_datatype=20, description="Metal 1", color="blue"
            )

    def test_negative_layer_number(self):
        with pytest.raises(ValidationError):
            GDSLayer(
                gds_layer=-1, gds_datatype=20, description="Bad", color="#000000"
            )


class TestDesignRule:
    def test_valid_rule(self):
        rule = DesignRule(
            rule_id="m1.1",
            rule_type=RuleType.min_width,
            layer="met1",
            value_um=0.140,
            description="Min width of met1",
            severity=7,
        )
        assert rule.rule_id == "m1.1"
        assert rule.value_um == 0.140

    def test_enclosure_rule_with_related_layer(self):
        rule = DesignRule(
            rule_id="m1.4",
            rule_type=RuleType.min_enclosure,
            layer="met1",
            related_layer="mcon",
            value_um=0.030,
        )
        assert rule.related_layer == "mcon"

    def test_zero_value_rejected(self):
        with pytest.raises(ValidationError):
            DesignRule(
                rule_id="bad",
                rule_type=RuleType.min_width,
                layer="met1",
                value_um=0.0,
            )

    def test_empty_rule_id_rejected(self):
        with pytest.raises(ValidationError):
            DesignRule(
                rule_id="  ",
                rule_type=RuleType.min_width,
                layer="met1",
                value_um=0.140,
            )

    def test_severity_bounds(self):
        with pytest.raises(ValidationError):
            DesignRule(
                rule_id="x",
                rule_type=RuleType.min_width,
                layer="met1",
                value_um=0.1,
                severity=11,
            )


class TestFixStrategyWeight:
    def test_defaults(self):
        w = FixStrategyWeight()
        assert w.enabled is True
        assert w.priority == 5
        assert w.prefer_move is True
        assert w.max_iterations == 3

    def test_priority_bounds(self):
        with pytest.raises(ValidationError):
            FixStrategyWeight(priority=0)
        with pytest.raises(ValidationError):
            FixStrategyWeight(priority=11)


class TestPDKConfig:
    @pytest.fixture()
    def minimal_config(self):
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
                "via": GDSLayer(
                    gds_layer=68,
                    gds_datatype=44,
                    description="Via",
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
                ),
                DesignRule(
                    rule_id="m1.2",
                    rule_type=RuleType.min_spacing,
                    layer="met1",
                    value_um=0.140,
                ),
                DesignRule(
                    rule_id="via.4a",
                    rule_type=RuleType.min_enclosure,
                    layer="met1",
                    related_layer="via",
                    value_um=0.055,
                ),
            ],
            connectivity=[
                ConnectivityRule(
                    via_layer="via", lower_layer="met1", upper_layer="met2"
                ),
            ],
            fix_weights={
                "min_width": FixStrategyWeight(priority=3),
            },
            klayout_drc_deck="test.drc",
        )

    def test_get_layer(self, minimal_config):
        layer = minimal_config.get_layer("met1")
        assert layer.gds_layer == 68

    def test_get_layer_missing(self, minimal_config):
        with pytest.raises(KeyError, match="not found"):
            minimal_config.get_layer("met99")

    def test_get_rules_for_layer(self, minimal_config):
        rules = minimal_config.get_rules_for_layer("met1")
        assert len(rules) == 3  # m1.1, m1.2, via.4a

    def test_get_rule_by_id(self, minimal_config):
        rule = minimal_config.get_rule("m1.1")
        assert rule is not None
        assert rule.value_um == 0.140

    def test_get_rule_missing(self, minimal_config):
        assert minimal_config.get_rule("nonexistent") is None

    def test_get_routing_layers(self, minimal_config):
        routing = minimal_config.get_routing_layers()
        assert routing == ["met1", "met2"]

    def test_get_via_layers(self, minimal_config):
        vias = minimal_config.get_via_layers()
        assert vias == ["via"]

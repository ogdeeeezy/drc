"""Tests for extended PDKConfig fields (drc_flags, device_classes, layer_stack)."""

import pytest
from pydantic import ValidationError

from backend.pdk.schema import (
    DesignRule,
    FixStrategyWeight,
    GDSLayer,
    PDKConfig,
    RuleType,
)


def _minimal_config(**overrides):
    """Build a minimal PDKConfig with optional field overrides."""
    defaults = dict(
        name="test",
        version="1.0",
        process_node_nm=130,
        grid_um=0.005,
        layers={
            "met1": GDSLayer(
                gds_layer=68, gds_datatype=20, description="Metal 1",
                color="#0000FF", is_routing=True,
            ),
        },
        rules=[
            DesignRule(
                rule_id="m1.1", rule_type=RuleType.min_width,
                layer="met1", value_um=0.140,
            ),
        ],
        connectivity=[],
        fix_weights={"min_width": FixStrategyWeight(priority=3)},
        klayout_drc_deck="test.drc",
    )
    defaults.update(overrides)
    return PDKConfig(**defaults)


class TestDRCFlags:
    def test_pdk_config_with_drc_flags(self):
        cfg = _minimal_config(drc_flags={"feol": "true", "beol": "true"})
        assert cfg.drc_flags == {"feol": "true", "beol": "true"}

    def test_pdk_config_without_drc_flags(self):
        cfg = _minimal_config()
        assert cfg.drc_flags is None

    def test_drc_flags_empty_dict(self):
        cfg = _minimal_config(drc_flags={})
        assert cfg.drc_flags == {}


class TestDeviceClasses:
    def test_pdk_config_with_device_classes(self):
        cfg = _minimal_config(
            device_classes={"NMOS": "sky130_fd_pr__nfet_01v8", "PMOS": "sky130_fd_pr__pfet_01v8"}
        )
        assert cfg.device_classes["NMOS"] == "sky130_fd_pr__nfet_01v8"
        assert cfg.device_classes["PMOS"] == "sky130_fd_pr__pfet_01v8"

    def test_pdk_config_without_device_classes(self):
        cfg = _minimal_config()
        assert cfg.device_classes is None


class TestLayerStack:
    def test_pdk_config_with_layer_stack(self):
        cfg = _minimal_config(layer_stack=["diff", "li1", "met1", "met2"])
        assert cfg.layer_stack == ["diff", "li1", "met1", "met2"]
        assert cfg.layer_stack[0] == "diff"

    def test_pdk_config_without_layer_stack(self):
        cfg = _minimal_config()
        assert cfg.layer_stack is None

    def test_layer_stack_empty_list(self):
        cfg = _minimal_config(layer_stack=[])
        assert cfg.layer_stack == []


class TestBackwardCompatibility:
    def test_all_new_fields_default_none(self):
        """Existing configs without new fields still validate."""
        cfg = _minimal_config()
        assert cfg.drc_flags is None
        assert cfg.device_classes is None
        assert cfg.layer_stack is None

    def test_all_new_fields_set(self):
        """Config with all new fields validates."""
        cfg = _minimal_config(
            drc_flags={"feol": "true"},
            device_classes={"NMOS": "nfet"},
            layer_stack=["met1", "met2"],
        )
        assert cfg.drc_flags is not None
        assert cfg.device_classes is not None
        assert cfg.layer_stack is not None

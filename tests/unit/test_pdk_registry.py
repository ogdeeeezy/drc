"""Tests for PDK registry — discovery and loading."""

import json
from pathlib import Path

import pytest

from backend.pdk.registry import PDKRegistry
from backend.pdk.schema import PDKConfig


@pytest.fixture()
def sky130_registry():
    """Registry pointed at the real SKY130 config."""
    configs_dir = Path(__file__).parent.parent.parent / "backend" / "pdk" / "configs"
    return PDKRegistry(configs_dir=configs_dir)


@pytest.fixture()
def empty_registry(tmp_path):
    """Registry pointed at an empty directory."""
    return PDKRegistry(configs_dir=tmp_path)


class TestPDKRegistry:
    def test_list_pdks(self, sky130_registry):
        pdks = sky130_registry.list_pdks()
        assert "sky130" in pdks

    def test_list_empty(self, empty_registry):
        assert empty_registry.list_pdks() == []

    def test_load_sky130(self, sky130_registry):
        config = sky130_registry.load("sky130")
        assert isinstance(config, PDKConfig)
        assert config.name == "sky130"
        assert config.process_node_nm == 130
        assert config.grid_um == 0.005

    def test_sky130_has_layers(self, sky130_registry):
        config = sky130_registry.load("sky130")
        assert len(config.layers) >= 20
        assert "met1" in config.layers
        assert "li1" in config.layers
        assert "via" in config.layers

    def test_sky130_has_rules(self, sky130_registry):
        config = sky130_registry.load("sky130")
        assert len(config.rules) >= 30

    def test_sky130_met1_rules(self, sky130_registry):
        config = sky130_registry.load("sky130")
        rule = config.get_rule("m1.1")
        assert rule is not None
        assert rule.value_um == 0.140

    def test_sky130_connectivity(self, sky130_registry):
        config = sky130_registry.load("sky130")
        assert len(config.connectivity) >= 7
        via_layers = [c.via_layer for c in config.connectivity]
        assert "via" in via_layers
        assert "mcon" in via_layers

    def test_sky130_routing_layers_ordered(self, sky130_registry):
        config = sky130_registry.load("sky130")
        routing = config.get_routing_layers()
        assert routing == ["li1", "met1", "met2", "met3", "met4", "met5"]

    def test_load_caches(self, sky130_registry):
        c1 = sky130_registry.load("sky130")
        c2 = sky130_registry.load("sky130")
        assert c1 is c2

    def test_reload_clears_cache(self, sky130_registry):
        c1 = sky130_registry.load("sky130")
        c2 = sky130_registry.reload("sky130")
        assert c1 is not c2

    def test_load_missing_pdk(self, sky130_registry):
        with pytest.raises(FileNotFoundError, match="not found"):
            sky130_registry.load("nonexistent_pdk")

    def test_custom_pdk(self, tmp_path):
        """Test loading a custom PDK config from a temp directory."""
        pdk_dir = tmp_path / "mypdk"
        pdk_dir.mkdir()
        config_data = {
            "name": "mypdk",
            "version": "1.0",
            "process_node_nm": 65,
            "grid_um": 0.001,
            "klayout_drc_deck": "mypdk.drc",
            "layers": {
                "met1": {
                    "gds_layer": 10,
                    "gds_datatype": 0,
                    "description": "Metal 1",
                    "color": "#0000FF",
                    "is_routing": True,
                }
            },
            "rules": [
                {
                    "rule_id": "m1.w",
                    "rule_type": "min_width",
                    "layer": "met1",
                    "value_um": 0.065,
                }
            ],
            "connectivity": [],
            "fix_weights": {},
        }
        (pdk_dir / "pdk.json").write_text(json.dumps(config_data))

        registry = PDKRegistry(configs_dir=tmp_path)
        assert "mypdk" in registry.list_pdks()
        config = registry.load("mypdk")
        assert config.process_node_nm == 65

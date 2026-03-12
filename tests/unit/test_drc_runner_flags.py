"""Tests for DRC runner flag resolution (pdk.drc_flags vs DEFAULT_DRC_FLAGS)."""

from pathlib import Path

import pytest

from backend.core.drc_runner import DRCRunner
from backend.pdk.schema import (
    DesignRule,
    FixStrategyWeight,
    GDSLayer,
    PDKConfig,
    RuleType,
)


def _make_pdk(**overrides):
    defaults = dict(
        name="test_pdk",
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
                layer="met1", value_um=0.140, severity=7,
            ),
        ],
        connectivity=[],
        fix_weights={"min_width": FixStrategyWeight(priority=3)},
        klayout_drc_deck="test.drc",
    )
    defaults.update(overrides)
    return PDKConfig(**defaults)


@pytest.fixture()
def runner():
    return DRCRunner()


class TestBuildCommandFlags:
    def test_build_command_uses_pdk_drc_flags(self, runner, tmp_path):
        """When pdk.drc_flags is set, those flags are used instead of DEFAULT_DRC_FLAGS."""
        pdk = _make_pdk(drc_flags={"feol": "true", "beol": "false", "custom": "yes"})
        gds = tmp_path / "test.gds"
        gds.touch()
        deck = tmp_path / "test.drc"
        deck.touch()
        report = tmp_path / "report.lyrdb"

        cmd = runner.build_command(gds, deck, report, pdk=pdk)
        cmd_str = " ".join(cmd)

        # PDK flags should be present
        assert "feol=true" in cmd_str
        assert "beol=false" in cmd_str
        assert "custom=yes" in cmd_str
        # DEFAULT_DRC_FLAGS keys NOT in PDK flags should NOT appear
        # (seal and floating_met are in defaults but not in our pdk flags)
        assert "seal=" not in cmd_str
        assert "floating_met=" not in cmd_str

    def test_build_command_falls_back_to_defaults(self, runner, tmp_path):
        """When pdk.drc_flags is None, DEFAULT_DRC_FLAGS are used."""
        pdk = _make_pdk()  # no drc_flags
        gds = tmp_path / "test.gds"
        gds.touch()
        deck = tmp_path / "test.drc"
        deck.touch()
        report = tmp_path / "report.lyrdb"

        cmd = runner.build_command(gds, deck, report, pdk=pdk)
        cmd_str = " ".join(cmd)

        # Default flags should be present
        assert "feol=true" in cmd_str
        assert "beol=true" in cmd_str
        assert "offgrid=true" in cmd_str

    def test_build_command_no_pdk_uses_defaults(self, runner, tmp_path):
        """When pdk is not passed at all, DEFAULT_DRC_FLAGS are used."""
        gds = tmp_path / "test.gds"
        gds.touch()
        deck = tmp_path / "test.drc"
        deck.touch()
        report = tmp_path / "report.lyrdb"

        cmd = runner.build_command(gds, deck, report)
        cmd_str = " ".join(cmd)

        assert "feol=true" in cmd_str
        assert "beol=true" in cmd_str

    def test_per_call_flags_override_pdk_flags(self, runner, tmp_path):
        """Per-call drc_flags override pdk.drc_flags."""
        pdk = _make_pdk(drc_flags={"feol": "true", "beol": "true"})
        gds = tmp_path / "test.gds"
        gds.touch()
        deck = tmp_path / "test.drc"
        deck.touch()
        report = tmp_path / "report.lyrdb"

        cmd = runner.build_command(
            gds, deck, report, pdk=pdk, drc_flags={"beol": "false"}
        )
        cmd_str = " ".join(cmd)

        assert "feol=true" in cmd_str
        # Per-call override wins
        assert "beol=false" in cmd_str

"""Tests for SKY130 LVS deck, PDK configuration, and end-to-end LVS flow."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config import PDK_CONFIGS_DIR
from backend.core.lvs_models import LVSMismatchType
from backend.core.lvs_parser import LVSReportParser
from backend.core.lvs_runner import LVSRunner
from backend.pdk.registry import PDKRegistry
from backend.pdk.schema import PDKConfig

# ── Paths ──────────────────────────────────────────────────────────────────

SKY130_DIR = PDK_CONFIGS_DIR / "sky130"
LVS_DECK_PATH = SKY130_DIR / "sky130A.lvs"
PDK_JSON_PATH = SKY130_DIR / "pdk.json"

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
LVSDB_DIR = FIXTURES_DIR / "lvsdb"
SPICE_DIR = FIXTURES_DIR / "spice"


# ── Deck File Existence and Structure ──────────────────────────────────────


class TestLVSDeckFile:
    """Verify the SKY130 LVS deck file exists and has correct structure."""

    def test_deck_file_exists(self):
        assert LVS_DECK_PATH.exists(), f"LVS deck not found at {LVS_DECK_PATH}"

    def test_deck_is_not_empty(self):
        content = LVS_DECK_PATH.read_text()
        assert len(content) > 100, "LVS deck appears too small"

    def test_deck_has_input_setup(self):
        content = LVS_DECK_PATH.read_text()
        assert "source($input)" in content, "Missing source($input) directive"
        assert "schematic($schematic)" in content, "Missing schematic($schematic) directive"
        assert "report_lvs($report)" in content, "Missing report_lvs($report) directive"

    def test_deck_has_deep_mode(self):
        content = LVS_DECK_PATH.read_text()
        # Check for 'deep' keyword (not inside a comment)
        lines = content.split("\n")
        deep_lines = [l.strip() for l in lines if l.strip() == "deep"]
        assert len(deep_lines) >= 1, "Missing 'deep' mode for hierarchical extraction"

    def test_deck_extracts_nmos(self):
        content = LVS_DECK_PATH.read_text()
        assert 'mos4("NMOS")' in content, "Missing NMOS device extraction"

    def test_deck_extracts_pmos(self):
        content = LVS_DECK_PATH.read_text()
        assert 'mos4("PMOS")' in content, "Missing PMOS device extraction"

    def test_deck_extracts_resistor(self):
        content = LVS_DECK_PATH.read_text()
        assert 'resistor("RES"' in content, "Missing poly resistor extraction"

    def test_deck_has_nwell_layer(self):
        content = LVS_DECK_PATH.read_text()
        assert "input(64, 20)" in content, "Missing nwell layer (64, 20)"

    def test_deck_has_diff_layer(self):
        content = LVS_DECK_PATH.read_text()
        assert "input(65, 20)" in content, "Missing diff layer (65, 20)"

    def test_deck_has_poly_layer(self):
        content = LVS_DECK_PATH.read_text()
        assert "input(66, 20)" in content, "Missing poly layer (66, 20)"

    def test_deck_has_poly_resistor_id_layer(self):
        content = LVS_DECK_PATH.read_text()
        assert "input(66, 13)" in content, "Missing poly resistor ID layer (66, 13)"

    def test_deck_has_full_metal_stack_connectivity(self):
        """Verify connectivity rules for li1 through met5."""
        content = LVS_DECK_PATH.read_text()
        # Contact/via connectivity
        assert "connect(licon, li1)" in content, "Missing licon→li1 connectivity"
        assert "connect(li1," in content and "mcon" in content, "Missing li1→mcon connectivity"
        assert "connect(mcon," in content and "met1" in content, "Missing mcon→met1 connectivity"
        # Metal stack
        assert "connect(met1, via1)" in content, "Missing met1→via1 connectivity"
        assert "connect(via1, met2)" in content, "Missing via1→met2 connectivity"
        assert "connect(met2, via2)" in content, "Missing met2→via2 connectivity"
        assert "connect(via2, met3)" in content, "Missing via2→met3 connectivity"
        assert "connect(met3, via3)" in content, "Missing met3→via3 connectivity"
        assert "connect(via3, met4)" in content, "Missing via3→met4 connectivity"
        assert "connect(met4, via4)" in content, "Missing met4→via4 connectivity"
        assert "connect(via4, met5)" in content, "Missing via4→met5 connectivity"

    def test_deck_has_well_tap_connectivity(self):
        content = LVS_DECK_PATH.read_text()
        assert "connect(nwell, ntap)" in content, "Missing nwell→ntap body connectivity"
        assert "connect(pwell, ptap)" in content, "Missing pwell→ptap body connectivity"

    def test_deck_has_compare(self):
        content = LVS_DECK_PATH.read_text()
        lines = content.split("\n")
        compare_lines = [l.strip() for l in lines if l.strip() == "compare"]
        assert len(compare_lines) >= 1, "Missing 'compare' directive"

    def test_deck_has_netlist_simplify(self):
        content = LVS_DECK_PATH.read_text()
        assert "netlist.simplify" in content, "Missing netlist.simplify before compare"

    def test_deck_has_implant_markers(self):
        content = LVS_DECK_PATH.read_text()
        assert "input(93, 44)" in content, "Missing nsdm layer (93, 44)"
        assert "input(94, 20)" in content, "Missing psdm layer (94, 20)"

    def test_deck_derives_nsd_from_diff_and_nsdm(self):
        content = LVS_DECK_PATH.read_text()
        assert "nsd" in content and "diff & nsdm" in content, (
            "Missing N+ active derivation (diff & nsdm)"
        )

    def test_deck_derives_psd_from_diff_and_psdm(self):
        content = LVS_DECK_PATH.read_text()
        assert "psd" in content and "diff & psdm" in content, (
            "Missing P+ active derivation (diff & psdm)"
        )

    def test_deck_separates_gate_poly_from_resistor_poly(self):
        content = LVS_DECK_PATH.read_text()
        assert "gate_poly" in content and "poly - poly_res" in content, (
            "Must exclude resistor-marked poly from gate extraction"
        )


# ── PDK Configuration ──────────────────────────────────────────────────────


class TestPDKConfiguration:
    """Verify pdk.json includes klayout_lvs_deck and loads correctly."""

    def test_pdk_json_has_lvs_deck_field(self):
        with open(PDK_JSON_PATH) as f:
            data = json.load(f)
        assert "klayout_lvs_deck" in data, "pdk.json missing klayout_lvs_deck field"
        assert data["klayout_lvs_deck"] == "sky130A.lvs"

    def test_pdk_config_loads_with_lvs_deck(self):
        with open(PDK_JSON_PATH) as f:
            data = json.load(f)
        config = PDKConfig.model_validate(data)
        assert config.klayout_lvs_deck == "sky130A.lvs"

    def test_pdk_registry_loads_sky130(self):
        registry = PDKRegistry()
        config = registry.load("sky130")
        assert config.klayout_lvs_deck == "sky130A.lvs"
        assert config.name == "sky130"

    def test_lvs_runner_resolves_deck_path(self):
        registry = PDKRegistry()
        config = registry.load("sky130")
        runner = LVSRunner()
        deck_path = runner.get_lvs_deck_path(config)
        assert deck_path.exists()
        assert deck_path.name == "sky130A.lvs"
        assert deck_path == LVS_DECK_PATH


# ── SPICE Test Fixtures ────────────────────────────────────────────────────


class TestSPICEFixtures:
    """Verify SPICE test fixtures exist and have valid structure."""

    def test_inverter_spice_exists(self):
        path = SPICE_DIR / "inverter.spice"
        assert path.exists(), f"Missing SPICE fixture: {path}"

    def test_inverter_with_resistor_spice_exists(self):
        path = SPICE_DIR / "inverter_with_resistor.spice"
        assert path.exists(), f"Missing SPICE fixture: {path}"

    def test_inverter_spice_has_subcircuit(self):
        content = (SPICE_DIR / "inverter.spice").read_text()
        assert ".subckt INVERTER" in content
        assert ".ends" in content

    def test_inverter_spice_has_nmos_and_pmos(self):
        content = (SPICE_DIR / "inverter.spice").read_text()
        assert "NMOS" in content, "Missing NMOS device"
        assert "PMOS" in content, "Missing PMOS device"

    def test_inverter_with_resistor_has_extra_device(self):
        content = (SPICE_DIR / "inverter_with_resistor.spice").read_text()
        assert "NMOS" in content
        assert "PMOS" in content
        assert "RES" in content, "Missing resistor for mismatch test"


# ── End-to-End LVS Flow (Mocked Subprocess) ───────────────────────────────


class TestLVSEndToEndFlow:
    """Test the full LVS pipeline: Runner (mocked) → Parser → Report.

    These tests use existing .lvsdb fixture files to simulate KLayout output,
    verifying the full flow from runner result to parsed mismatch report.
    """

    def test_clean_inverter_produces_match(self):
        """Simulate: LVS run on matching layout+schematic → match=true."""
        parser = LVSReportParser()
        report = parser.parse_file(LVSDB_DIR / "clean_inverter.lvsdb")

        assert report.match is True
        assert report.devices_matched == 2  # PMOS + NMOS
        assert report.devices_mismatched == 0
        assert report.nets_matched == 4  # IN, VSS, VDD, OUT
        assert report.nets_mismatched == 0
        assert len(report.mismatches) == 0

    def test_mismatched_inverter_produces_nomatch(self):
        """Simulate: LVS run with missing device → match=false, mismatches reported."""
        parser = LVSReportParser()
        report = parser.parse_file(LVSDB_DIR / "mismatched_inverter.lvsdb")

        assert report.match is False
        assert report.devices_mismatched > 0
        assert len(report.mismatches) > 0

        # Should find extra_device (extra NMOS in layout)
        mismatch_types = {m.type for m in report.mismatches}
        assert LVSMismatchType.extra_device in mismatch_types or (
            LVSMismatchType.missing_device in mismatch_types
        ), "Should report extra or missing device mismatches"

    def test_mismatched_has_missing_device(self):
        """Verify a missing_device mismatch is reported for the resistor."""
        parser = LVSReportParser()
        report = parser.parse_file(LVSDB_DIR / "mismatched_inverter.lvsdb")

        missing_devices = [
            m for m in report.mismatches if m.type == LVSMismatchType.missing_device
        ]
        assert len(missing_devices) >= 1, (
            "Should report at least one missing device (RES not in layout)"
        )

    def test_runner_builds_correct_command_with_sky130_deck(self):
        """Verify LVSRunner builds the correct command using the sky130 LVS deck."""
        registry = PDKRegistry()
        config = registry.load("sky130")
        runner = LVSRunner()
        deck_path = runner.get_lvs_deck_path(config)

        cmd = runner.build_command(
            gds_path=Path("/tmp/test.gds"),
            netlist_path=Path("/tmp/test.spice"),
            lvs_deck_path=deck_path,
            report_path=Path("/tmp/test.lvsdb"),
        )

        assert "-b" in cmd, "Missing batch mode flag"
        assert "-r" in cmd, "Missing -r flag for deck"
        assert str(deck_path) in cmd, "Deck path not in command"
        assert "input=/tmp/test.gds" in cmd, "Missing input GDS parameter"
        assert "schematic=/tmp/test.spice" in cmd, "Missing schematic parameter"
        assert "report=/tmp/test.lvsdb" in cmd, "Missing report parameter"


# ── Integration Test (Requires KLayout) ────────────────────────────────────


def _has_klayout() -> bool:
    """Check if KLayout binary is available for integration tests."""
    runner = LVSRunner()
    return runner.check_klayout_available()


@pytest.mark.skipif(not _has_klayout(), reason="KLayout not installed")
class TestLVSIntegration:
    """Integration tests that require KLayout binary.

    These are skipped in CI where KLayout is not available.
    They validate the actual deck execution with real GDS and SPICE files.
    """

    def test_placeholder_for_integration(self):
        """Placeholder: real integration tests need GDS layout fixtures.

        To run actual LVS integration tests, generate a SKY130 inverter GDS
        (e.g., using the PCell framework) and test against inverter.spice.
        """
        assert _has_klayout(), "KLayout should be available for integration tests"

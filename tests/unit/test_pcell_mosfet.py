"""Tests for the MOSFET parameterized cell generator."""

import gdstk
import pytest

from backend.pcell.mosfet import (
    LYR_DIFF,
    LYR_LI1,
    LYR_LICON,
    LYR_MCON,
    LYR_MET1,
    LYR_MET1_LBL,
    LYR_NSDM,
    LYR_NWELL,
    LYR_POLY,
    LYR_PSDM,
    SKY130,
    MOSFETGenerator,
)


@pytest.fixture
def gen():
    return MOSFETGenerator()


# ---------------------------------------------------------------------------
# Helper to count polygons on a specific layer
# ---------------------------------------------------------------------------
def _polys_on_layer(cell: gdstk.Cell, layer: int, datatype: int) -> list:
    return [p for p in cell.polygons if p.layer == layer and p.datatype == datatype]


def _labels_on_layer(cell: gdstk.Cell, layer: int, texttype: int) -> list:
    return [lb for lb in cell.labels if lb.layer == layer and lb.texttype == texttype]


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------
class TestMOSFETValidation:
    def test_invalid_device_type(self, gen):
        with pytest.raises(ValueError, match="device_type"):
            gen.validate_params({"device_type": "bjt", "w_um": 0.42, "l_um": 0.15})

    def test_w_too_small(self, gen):
        with pytest.raises(ValueError, match="w_um"):
            gen.validate_params({"device_type": "nmos", "w_um": 0.10, "l_um": 0.15})

    def test_l_too_small(self, gen):
        with pytest.raises(ValueError, match="l_um"):
            gen.validate_params({"device_type": "nmos", "w_um": 0.42, "l_um": 0.01})

    def test_fingers_zero(self, gen):
        with pytest.raises(ValueError, match="fingers"):
            gen.validate_params(
                {"device_type": "nmos", "w_um": 0.42, "l_um": 0.15, "fingers": 0}
            )

    def test_invalid_gate_contact(self, gen):
        with pytest.raises(ValueError, match="gate_contact"):
            gen.validate_params(
                {
                    "device_type": "nmos",
                    "w_um": 0.42,
                    "l_um": 0.15,
                    "gate_contact": "left",
                }
            )

    def test_valid_params_pass(self, gen):
        gen.validate_params({"device_type": "nmos", "w_um": 0.42, "l_um": 0.15})
        gen.validate_params(
            {
                "device_type": "pmos",
                "w_um": 1.0,
                "l_um": 0.15,
                "fingers": 4,
                "gate_contact": "top",
            }
        )


# ---------------------------------------------------------------------------
# 1-finger NMOS
# ---------------------------------------------------------------------------
class TestSingleFingerNMOS:
    """Test: generate 1-finger NMOS → verify layer count, polygon count, cell name."""

    @pytest.fixture
    def result(self, gen):
        return gen.generate(
            {"device_type": "nmos", "w_um": 0.42, "l_um": 0.15, "fingers": 1}
        )

    def test_cell_name_format(self, result):
        assert result.cell_name.startswith("sky130_nmos_")
        assert "W0p42" in result.cell_name
        assert "L0p15" in result.cell_name
        assert "F1" in result.cell_name

    def test_params_echoed(self, result):
        assert result.params["device_type"] == "nmos"
        assert result.params["w_um"] == 0.42
        assert result.params["l_um"] == 0.15
        assert result.params["fingers"] == 1

    def test_has_diffusion(self, result):
        polys = _polys_on_layer(result.cell, *LYR_DIFF)
        assert len(polys) == 1, "Expected exactly one diffusion rectangle"

    def test_has_poly_gate(self, result):
        polys = _polys_on_layer(result.cell, *LYR_POLY)
        # 1 gate body + possible T-gate pads (L=0.15 < 0.270, so 2 pads for "both")
        assert len(polys) >= 1, "Expected at least one poly gate"

    def test_has_nsdm_no_nwell(self, result):
        nsdm = _polys_on_layer(result.cell, *LYR_NSDM)
        psdm = _polys_on_layer(result.cell, *LYR_PSDM)
        nwell = _polys_on_layer(result.cell, *LYR_NWELL)
        assert len(nsdm) == 1, "NMOS should have nsdm implant"
        assert len(psdm) == 1, "NMOS should have psdm for substrate tap"
        assert len(nwell) == 0, "NMOS should not have nwell"

    def test_has_contacts(self, result):
        licons = _polys_on_layer(result.cell, *LYR_LICON)
        mcons = _polys_on_layer(result.cell, *LYR_MCON)
        assert len(licons) >= 4, "Expected licons for S/D + gate contacts"
        assert len(mcons) >= 4, "Expected mcons matching licons"

    def test_has_li1(self, result):
        li1 = _polys_on_layer(result.cell, *LYR_LI1)
        assert len(li1) >= 2, "Expected li1 routing for S/D regions"

    def test_has_met1(self, result):
        met1 = _polys_on_layer(result.cell, *LYR_MET1)
        assert len(met1) >= 2, "Expected met1 pads for S, D, G pins"

    def test_has_pin_labels(self, result):
        labels = _labels_on_layer(result.cell, *LYR_MET1_LBL)
        label_texts = {lb.text for lb in labels}
        assert "S" in label_texts, "Missing source pin label"
        assert "D" in label_texts, "Missing drain pin label"
        assert "G" in label_texts, "Missing gate pin label"
        assert "B" in label_texts, "Missing body pin label"

    def test_two_sd_regions(self, result):
        """1-finger MOSFET has 2 S/D regions: S, D."""
        assert result.metadata["n_sd_regions"] == 2

    def test_cell_is_valid_gdstk(self, result, tmp_path):
        """Verify the cell can be written to a GDS file without error."""
        lib = gdstk.Library()
        lib.add(result.cell)
        out = tmp_path / "test.gds"
        lib.write_gds(str(out))
        assert out.stat().st_size > 0

    def test_deterministic(self, gen):
        """Same params → same GDS output."""
        params = {"device_type": "nmos", "w_um": 0.42, "l_um": 0.15, "fingers": 1}
        r1 = gen.generate(params)
        r2 = gen.generate(params)
        # Cell names match
        assert r1.cell_name == r2.cell_name
        # Same polygon count per layer
        for lyr in [LYR_DIFF, LYR_POLY, LYR_LICON, LYR_LI1, LYR_MCON, LYR_MET1]:
            p1 = _polys_on_layer(r1.cell, *lyr)
            p2 = _polys_on_layer(r2.cell, *lyr)
            assert len(p1) == len(p2), f"Non-deterministic on layer {lyr}"


# ---------------------------------------------------------------------------
# 4-finger PMOS
# ---------------------------------------------------------------------------
class TestMultiFingerPMOS:
    """Test: generate 4-finger PMOS → verify nwell present, correct finger count."""

    @pytest.fixture
    def result(self, gen):
        return gen.generate(
            {"device_type": "pmos", "w_um": 1.0, "l_um": 0.15, "fingers": 4}
        )

    def test_cell_name(self, result):
        assert "pmos" in result.cell_name
        assert "F4" in result.cell_name

    def test_has_nwell(self, result):
        nwell = _polys_on_layer(result.cell, *LYR_NWELL)
        assert len(nwell) == 1, "PMOS must have nwell"

    def test_has_psdm_no_nsdm(self, result):
        psdm = _polys_on_layer(result.cell, *LYR_PSDM)
        nsdm = _polys_on_layer(result.cell, *LYR_NSDM)
        assert len(psdm) == 1, "PMOS should have psdm"
        assert len(nsdm) == 1, "PMOS should have nsdm for well tap"

    def test_four_poly_gates(self, result):
        """4 fingers → at least 4 poly rectangles (more with T-gate pads)."""
        polys = _polys_on_layer(result.cell, *LYR_POLY)
        assert len(polys) >= 4

    def test_five_sd_regions(self, result):
        """4 fingers → 5 S/D regions (S,D,S,D,S)."""
        assert result.metadata["n_sd_regions"] == 5

    def test_nwell_encloses_diff(self, result):
        """Nwell must enclose diffusion by at least nwell_enc_diff."""
        diff = _polys_on_layer(result.cell, *LYR_DIFF)[0]
        nwell = _polys_on_layer(result.cell, *LYR_NWELL)[0]
        diff_bb = diff.bounding_box()
        nwell_bb = nwell.bounding_box()
        enc = SKY130.nwell_enc_diff - 0.001  # tiny tolerance for float
        assert nwell_bb[0][0] <= diff_bb[0][0] - enc, "Nwell left enclosure"
        assert nwell_bb[0][1] <= diff_bb[0][1] - enc, "Nwell bottom enclosure"
        assert nwell_bb[1][0] >= diff_bb[1][0] + enc, "Nwell right enclosure"
        assert nwell_bb[1][1] >= diff_bb[1][1] + enc, "Nwell top enclosure"

    def test_diff_extends_beyond_poly(self, result):
        """Diffusion must extend beyond outermost gate body edges (poly.7).

        Only gate body polys count — T-gate endcap pads may be wider but don't
        cross the diff, so poly.7 doesn't apply to them.
        """
        diff = _polys_on_layer(result.cell, *LYR_DIFF)[0]
        polys = _polys_on_layer(result.cell, *LYR_POLY)
        diff_bb = diff.bounding_box()
        diff_y0, diff_y1 = diff_bb[0][1], diff_bb[1][1]

        # Filter to gate body polys (those that span the full diff height)
        gate_bodies = [
            p for p in polys
            if p.bounding_box()[0][1] < diff_y0 + 0.01
            and p.bounding_box()[1][1] > diff_y1 - 0.01
        ]
        assert len(gate_bodies) >= 4, "Expected 4 gate body polys"

        leftmost_gate_x = min(p.bounding_box()[0][0] for p in gate_bodies)
        rightmost_gate_x = max(p.bounding_box()[1][0] for p in gate_bodies)

        ext = SKY130.diff_ext_poly - 0.001
        assert diff_bb[0][0] <= leftmost_gate_x - ext, "Diff left extension beyond poly"
        assert diff_bb[1][0] >= rightmost_gate_x + ext, "Diff right extension beyond poly"

    def test_multiple_contacts_in_y(self, result):
        """W=1.0 should fit multiple contacts vertically."""
        assert result.metadata["n_sd_contacts_y"] >= 2

    def test_source_drain_labels(self, result):
        labels = _labels_on_layer(result.cell, *LYR_MET1_LBL)
        label_texts = [lb.text for lb in labels]
        s_count = label_texts.count("S")
        d_count = label_texts.count("D")
        # 5 S/D regions: S, D, S, D, S → 3 source, 2 drain
        assert s_count == 3
        assert d_count == 2

    def test_source_bus_connects_all_sources(self, result):
        """A horizontal met1 bus bar must span all source pad X positions."""
        labels = _labels_on_layer(result.cell, *LYR_MET1_LBL)
        src_xs = sorted(lb.origin[0] for lb in labels if lb.text == "S")
        assert len(src_xs) == 3

        met1 = _polys_on_layer(result.cell, *LYR_MET1)
        bus_found = any(
            p.bounding_box()[0][0] <= src_xs[0] + 0.001
            and p.bounding_box()[1][0] >= src_xs[-1] - 0.001
            for p in met1
        )
        assert bus_found, "No met1 bus bar spanning all source X positions"

    def test_drain_bus_connects_all_drains(self, result):
        """A horizontal met1 bus bar must span all drain pad X positions."""
        labels = _labels_on_layer(result.cell, *LYR_MET1_LBL)
        drn_xs = sorted(lb.origin[0] for lb in labels if lb.text == "D")
        assert len(drn_xs) == 2

        met1 = _polys_on_layer(result.cell, *LYR_MET1)
        bus_found = any(
            p.bounding_box()[0][0] <= drn_xs[0] + 0.001
            and p.bounding_box()[1][0] >= drn_xs[-1] - 0.001
            for p in met1
        )
        assert bus_found, "No met1 bus bar spanning all drain X positions"

    def test_single_finger_no_bus(self, gen):
        """1-finger device should not add extra met1 for bus bars."""
        r_1f = gen.generate(
            {"device_type": "pmos", "w_um": 1.0, "l_um": 0.15, "fingers": 1}
        )
        met1_1f = len(_polys_on_layer(r_1f.cell, *LYR_MET1))
        # 1-finger: 2 S/D pads + 2 gate pads (both) + 1 body = 5
        # No bus bars or vertical drops
        assert met1_1f == 5


# ---------------------------------------------------------------------------
# 2-finger NMOS
# ---------------------------------------------------------------------------
class TestMultiFingerNMOS:
    """Test: 2-finger NMOS → verify S/D bus routing and connectivity."""

    @pytest.fixture
    def result(self, gen):
        return gen.generate(
            {"device_type": "nmos", "w_um": 0.42, "l_um": 0.15, "fingers": 2}
        )

    def test_three_sd_regions(self, result):
        """2 fingers → 3 S/D regions (S, D, S)."""
        assert result.metadata["n_sd_regions"] == 3

    def test_source_bus_present(self, result):
        """Source bus met1 spans both source pad X positions."""
        labels = _labels_on_layer(result.cell, *LYR_MET1_LBL)
        src_xs = sorted(lb.origin[0] for lb in labels if lb.text == "S")
        assert len(src_xs) == 2

        met1 = _polys_on_layer(result.cell, *LYR_MET1)
        bus_found = any(
            p.bounding_box()[0][0] <= src_xs[0] + 0.001
            and p.bounding_box()[1][0] >= src_xs[-1] - 0.001
            for p in met1
        )
        assert bus_found, "No met1 bus bar spanning all source X positions"

    def test_has_nsdm_no_nwell(self, result):
        nsdm = _polys_on_layer(result.cell, *LYR_NSDM)
        nwell = _polys_on_layer(result.cell, *LYR_NWELL)
        assert len(nsdm) == 1, "NMOS should have nsdm implant"
        assert len(nwell) == 0, "NMOS should not have nwell"

    def test_cell_is_valid_gdstk(self, result, tmp_path):
        """Verify the cell can be written to a GDS file without error."""
        lib = gdstk.Library()
        lib.add(result.cell)
        out = tmp_path / "test_2f_nmos.gds"
        lib.write_gds(str(out))
        assert out.stat().st_size > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_minimum_size_nmos(self, gen):
        """Minimum-size transistor should still generate valid cell."""
        result = gen.generate(
            {"device_type": "nmos", "w_um": 0.42, "l_um": 0.15, "fingers": 1}
        )
        assert result.cell is not None
        # Verify at least basic layers present
        for lyr in [LYR_DIFF, LYR_POLY, LYR_LICON, LYR_MET1]:
            assert len(_polys_on_layer(result.cell, *lyr)) >= 1

    def test_wide_gate_no_t_gate(self, gen):
        """L >= 0.270 should not need T-gate widening."""
        result = gen.generate(
            {"device_type": "nmos", "w_um": 0.42, "l_um": 0.30, "fingers": 1}
        )
        polys = _polys_on_layer(result.cell, *LYR_POLY)
        # With L=0.30 >= 0.270, no T-gate pads needed → just 1 poly rect
        assert len(polys) == 1

    def test_gate_contact_top_only(self, gen):
        result = gen.generate(
            {
                "device_type": "nmos",
                "w_um": 0.42,
                "l_um": 0.15,
                "fingers": 1,
                "gate_contact": "top",
            }
        )
        labels = _labels_on_layer(result.cell, *LYR_MET1_LBL)
        g_labels = [lb for lb in labels if lb.text == "G"]
        # Gate contacts only at top → gate labels only above diff
        diff_top = 0.42
        for lb in g_labels:
            assert lb.origin[1] > diff_top * 0.5, "Gate label should be above diff center"

    def test_gate_contact_bottom_only(self, gen):
        result = gen.generate(
            {
                "device_type": "nmos",
                "w_um": 0.42,
                "l_um": 0.15,
                "fingers": 1,
                "gate_contact": "bottom",
            }
        )
        labels = _labels_on_layer(result.cell, *LYR_MET1_LBL)
        g_labels = [lb for lb in labels if lb.text == "G"]
        for lb in g_labels:
            assert lb.origin[1] < 0, "Gate label should be below diff"


class TestParamSchema:
    def test_schema_has_required_params(self, gen):
        schema = gen.param_schema()
        assert "device_type" in schema
        assert "w_um" in schema
        assert "l_um" in schema
        assert "fingers" in schema
        assert "gate_contact" in schema

    def test_schema_has_choices(self, gen):
        schema = gen.param_schema()
        assert "nmos" in schema["device_type"]["choices"]
        assert "pmos" in schema["device_type"]["choices"]

    def test_schema_has_defaults(self, gen):
        schema = gen.param_schema()
        assert schema["fingers"]["default"] == 1
        assert schema["gate_contact"]["default"] == "both"

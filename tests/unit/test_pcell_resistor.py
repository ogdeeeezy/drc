"""Tests for the poly resistor parameterized cell generator."""

import gdstk
import pytest

from backend.pcell.resistor import (
    LYR_LI1,
    LYR_LICON,
    LYR_MCON,
    LYR_MET1,
    LYR_MET1_LBL,
    LYR_NPC,
    LYR_POLY,
    LYR_POLY_RS,
    LYR_PSDM,
    LYR_RPM,
    SKY130_RES,
    PolyResistorGenerator,
)


@pytest.fixture
def gen():
    return PolyResistorGenerator()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _polys_on_layer(cell: gdstk.Cell, layer: int, datatype: int) -> list:
    return [p for p in cell.polygons if p.layer == layer and p.datatype == datatype]


def _labels_on_layer(cell: gdstk.Cell, layer: int, texttype: int) -> list:
    return [lb for lb in cell.labels if lb.layer == layer and lb.texttype == texttype]


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------
class TestPolyResValidation:
    def test_w_too_small(self, gen):
        with pytest.raises(ValueError, match="w_um"):
            gen.validate_params({"w_um": 0.10, "l_um": 1.0})

    def test_l_too_small(self, gen):
        with pytest.raises(ValueError, match="l_um"):
            gen.validate_params({"w_um": 0.50, "l_um": 0.01})

    def test_segments_zero(self, gen):
        with pytest.raises(ValueError, match="segments"):
            gen.validate_params({"w_um": 0.50, "l_um": 1.0, "segments": 0})

    def test_w_none(self, gen):
        with pytest.raises(ValueError, match="w_um"):
            gen.validate_params({"l_um": 1.0})

    def test_l_none(self, gen):
        with pytest.raises(ValueError, match="l_um"):
            gen.validate_params({"w_um": 0.50})

    def test_valid_params(self, gen):
        gen.validate_params({"w_um": 0.50, "l_um": 2.0})
        gen.validate_params({"w_um": 0.50, "l_um": 2.0, "segments": 3})


# ---------------------------------------------------------------------------
# 1-segment resistor
# ---------------------------------------------------------------------------
class TestSingleSegmentResistor:
    """Test: generate 1-segment resistor -> verify layers and pin labels."""

    @pytest.fixture
    def result(self, gen):
        return gen.generate({"w_um": 0.50, "l_um": 2.0, "segments": 1})

    def test_cell_name(self, result):
        assert result.cell_name.startswith("sky130_polyres_")
        assert "W0p5" in result.cell_name
        assert "L2" in result.cell_name
        assert "S1" in result.cell_name

    def test_params_echoed(self, result):
        assert result.params["w_um"] == 0.5
        assert result.params["l_um"] == 2.0
        assert result.params["segments"] == 1

    def test_has_poly(self, result):
        polys = _polys_on_layer(result.cell, *LYR_POLY)
        assert len(polys) >= 1, "Expected poly body"

    def test_has_rpm(self, result):
        rpms = _polys_on_layer(result.cell, *LYR_RPM)
        assert len(rpms) == 1, "Expected one RPM marker for single segment"

    def test_has_poly_rs(self, result):
        poly_rs = _polys_on_layer(result.cell, *LYR_POLY_RS)
        assert len(poly_rs) == 1, "Expected one poly_rs marker"

    def test_has_psdm(self, result):
        psdm = _polys_on_layer(result.cell, *LYR_PSDM)
        assert len(psdm) == 1, "Expected PSDM implant layer"

    def test_has_npc(self, result):
        npc = _polys_on_layer(result.cell, *LYR_NPC)
        assert len(npc) >= 1, "Expected NPC layer"

    def test_has_contacts(self, result):
        licons = _polys_on_layer(result.cell, *LYR_LICON)
        mcons = _polys_on_layer(result.cell, *LYR_MCON)
        assert len(licons) >= 2, "Expected licons at head and tail"
        assert len(mcons) >= 2, "Expected mcons at head and tail"

    def test_has_li1(self, result):
        li1 = _polys_on_layer(result.cell, *LYR_LI1)
        assert len(li1) >= 2, "Expected li1 at head and tail"

    def test_has_met1(self, result):
        met1 = _polys_on_layer(result.cell, *LYR_MET1)
        assert len(met1) >= 2, "Expected met1 pads at head and tail"

    def test_pin_labels_plus_minus(self, result):
        labels = _labels_on_layer(result.cell, *LYR_MET1_LBL)
        label_texts = {lb.text for lb in labels}
        assert "PLUS" in label_texts, "Missing PLUS pin label"
        assert "MINUS" in label_texts, "Missing MINUS pin label"

    def test_rpm_min_width_satisfied(self, result):
        """RPM must satisfy minimum width (1.27um) in both dimensions."""
        rpms = _polys_on_layer(result.cell, *LYR_RPM)
        for rpm in rpms:
            bb = rpm.bounding_box()
            rpm_w = bb[1][0] - bb[0][0]
            rpm_h = bb[1][1] - bb[0][1]
            assert rpm_w >= SKY130_RES.rpm_min_width - 0.001, (
                f"RPM width {rpm_w} < min {SKY130_RES.rpm_min_width}"
            )
            assert rpm_h >= SKY130_RES.rpm_min_width - 0.001, (
                f"RPM height {rpm_h} < min {SKY130_RES.rpm_min_width}"
            )

    def test_total_resistance_length(self, result):
        assert result.metadata["total_resistance_length_um"] == pytest.approx(2.0, abs=0.01)

    def test_cell_writes_gds(self, result, tmp_path):
        lib = gdstk.Library()
        lib.add(result.cell)
        out = tmp_path / "test_res.gds"
        lib.write_gds(str(out))
        assert out.stat().st_size > 0

    def test_deterministic(self, gen):
        params = {"w_um": 0.50, "l_um": 2.0, "segments": 1}
        r1 = gen.generate(params)
        r2 = gen.generate(params)
        assert r1.cell_name == r2.cell_name
        for lyr in [LYR_POLY, LYR_RPM, LYR_LICON, LYR_MET1]:
            p1 = _polys_on_layer(r1.cell, *lyr)
            p2 = _polys_on_layer(r2.cell, *lyr)
            assert len(p1) == len(p2), f"Non-deterministic on layer {lyr}"


# ---------------------------------------------------------------------------
# 3-segment serpentine
# ---------------------------------------------------------------------------
class TestThreeSegmentSerpentine:
    """Test: 3-segment serpentine -> verify U-turns, total resistance length."""

    @pytest.fixture
    def result(self, gen):
        return gen.generate({"w_um": 0.50, "l_um": 2.0, "segments": 3})

    def test_cell_name(self, result):
        assert "S3" in result.cell_name

    def test_three_rpm_markers(self, result):
        rpms = _polys_on_layer(result.cell, *LYR_RPM)
        assert len(rpms) == 3, "Expected 3 RPM markers for 3 segments"

    def test_three_poly_rs_markers(self, result):
        poly_rs = _polys_on_layer(result.cell, *LYR_POLY_RS)
        assert len(poly_rs) == 3, "Expected 3 poly_rs markers"

    def test_total_resistance_length(self, result):
        expected = 3 * 2.0
        assert result.metadata["total_resistance_length_um"] == pytest.approx(
            expected, abs=0.01
        )

    def test_has_uturn_poly(self, result):
        """3 segments need 2 U-turns → more poly rectangles than segments."""
        polys = _polys_on_layer(result.cell, *LYR_POLY)
        # 3 segment bodies + 2 U-turn bridges = 5 poly rectangles minimum
        assert len(polys) >= 5, (
            f"Expected at least 5 poly rects (3 segments + 2 U-turns), got {len(polys)}"
        )

    def test_pin_labels(self, result):
        labels = _labels_on_layer(result.cell, *LYR_MET1_LBL)
        label_texts = {lb.text for lb in labels}
        assert "PLUS" in label_texts
        assert "MINUS" in label_texts

    def test_segments_metadata(self, result):
        assert result.metadata["segments"] == 3

    def test_cell_writes_gds(self, result, tmp_path):
        lib = gdstk.Library()
        lib.add(result.cell)
        out = tmp_path / "test_res3.gds"
        lib.write_gds(str(out))
        assert out.stat().st_size > 0


# ---------------------------------------------------------------------------
# No-contact variant
# ---------------------------------------------------------------------------
class TestNoContacts:
    def test_no_head_contact(self, gen):
        result = gen.generate(
            {"w_um": 0.50, "l_um": 2.0, "segments": 1, "head_contact": False}
        )
        labels = _labels_on_layer(result.cell, *LYR_MET1_LBL)
        label_texts = {lb.text for lb in labels}
        assert "PLUS" not in label_texts, "Should not have PLUS without head contact"
        assert "MINUS" in label_texts

    def test_no_tail_contact(self, gen):
        result = gen.generate(
            {"w_um": 0.50, "l_um": 2.0, "segments": 1, "tail_contact": False}
        )
        labels = _labels_on_layer(result.cell, *LYR_MET1_LBL)
        label_texts = {lb.text for lb in labels}
        assert "PLUS" in label_texts
        assert "MINUS" not in label_texts, "Should not have MINUS without tail contact"


# ---------------------------------------------------------------------------
# Param schema
# ---------------------------------------------------------------------------
class TestResistorParamSchema:
    def test_has_required_params(self, gen):
        schema = gen.param_schema()
        assert "w_um" in schema
        assert "l_um" in schema
        assert "segments" in schema
        assert "head_contact" in schema
        assert "tail_contact" in schema

    def test_defaults(self, gen):
        schema = gen.param_schema()
        assert schema["segments"]["default"] == 1
        assert schema["head_contact"]["default"] is True
        assert schema["tail_contact"]["default"] is True

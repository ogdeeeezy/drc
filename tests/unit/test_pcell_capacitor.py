"""Tests for the MIM capacitor parameterized cell generator."""

import gdstk
import pytest

from backend.pcell.capacitor import (
    LYR_CAPM,
    LYR_MET2,
    LYR_MET3,
    LYR_MET3_LBL,
    LYR_MET4,
    LYR_MET4_LBL,
    LYR_VIA2,
    LYR_VIA3,
    SKY130_MIM,
    MIMCapGenerator,
)


@pytest.fixture
def gen():
    return MIMCapGenerator()


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
class TestMIMCapValidation:
    def test_w_too_small(self, gen):
        with pytest.raises(ValueError, match="w_um"):
            gen.validate_params({"w_um": 0.5, "l_um": 2.0})

    def test_l_too_small(self, gen):
        with pytest.raises(ValueError, match="l_um"):
            gen.validate_params({"w_um": 2.0, "l_um": 0.5})

    def test_w_none(self, gen):
        with pytest.raises(ValueError, match="w_um"):
            gen.validate_params({"l_um": 2.0})

    def test_l_none(self, gen):
        with pytest.raises(ValueError, match="l_um"):
            gen.validate_params({"w_um": 2.0})

    def test_valid_params(self, gen):
        gen.validate_params({"w_um": 2.0, "l_um": 2.0})

    def test_min_dimension_accepted(self, gen):
        gen.validate_params(
            {
                "w_um": SKY130_MIM.capm_min_width,
                "l_um": SKY130_MIM.capm_min_width,
            }
        )


# ---------------------------------------------------------------------------
# param_schema
# ---------------------------------------------------------------------------
class TestMIMCapSchema:
    def test_schema_keys(self, gen):
        schema = gen.param_schema()
        assert "w_um" in schema
        assert "l_um" in schema

    def test_schema_min_values(self, gen):
        schema = gen.param_schema()
        assert schema["w_um"]["min"] == SKY130_MIM.capm_min_width
        assert schema["l_um"]["min"] == SKY130_MIM.capm_min_width


# ---------------------------------------------------------------------------
# Basic generation
# ---------------------------------------------------------------------------
class TestMIMCapGeneration:
    def test_basic_generation(self, gen):
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        assert result.cell is not None
        assert result.cell_name.startswith("sky130_mimcap")
        assert result.params["w_um"] == 5.0
        assert result.params["l_um"] == 5.0

    def test_cell_name_format(self, gen):
        result = gen.generate({"w_um": 3.0, "l_um": 4.0})
        assert "sky130" in result.cell_name
        assert "mimcap" in result.cell_name

    def test_met3_bottom_plate_present(self, gen):
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        met3 = _polys_on_layer(result.cell, *LYR_MET3)
        assert len(met3) >= 1, "Expected at least one met3 polygon (bottom plate)"

    def test_capm_top_plate_present(self, gen):
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        capm = _polys_on_layer(result.cell, *LYR_CAPM)
        assert len(capm) == 1, "Expected exactly one CAPM polygon (top plate)"

    def test_via3_present(self, gen):
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        via3 = _polys_on_layer(result.cell, *LYR_VIA3)
        assert len(via3) > 0, "Expected via3 contacts on top plate"

    def test_via2_present(self, gen):
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        via2 = _polys_on_layer(result.cell, *LYR_VIA2)
        assert len(via2) > 0, "Expected via2 contacts for bottom plate routing"

    def test_met4_top_routing(self, gen):
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        met4 = _polys_on_layer(result.cell, *LYR_MET4)
        assert len(met4) >= 1, "Expected met4 routing for TOP terminal"

    def test_met2_bot_routing(self, gen):
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        met2 = _polys_on_layer(result.cell, *LYR_MET2)
        assert len(met2) >= 1, "Expected met2 routing for BOT terminal"

    def test_met3_encloses_capm(self, gen):
        """Met3 must extend beyond CAPM on all sides."""
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        met3 = _polys_on_layer(result.cell, *LYR_MET3)
        capm = _polys_on_layer(result.cell, *LYR_CAPM)

        met3_bb = met3[0].bounding_box()
        capm_bb = capm[0].bounding_box()

        # met3 should fully enclose CAPM
        assert met3_bb[0][0] < capm_bb[0][0], "met3 left should be left of CAPM"
        assert met3_bb[0][1] < capm_bb[0][1], "met3 bottom should be below CAPM"
        assert met3_bb[1][0] > capm_bb[1][0], "met3 right should be right of CAPM"
        assert met3_bb[1][1] > capm_bb[1][1], "met3 top should be above CAPM"


# ---------------------------------------------------------------------------
# Pin labels
# ---------------------------------------------------------------------------
class TestMIMCapLabels:
    def test_top_label(self, gen):
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        labels = _labels_on_layer(result.cell, *LYR_MET4_LBL)
        texts = [lb.text for lb in labels]
        assert "TOP" in texts, "Expected 'TOP' label on met4"

    def test_bot_label(self, gen):
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        labels = _labels_on_layer(result.cell, *LYR_MET3_LBL)
        texts = [lb.text for lb in labels]
        assert "BOT" in texts, "Expected 'BOT' label on met3 label layer"


# ---------------------------------------------------------------------------
# Capacitance calculation
# ---------------------------------------------------------------------------
class TestMIMCapMetadata:
    def test_capacitance_5x5(self, gen):
        """5um x 5um = 25um^2, at 2 fF/um^2 = 50 fF."""
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        assert result.metadata["capacitance_fF"] == pytest.approx(50.0)
        assert result.metadata["area_um2"] == pytest.approx(25.0)

    def test_capacitance_2x3(self, gen):
        """2um x 3um = 6um^2, at 2 fF/um^2 = 12 fF."""
        result = gen.generate({"w_um": 2.0, "l_um": 3.0})
        assert result.metadata["capacitance_fF"] == pytest.approx(12.0)
        assert result.metadata["area_um2"] == pytest.approx(6.0)

    def test_cap_density_in_metadata(self, gen):
        result = gen.generate({"w_um": 2.0, "l_um": 2.0})
        assert result.metadata["cap_density_fF_per_um2"] == 2.0

    def test_via_counts_in_metadata(self, gen):
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        assert result.metadata["n_via3"] > 0
        assert result.metadata["n_via2"] > 0


# ---------------------------------------------------------------------------
# Minimum dimensions
# ---------------------------------------------------------------------------
class TestMIMCapMinDimensions:
    def test_min_size_generates(self, gen):
        """Minimum CAPM dimensions should still produce a valid cell."""
        result = gen.generate(
            {
                "w_um": SKY130_MIM.capm_min_width,
                "l_um": SKY130_MIM.capm_min_width,
            }
        )
        assert result.cell is not None
        # Should have at least met3, CAPM
        met3 = _polys_on_layer(result.cell, *LYR_MET3)
        capm = _polys_on_layer(result.cell, *LYR_CAPM)
        assert len(met3) >= 1
        assert len(capm) == 1

    def test_capacitance_at_min_size(self, gen):
        """1um x 1um = 1 um^2, at 2 fF/um^2 = 2 fF."""
        result = gen.generate(
            {
                "w_um": SKY130_MIM.capm_min_width,
                "l_um": SKY130_MIM.capm_min_width,
            }
        )
        expected = SKY130_MIM.capm_min_width**2 * SKY130_MIM.cap_per_um2_fF
        assert result.metadata["capacitance_fF"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------
class TestMIMCapDeterminism:
    def test_same_params_same_result(self, gen):
        """Same parameters should produce identical cells."""
        r1 = gen.generate({"w_um": 3.0, "l_um": 4.0})
        r2 = gen.generate({"w_um": 3.0, "l_um": 4.0})
        assert r1.cell_name == r2.cell_name
        assert len(r1.cell.polygons) == len(r2.cell.polygons)
        assert r1.metadata == r2.metadata


# ---------------------------------------------------------------------------
# GDS write (smoke test)
# ---------------------------------------------------------------------------
class TestMIMCapGDSWrite:
    def test_write_gds(self, gen, tmp_path):
        """Verify the generated cell can be written to a GDS file."""
        result = gen.generate({"w_um": 5.0, "l_um": 5.0})
        lib = gdstk.Library()
        lib.add(result.cell)
        gds_path = tmp_path / "mim_cap.gds"
        lib.write_gds(str(gds_path))
        assert gds_path.exists()
        assert gds_path.stat().st_size > 0

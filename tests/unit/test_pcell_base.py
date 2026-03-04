"""Tests for PCell base framework."""

from backend.pcell.base import PCellGenerator, PCellResult


class TestSnapToGrid:
    def test_exact_grid_value(self):
        assert PCellGenerator.snap_to_grid(0.150) == 0.150

    def test_rounds_down(self):
        assert PCellGenerator.snap_to_grid(0.152) == 0.150

    def test_rounds_up(self):
        assert PCellGenerator.snap_to_grid(0.153) == 0.155

    def test_zero(self):
        assert PCellGenerator.snap_to_grid(0.0) == 0.0

    def test_custom_grid(self):
        assert PCellGenerator.snap_to_grid(0.27, grid=0.01) == 0.27
        assert PCellGenerator.snap_to_grid(0.275, grid=0.01) == 0.28


class TestCellNameFormat:
    def test_basic(self):
        name = PCellGenerator.cell_name_format("sky130", "nmos", W=0.42, L=0.15, F=1)
        assert name == "sky130_nmos_W0p42_L0p15_F1"

    def test_integer_param(self):
        name = PCellGenerator.cell_name_format("sky130", "pmos", W=1.0, L=0.15, F=4)
        assert name == "sky130_pmos_W1_L0p15_F4"

    def test_trailing_zeros_stripped(self):
        name = PCellGenerator.cell_name_format("sky130", "nmos", W=0.500, L=0.150, F=2)
        assert "W0p5" in name
        assert "L0p15" in name


class TestPCellResult:
    def test_default_metadata(self):
        import gdstk

        cell = gdstk.Cell("test")
        result = PCellResult(cell=cell, cell_name="test", params={})
        assert result.metadata == {}

    def test_with_metadata(self):
        import gdstk

        cell = gdstk.Cell("test2")
        result = PCellResult(
            cell=cell,
            cell_name="test2",
            params={"w": 1.0},
            metadata={"capacitance_fF": 42.0},
        )
        assert result.metadata["capacitance_fF"] == 42.0
        assert result.params["w"] == 1.0

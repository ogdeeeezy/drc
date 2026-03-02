"""GDSII layout manager — load, extract, modify, and save layouts using gdstk."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import gdstk

from backend.pdk.schema import PDKConfig


@dataclass
class PolygonInfo:
    """A polygon with its layer context."""

    points: list[tuple[float, float]]
    gds_layer: int
    gds_datatype: int
    cell_name: str

    @property
    def layer_pair(self) -> tuple[int, int]:
        return (self.gds_layer, self.gds_datatype)


@dataclass
class CellInfo:
    """Summary info for a cell in the layout."""

    name: str
    polygon_count: int
    reference_count: int
    bbox: tuple[float, float, float, float] | None


class LayoutManager:
    """Manages GDSII layout I/O and polygon queries via gdstk."""

    def __init__(self):
        self._library: gdstk.Library | None = None
        self._source_path: Path | None = None

    @property
    def library(self) -> gdstk.Library:
        if self._library is None:
            raise RuntimeError("No layout loaded. Call load() first.")
        return self._library

    @property
    def source_path(self) -> Path | None:
        return self._source_path

    def load(self, gds_path: str | Path) -> None:
        """Load a GDSII file."""
        path = Path(gds_path)
        if not path.exists():
            raise FileNotFoundError(f"GDSII file not found: {path}")
        self._library = gdstk.read_gds(str(path))
        self._source_path = path

    def save(self, output_path: str | Path) -> Path:
        """Save the current layout to a GDSII file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.library.write_gds(str(path))
        return path

    def new_library(self, name: str = "agentic_drc") -> None:
        """Create a new empty library."""
        self._library = gdstk.Library(name)
        self._source_path = None

    def list_cells(self) -> list[CellInfo]:
        """List all cells in the layout."""
        result = []
        for cell in self.library.cells:
            bbox = cell.bounding_box()
            bbox_tuple = None
            if bbox is not None:
                bbox_tuple = (
                    float(bbox[0][0]),
                    float(bbox[0][1]),
                    float(bbox[1][0]),
                    float(bbox[1][1]),
                )
            result.append(
                CellInfo(
                    name=cell.name,
                    polygon_count=len(cell.polygons),
                    reference_count=len(cell.references),
                    bbox=bbox_tuple,
                )
            )
        return result

    def get_cell(self, name: str) -> gdstk.Cell:
        """Get a cell by name."""
        for cell in self.library.cells:
            if cell.name == name:
                return cell
        raise KeyError(f"Cell '{name}' not found in layout")

    def get_top_cells(self) -> list[gdstk.Cell]:
        """Get top-level cells (not referenced by any other cell)."""
        return list(self.library.top_level())

    def get_polygons(
        self,
        cell_name: str | None = None,
        layer: int | None = None,
        datatype: int | None = None,
    ) -> list[PolygonInfo]:
        """Extract polygons, optionally filtered by cell and/or layer.

        If cell_name is None, uses the first top-level cell.
        """
        if cell_name is None:
            top = self.get_top_cells()
            if not top:
                return []
            cell = top[0]
        else:
            cell = self.get_cell(cell_name)

        result = []
        for poly in cell.polygons:
            if layer is not None and poly.layer != layer:
                continue
            if datatype is not None and poly.datatype != datatype:
                continue
            points = [(float(p[0]), float(p[1])) for p in poly.points]
            result.append(
                PolygonInfo(
                    points=points,
                    gds_layer=poly.layer,
                    gds_datatype=poly.datatype,
                    cell_name=cell.name,
                )
            )
        return result

    def get_polygons_for_pdk_layer(
        self,
        pdk: PDKConfig,
        layer_name: str,
        cell_name: str | None = None,
    ) -> list[PolygonInfo]:
        """Get polygons for a named PDK layer."""
        gds_layer_info = pdk.get_layer(layer_name)
        return self.get_polygons(
            cell_name=cell_name,
            layer=gds_layer_info.gds_layer,
            datatype=gds_layer_info.gds_datatype,
        )

    def get_flattened_polygons(
        self,
        cell_name: str | None = None,
        layer: int | None = None,
        datatype: int | None = None,
    ) -> list[PolygonInfo]:
        """Get polygons from a flattened (hierarchy-resolved) view of a cell.

        This resolves all cell references, giving the complete set of polygons
        as they appear in the physical layout.
        """
        if cell_name is None:
            top = self.get_top_cells()
            if not top:
                return []
            cell = top[0]
        else:
            cell = self.get_cell(cell_name)

        # gdstk flatten creates a copy, so we flatten a copy to preserve the original
        flat_cell = cell.copy(cell.name + "_flat")
        flat_cell.flatten()

        result = []
        for poly in flat_cell.polygons:
            if layer is not None and poly.layer != layer:
                continue
            if datatype is not None and poly.datatype != datatype:
                continue
            points = [(float(p[0]), float(p[1])) for p in poly.points]
            result.append(
                PolygonInfo(
                    points=points,
                    gds_layer=poly.layer,
                    gds_datatype=poly.datatype,
                    cell_name=cell.name,
                )
            )
        return result

    def add_polygon(
        self,
        cell_name: str,
        points: list[tuple[float, float]],
        layer: int,
        datatype: int = 0,
    ) -> None:
        """Add a polygon to a cell."""
        cell = self.get_cell(cell_name)
        cell.add(gdstk.Polygon(points, layer=layer, datatype=datatype))

    def remove_polygon(self, cell_name: str, polygon_index: int) -> None:
        """Remove a polygon from a cell by index."""
        cell = self.get_cell(cell_name)
        if polygon_index < 0 or polygon_index >= len(cell.polygons):
            raise IndexError(
                f"Polygon index {polygon_index} out of range for cell '{cell_name}' "
                f"(has {len(cell.polygons)} polygons)"
            )
        cell.remove(cell.polygons[polygon_index])

    def replace_polygon(
        self,
        cell_name: str,
        polygon_index: int,
        new_points: list[tuple[float, float]],
    ) -> None:
        """Replace a polygon's geometry (same layer/datatype, new points)."""
        cell = self.get_cell(cell_name)
        if polygon_index < 0 or polygon_index >= len(cell.polygons):
            raise IndexError(f"Polygon index {polygon_index} out of range for cell '{cell_name}'")
        old_poly = cell.polygons[polygon_index]
        new_poly = gdstk.Polygon(new_points, layer=old_poly.layer, datatype=old_poly.datatype)
        cell.remove(old_poly)
        cell.add(new_poly)

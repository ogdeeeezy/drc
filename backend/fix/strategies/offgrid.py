"""Off-grid fix strategy.

Snap vertices to nearest grid point. Round conservatively (toward more width/spacing).
"""

from __future__ import annotations

from backend.core.geometry_utils import (
    bbox_height,
    bbox_width,
    polygon_bbox,
    snap_to_grid,
)
from backend.core.spatial_index import SpatialIndex
from backend.core.violation_models import Violation, ViolationGeometry
from backend.fix.fix_models import FixConfidence, FixSuggestion, PolygonDelta
from backend.fix.strategies.base import FixStrategy
from backend.pdk.schema import PDKConfig


class OffGridFix(FixStrategy):
    """Fix off-grid violations by snapping vertices to the manufacturing grid.

    Uses conservative rounding: when a vertex is between two grid points,
    snap in the direction that increases width/spacing (outward for width,
    away for spacing).
    """

    @property
    def rule_type(self) -> str:
        return "off_grid"

    @property
    def name(self) -> str:
        return "Off-Grid Fix"

    def can_fix(self, violation: Violation) -> bool:
        return violation.rule_type == "off_grid"

    def suggest_fix(
        self,
        violation: Violation,
        geometry: ViolationGeometry,
        pdk: PDKConfig,
        spatial_index: SpatialIndex,
    ) -> FixSuggestion | None:
        grid = pdk.grid_um
        vbox = geometry.bbox

        # Find the polygon containing the off-grid vertex
        nearby = spatial_index.query_bbox(vbox)
        if not nearby:
            nearby = spatial_index.query_nearby(vbox, margin=grid * 5)
        if not nearby:
            return None

        target_poly = nearby[0]
        original = target_poly.polygon.points
        orig_bbox = polygon_bbox(original)
        center_x = (orig_bbox[0] + orig_bbox[2]) / 2
        center_y = (orig_bbox[1] + orig_bbox[3]) / 2

        # Snap all off-grid vertices conservatively
        new_points = []
        any_changed = False
        for x, y in original:
            nx = self._conservative_snap(x, grid, center_x)
            ny = self._conservative_snap(y, grid, center_y)
            if abs(nx - x) > 1e-12 or abs(ny - y) > 1e-12:
                any_changed = True
            new_points.append((nx, ny))

        if not any_changed:
            return None

        # Verify the snapped polygon isn't degenerate
        new_bbox = polygon_bbox(new_points)
        if bbox_width(new_bbox) < grid or bbox_height(new_bbox) < grid:
            return None

        delta = PolygonDelta(
            cell_name=target_poly.polygon.cell_name,
            gds_layer=target_poly.polygon.gds_layer,
            gds_datatype=target_poly.polygon.gds_datatype,
            original_points=original,
            modified_points=new_points,
        )

        return FixSuggestion(
            violation_category=violation.category,
            rule_type=self.rule_type,
            description=f"Snap off-grid vertices to {grid}um grid",
            deltas=[delta],
            confidence=FixConfidence.high,
            priority=2,  # Off-grid is second highest priority
        )

    def _conservative_snap(
        self, value: float, grid: float, center: float
    ) -> float:
        """Snap to grid conservatively — away from center (outward).

        This ensures snapping doesn't reduce polygon width.
        """
        import math

        lower = math.floor(value / grid) * grid
        upper = math.ceil(value / grid) * grid

        # If already on grid
        if abs(value - lower) < 1e-12:
            return lower
        if abs(value - upper) < 1e-12:
            return upper

        # Snap away from center (conservative = more width/area)
        if value < center:
            return lower  # move outward (away from center, toward negative)
        else:
            return upper  # move outward (away from center, toward positive)

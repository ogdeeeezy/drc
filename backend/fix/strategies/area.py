"""Min-area fix strategy.

Extend wire length in the least-constrained direction by deficit / current_width.
"""

from __future__ import annotations

from backend.core.geometry_utils import (
    bbox_height,
    bbox_width,
    polygon_area,
    polygon_bbox,
    snap_to_grid,
)
from backend.core.spatial_index import SpatialIndex
from backend.core.violation_models import GeometryType, Violation, ViolationGeometry
from backend.fix.fix_models import FixConfidence, FixSuggestion, PolygonDelta
from backend.fix.strategies.base import FixStrategy
from backend.pdk.schema import PDKConfig


class MinAreaFix(FixStrategy):
    """Fix min-area violations by extending the polygon in its longest direction."""

    @property
    def rule_type(self) -> str:
        return "min_area"

    @property
    def name(self) -> str:
        return "Minimum Area Fix"

    def can_fix(self, violation: Violation) -> bool:
        return violation.rule_type == "min_area"

    def suggest_fix(
        self,
        violation: Violation,
        geometry: ViolationGeometry,
        pdk: PDKConfig,
        spatial_index: SpatialIndex,
    ) -> FixSuggestion | None:
        min_area = violation.value_um
        if min_area is None:
            return None

        grid = pdk.grid_um

        # For area violations, the geometry is typically a polygon marker
        # showing the undersized polygon itself
        if geometry.geometry_type == GeometryType.polygon and geometry.points:
            target_points = geometry.points
        elif geometry.geometry_type == GeometryType.edge_pair and geometry.edge_pair:
            # Find the polygon at the edge pair location
            target_points = self._find_polygon_points(
                geometry.edge_pair.bbox, spatial_index
            )
            if target_points is None:
                return None
        else:
            return None

        # Find the actual polygon in the spatial index
        target_bbox = polygon_bbox(target_points)
        target_poly = None
        nearby = spatial_index.query_bbox(target_bbox)
        for ip in nearby:
            ip_bbox = polygon_bbox(ip.polygon.points)
            # Match by overlapping bbox
            if (
                abs(ip_bbox[0] - target_bbox[0]) < grid
                and abs(ip_bbox[1] - target_bbox[1]) < grid
                and abs(ip_bbox[2] - target_bbox[2]) < grid
                and abs(ip_bbox[3] - target_bbox[3]) < grid
            ):
                target_poly = ip
                break

        if target_poly is None:
            if nearby:
                target_poly = nearby[0]
            else:
                return None

        original = target_poly.polygon.points
        orig_bbox = polygon_bbox(original)
        current_area = polygon_area(original)
        area_deficit = min_area - current_area

        if area_deficit <= 0:
            return None

        w = bbox_width(orig_bbox)
        h = bbox_height(orig_bbox)

        if w <= 0 or h <= 0:
            return None

        # Extend in the shorter dimension's perpendicular (i.e., along the longer axis)
        # For a wire: extend length, not width (width might already be at minimum)
        if w >= h:
            # Wider than tall → extend horizontally (along X)
            extend_amount = snap_to_grid(area_deficit / h, grid)
            # Extend toward less-constrained direction
            extend_right, extend_left = self._pick_extension_dir(
                orig_bbox, spatial_index, "x",
                target_poly.polygon.gds_layer, extend_amount, grid
            )
            new_points = self._extend_x(original, orig_bbox, extend_left, extend_right, grid)
        else:
            # Taller than wide → extend vertically (along Y)
            extend_amount = snap_to_grid(area_deficit / w, grid)
            extend_up, extend_down = self._pick_extension_dir(
                orig_bbox, spatial_index, "y",
                target_poly.polygon.gds_layer, extend_amount, grid
            )
            new_points = self._extend_y(original, orig_bbox, extend_down, extend_up, grid)

        if new_points == original:
            return None

        delta = PolygonDelta(
            cell_name=target_poly.polygon.cell_name,
            gds_layer=target_poly.polygon.gds_layer,
            gds_datatype=target_poly.polygon.gds_datatype,
            original_points=original,
            modified_points=new_points,
        )

        new_area = polygon_area(new_points)
        return FixSuggestion(
            violation_category=violation.category,
            rule_type=self.rule_type,
            description=(
                f"Extend polygon to area {new_area:.4f}um² "
                f"(min: {min_area:.4f}um²)"
            ),
            deltas=[delta],
            confidence=FixConfidence.high,
            priority=violation.severity,
        )

    def _find_polygon_points(self, bbox, spatial_index):
        """Find polygon points from spatial index matching a bbox."""
        nearby = spatial_index.query_bbox(bbox)
        if nearby:
            return nearby[0].polygon.points
        return None

    def _pick_extension_dir(
        self, bbox, spatial_index, axis, layer, amount, grid
    ):
        """Pick which direction to extend, preferring the less-constrained side.

        Returns (positive_extend, negative_extend).
        """
        margin = amount + 0.1
        if axis == "x":
            right_q = (bbox[2], bbox[1], bbox[2] + margin, bbox[3])
            left_q = (bbox[0] - margin, bbox[1], bbox[0], bbox[3])
        else:
            right_q = (bbox[0], bbox[3], bbox[2], bbox[3] + margin)
            left_q = (bbox[0], bbox[1] - margin, bbox[2], bbox[1])

        right_blocked = any(
            ip.polygon.gds_layer == layer
            for ip in spatial_index.query_bbox(right_q)
            if ip.bbox != bbox
        )
        left_blocked = any(
            ip.polygon.gds_layer == layer
            for ip in spatial_index.query_bbox(left_q)
            if ip.bbox != bbox
        )

        if right_blocked and not left_blocked:
            return (0.0, snap_to_grid(amount, grid))
        elif left_blocked and not right_blocked:
            return (snap_to_grid(amount, grid), 0.0)
        else:
            # Default: extend in positive direction
            return (snap_to_grid(amount, grid), 0.0)

    def _extend_x(self, points, bbox, extend_left, extend_right, grid):
        new_points = []
        for x, y in points:
            if extend_right > 0 and abs(x - bbox[2]) < grid / 2:
                new_points.append((snap_to_grid(x + extend_right, grid), y))
            elif extend_left > 0 and abs(x - bbox[0]) < grid / 2:
                new_points.append((snap_to_grid(x - extend_left, grid), y))
            else:
                new_points.append((x, y))
        return new_points

    def _extend_y(self, points, bbox, extend_down, extend_up, grid):
        new_points = []
        for x, y in points:
            if extend_up > 0 and abs(y - bbox[3]) < grid / 2:
                new_points.append((x, snap_to_grid(y + extend_up, grid)))
            elif extend_down > 0 and abs(y - bbox[1]) < grid / 2:
                new_points.append((x, snap_to_grid(y - extend_down, grid)))
            else:
                new_points.append((x, y))
        return new_points

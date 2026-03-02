"""Min-width fix strategy.

Expand polygon outward toward free space by the deficit amount.
If both sides are constrained, split the expansion evenly.
"""

from __future__ import annotations

from backend.core.geometry_utils import (
    polygon_bbox,
    snap_to_grid,
)
from backend.core.spatial_index import SpatialIndex
from backend.core.violation_models import GeometryType, Violation, ViolationGeometry
from backend.fix.fix_models import FixConfidence, FixSuggestion, PolygonDelta
from backend.fix.strategies.base import FixStrategy
from backend.pdk.schema import PDKConfig


class MinWidthFix(FixStrategy):
    """Fix min-width violations by expanding the polygon."""

    @property
    def rule_type(self) -> str:
        return "min_width"

    @property
    def name(self) -> str:
        return "Minimum Width Fix"

    def can_fix(self, violation: Violation) -> bool:
        return violation.rule_type == "min_width"

    def suggest_fix(
        self,
        violation: Violation,
        geometry: ViolationGeometry,
        pdk: PDKConfig,
        spatial_index: SpatialIndex,
    ) -> FixSuggestion | None:
        if geometry.geometry_type != GeometryType.edge_pair:
            return None
        if geometry.edge_pair is None:
            return None

        ep = geometry.edge_pair
        min_width = violation.value_um
        if min_width is None:
            return None

        # Determine the violation bounding box and which dimension is narrow
        vbox = ep.bbox
        w = vbox[2] - vbox[0]
        h = vbox[3] - vbox[1]

        # The narrow dimension is the one that violates min_width
        # Edge pairs for width: two parallel edges of the same polygon
        is_narrow_x = w < h  # narrow in X → edges are vertical, expand horizontally
        deficit = min_width - (w if is_narrow_x else h)

        if deficit <= 0:
            return None

        grid = pdk.grid_um

        # Find the polygon that contains this violation
        nearby = spatial_index.query_bbox(vbox)
        target_poly = None
        for ip in nearby:
            # Find the polygon on the same layer whose bbox overlaps the violation
            poly_bbox = polygon_bbox(ip.polygon.points)
            if self._bbox_contains(poly_bbox, vbox):
                target_poly = ip
                break

        if target_poly is None:
            # Fallback: use the nearest polygon
            if nearby:
                target_poly = nearby[0]
            else:
                return None

        original = target_poly.polygon.points
        orig_bbox = polygon_bbox(original)

        # Determine expansion direction and check for obstacles
        half_deficit = snap_to_grid(deficit / 2, grid)
        full_deficit = snap_to_grid(deficit, grid)

        if is_narrow_x:
            # Expand left and/or right
            expand_left, expand_right = self._compute_expansion(
                center_min=orig_bbox[0],
                center_max=orig_bbox[2],
                deficit=full_deficit,
                half=half_deficit,
                spatial_index=spatial_index,
                bbox=orig_bbox,
                axis="x",
                layer=target_poly.polygon.gds_layer,
            )
            new_points = self._expand_rectilinear_x(original, expand_left, expand_right, grid)
        else:
            # Expand up and/or down
            expand_down, expand_up = self._compute_expansion(
                center_min=orig_bbox[1],
                center_max=orig_bbox[3],
                deficit=full_deficit,
                half=half_deficit,
                spatial_index=spatial_index,
                bbox=orig_bbox,
                axis="y",
                layer=target_poly.polygon.gds_layer,
            )
            new_points = self._expand_rectilinear_y(original, expand_down, expand_up, grid)

        if new_points == original:
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
            description=(
                f"Expand polygon by {full_deficit:.3f}um to meet min width {min_width:.3f}um"
            ),
            deltas=[delta],
            confidence=FixConfidence.high,
            priority=violation.severity,
        )

    def _compute_expansion(
        self,
        center_min: float,
        center_max: float,
        deficit: float,
        half: float,
        spatial_index: SpatialIndex,
        bbox: tuple[float, float, float, float],
        axis: str,
        layer: int,
    ) -> tuple[float, float]:
        """Decide how much to expand on each side.

        Returns (expand_negative, expand_positive) amounts.
        Prefers symmetric expansion but shifts if one side is blocked.
        """
        # Check for obstacles on each side
        margin = deficit + 0.1  # extra margin for obstacle detection
        if axis == "x":
            left_query = (bbox[0] - margin, bbox[1], bbox[0], bbox[3])
            right_query = (bbox[2], bbox[1], bbox[2] + margin, bbox[3])
        else:
            left_query = (bbox[0], bbox[1] - margin, bbox[2], bbox[1])
            right_query = (bbox[0], bbox[3], bbox[2], bbox[3] + margin)

        left_blocked = any(
            ip.polygon.gds_layer == layer
            for ip in spatial_index.query_bbox(left_query)
            if ip.bbox != bbox
        )
        right_blocked = any(
            ip.polygon.gds_layer == layer
            for ip in spatial_index.query_bbox(right_query)
            if ip.bbox != bbox
        )

        if left_blocked and not right_blocked:
            return (0.0, deficit)
        elif right_blocked and not left_blocked:
            return (deficit, 0.0)
        else:
            # Both free or both blocked — split evenly
            return (half, half)

    def _expand_rectilinear_x(
        self,
        points: list[tuple[float, float]],
        expand_left: float,
        expand_right: float,
        grid: float,
    ) -> list[tuple[float, float]]:
        """Expand a rectilinear polygon horizontally."""
        if not points:
            return points
        bbox = polygon_bbox(points)
        xmin, xmax = bbox[0], bbox[2]
        new_points = []
        for x, y in points:
            if abs(x - xmin) < grid / 2:
                nx = snap_to_grid(x - expand_left, grid)
            elif abs(x - xmax) < grid / 2:
                nx = snap_to_grid(x + expand_right, grid)
            else:
                nx = x
            new_points.append((nx, y))
        return new_points

    def _expand_rectilinear_y(
        self,
        points: list[tuple[float, float]],
        expand_down: float,
        expand_up: float,
        grid: float,
    ) -> list[tuple[float, float]]:
        """Expand a rectilinear polygon vertically."""
        if not points:
            return points
        bbox = polygon_bbox(points)
        ymin, ymax = bbox[1], bbox[3]
        new_points = []
        for x, y in points:
            if abs(y - ymin) < grid / 2:
                ny = snap_to_grid(y - expand_down, grid)
            elif abs(y - ymax) < grid / 2:
                ny = snap_to_grid(y + expand_up, grid)
            else:
                ny = y
            new_points.append((x, ny))
        return new_points

    def _bbox_contains(
        self,
        outer: tuple[float, float, float, float],
        inner: tuple[float, float, float, float],
    ) -> bool:
        """Check if outer bbox fully contains inner bbox."""
        return (
            outer[0] <= inner[0]
            and outer[1] <= inner[1]
            and outer[2] >= inner[2]
            and outer[3] >= inner[3]
        )

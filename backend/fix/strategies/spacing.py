"""Min-spacing fix strategy.

Move the less-connected polygon away, OR shrink both polygons by deficit/2.
Prefers move (configurable via PDK fix_weights.prefer_move).
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


class MinSpacingFix(FixStrategy):
    """Fix min-spacing violations by moving polygons apart or shrinking them."""

    @property
    def rule_type(self) -> str:
        return "min_spacing"

    @property
    def name(self) -> str:
        return "Minimum Spacing Fix"

    def can_fix(self, violation: Violation) -> bool:
        return violation.rule_type == "min_spacing"

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
        min_spacing = violation.value_um
        if min_spacing is None:
            return None

        grid = pdk.grid_um

        # Determine spacing direction from edge pair
        # Edge1 and edge2 are on different polygons, facing each other
        vbox = ep.bbox
        w = vbox[2] - vbox[0]
        h = vbox[3] - vbox[1]

        # The gap is the smaller dimension of the edge pair bbox
        is_horizontal_gap = w < h  # gap in X direction
        current_gap = w if is_horizontal_gap else h
        deficit = min_spacing - current_gap

        if deficit <= 0:
            return None

        # Find the two polygons involved
        poly1, poly2 = self._find_two_polygons(ep, spatial_index)
        if poly1 is None or poly2 is None:
            return None

        # Check PDK preference
        prefer_move = True
        fw = pdk.fix_weights.get("min_spacing")
        if fw is not None:
            prefer_move = fw.prefer_move

        if prefer_move:
            return self._suggest_move_fix(
                violation, poly1, poly2, deficit, is_horizontal_gap, grid, pdk,
                spatial_index,
            )
        else:
            return self._suggest_shrink_fix(
                violation, poly1, poly2, deficit, is_horizontal_gap, grid, pdk
            )

    def _find_two_polygons(self, ep, spatial_index):
        """Find the two polygons involved in a spacing violation."""
        # Edge 1 midpoint
        mid1 = (
            (ep.edge1_start[0] + ep.edge1_end[0]) / 2,
            (ep.edge1_start[1] + ep.edge1_end[1]) / 2,
        )
        # Edge 2 midpoint
        mid2 = (
            (ep.edge2_start[0] + ep.edge2_end[0]) / 2,
            (ep.edge2_start[1] + ep.edge2_end[1]) / 2,
        )

        candidates1 = spatial_index.query_point(mid1[0], mid1[1])
        candidates2 = spatial_index.query_point(mid2[0], mid2[1])

        poly1 = candidates1[0] if candidates1 else None
        poly2 = candidates2[0] if candidates2 else None

        # Make sure they're different polygons
        if poly1 is not None and poly2 is not None and poly1.index_id == poly2.index_id:
            # Same polygon found for both edges — try broader search
            nearby = spatial_index.query_nearby(ep.bbox, margin=0.5)
            if len(nearby) >= 2:
                poly1 = nearby[0]
                poly2 = nearby[1]
            else:
                return None, None

        return poly1, poly2

    def _suggest_move_fix(self, violation, poly1, poly2, deficit, is_horizontal_gap, grid, pdk, spatial_index):
        """Move the smaller polygon away by the full deficit."""
        # Move the polygon with smaller area (less connected, easier to move)
        from backend.core.geometry_utils import polygon_area

        area1 = polygon_area(poly1.polygon.points)
        area2 = polygon_area(poly2.polygon.points)

        if area1 <= area2:
            to_move, stationary = poly1, poly2
            _ = -1  # poly1 moves away from poly2
        else:
            to_move, stationary = poly2, poly1
            _ = 1  # poly2 moves away from poly1

        # Determine which direction to move
        move_bbox = polygon_bbox(to_move.polygon.points)
        stay_bbox = polygon_bbox(stationary.polygon.points)

        move_amount = snap_to_grid(deficit, grid)

        if is_horizontal_gap:
            # Determine if to_move is left or right of stationary
            if move_bbox[2] <= stay_bbox[0]:
                # to_move is to the left — move it further left
                dx = -move_amount
            else:
                # to_move is to the right — move it further right
                dx = move_amount
            dy = 0.0
        else:
            if move_bbox[3] <= stay_bbox[1]:
                dy = -move_amount
            else:
                dy = move_amount
            dx = 0.0

        new_points = [
            (snap_to_grid(x + dx, grid), snap_to_grid(y + dy, grid))
            for x, y in to_move.polygon.points
        ]

        delta = PolygonDelta(
            cell_name=to_move.polygon.cell_name,
            gds_layer=to_move.polygon.gds_layer,
            gds_datatype=to_move.polygon.gds_datatype,
            original_points=to_move.polygon.points,
            modified_points=new_points,
        )

        confidence = self._assess_move_confidence(
            to_move, stationary, new_points, move_amount, violation, spatial_index
        )

        return FixSuggestion(
            violation_category=violation.category,
            rule_type=self.rule_type,
            description=(
                f"Move polygon by {move_amount:.3f}um to meet "
                f"min spacing {violation.value_um:.3f}um"
            ),
            deltas=[delta],
            confidence=confidence,
            priority=violation.severity,
        )

    def _assess_move_confidence(
        self, to_move, stationary, new_points, move_amount, violation, spatial_index
    ) -> FixConfidence:
        """Promote to high confidence when the move is small, single-layer, no collision.

        Criteria for high confidence:
        1. Small move: deficit <= rule value (move is at most the min spacing distance)
        2. No collision: moved polygon doesn't overlap or crowd other same-layer polygons
        """
        min_spacing = violation.value_um
        if min_spacing is None:
            return FixConfidence.medium

        # 1. Small move check: deficit should not exceed the rule value
        if move_amount > min_spacing:
            return FixConfidence.medium

        # 2. Collision check: query for same-layer polygons near the moved position
        new_bbox = polygon_bbox(new_points)
        # Expand search by min_spacing to catch spacing violations the move might create
        nearby = spatial_index.query_nearby(
            new_bbox,
            margin=min_spacing,
            layer=to_move.polygon.gds_layer,
            datatype=to_move.polygon.gds_datatype,
        )

        for neighbor in nearby:
            # Skip the polygon being moved and the stationary one (already accounted for)
            if neighbor.index_id == to_move.index_id:
                continue
            if neighbor.index_id == stationary.index_id:
                continue
            # Another same-layer polygon is within min_spacing of the new position
            return FixConfidence.medium

        return FixConfidence.high

    def _suggest_shrink_fix(self, violation, poly1, poly2, deficit, is_horizontal_gap, grid, pdk):
        """Shrink both polygons by deficit/2 each."""
        half = snap_to_grid(deficit / 2, grid)
        # Ensure we cover the full deficit even after grid snapping
        if half * 2 < deficit:
            half = snap_to_grid(half + grid, grid)

        deltas = []
        for poly, is_first in [(poly1, True), (poly2, False)]:
            original = poly.polygon.points
            bbox = polygon_bbox(original)

            if is_horizontal_gap:
                # Shrink the facing edge inward
                if is_first:
                    # poly1 is on the left — shrink its right edge
                    new_points = self._shrink_edge(original, bbox, "right", half, grid)
                else:
                    # poly2 is on the right — shrink its left edge
                    new_points = self._shrink_edge(original, bbox, "left", half, grid)
            else:
                if is_first:
                    new_points = self._shrink_edge(original, bbox, "top", half, grid)
                else:
                    new_points = self._shrink_edge(original, bbox, "bottom", half, grid)

            deltas.append(
                PolygonDelta(
                    cell_name=poly.polygon.cell_name,
                    gds_layer=poly.polygon.gds_layer,
                    gds_datatype=poly.polygon.gds_datatype,
                    original_points=original,
                    modified_points=new_points,
                )
            )

        return FixSuggestion(
            violation_category=violation.category,
            rule_type=self.rule_type,
            description=(
                f"Shrink both polygons by {half:.3f}um each to meet "
                f"min spacing {violation.value_um:.3f}um"
            ),
            deltas=deltas,
            confidence=FixConfidence.medium,
            priority=violation.severity,
        )

    def _shrink_edge(self, points, bbox, edge, amount, grid):
        """Shrink a rectilinear polygon by moving one edge inward."""
        new_points = []
        for x, y in points:
            if edge == "right" and abs(x - bbox[2]) < grid / 2:
                new_points.append((snap_to_grid(x - amount, grid), y))
            elif edge == "left" and abs(x - bbox[0]) < grid / 2:
                new_points.append((snap_to_grid(x + amount, grid), y))
            elif edge == "top" and abs(y - bbox[3]) < grid / 2:
                new_points.append((x, snap_to_grid(y - amount, grid)))
            elif edge == "bottom" and abs(y - bbox[1]) < grid / 2:
                new_points.append((x, snap_to_grid(y + amount, grid)))
            else:
                new_points.append((x, y))
        return new_points

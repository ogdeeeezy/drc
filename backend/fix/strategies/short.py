"""Short-circuit fix strategy.

Boolean-subtract the overlap region + spacing buffer from the less-connected polygon.
"""

from __future__ import annotations

from backend.core.geometry_utils import (
    polygon_area,
    polygon_bbox,
    snap_to_grid,
)
from backend.core.spatial_index import SpatialIndex
from backend.core.violation_models import Violation, ViolationGeometry
from backend.fix.fix_models import FixConfidence, FixSuggestion, PolygonDelta
from backend.fix.strategies.base import FixStrategy
from backend.pdk.schema import PDKConfig


class ShortCircuitFix(FixStrategy):
    """Fix short-circuit violations by removing overlap from the smaller polygon.

    For shorts, we shrink the less-connected polygon to eliminate
    the overlap plus a spacing buffer.
    """

    @property
    def rule_type(self) -> str:
        return "short"

    @property
    def name(self) -> str:
        return "Short Circuit Fix"

    def can_fix(self, violation: Violation) -> bool:
        # Shorts may be reported under various category names
        cat = violation.category.lower()
        return "short" in cat or violation.rule_type == "short"

    def suggest_fix(
        self,
        violation: Violation,
        geometry: ViolationGeometry,
        pdk: PDKConfig,
        spatial_index: SpatialIndex,
    ) -> FixSuggestion | None:
        if geometry.edge_pair is None and geometry.points is None:
            return None

        grid = pdk.grid_um
        vbox = geometry.bbox

        # Find the two polygons involved in the short
        nearby = spatial_index.query_bbox(vbox)
        if len(nearby) < 2:
            # Try expanding search
            nearby = spatial_index.query_nearby(vbox, margin=0.5)

        if len(nearby) < 2:
            return None

        # Pick the two polygons with the most overlap to the violation region
        # Sort by overlap with violation bbox
        scored = []
        for ip in nearby:
            pbbox = ip.bbox
            overlap_x = max(0, min(pbbox[2], vbox[2]) - max(pbbox[0], vbox[0]))
            overlap_y = max(0, min(pbbox[3], vbox[3]) - max(pbbox[1], vbox[1]))
            scored.append((overlap_x * overlap_y, ip))
        scored.sort(key=lambda x: x[0], reverse=True)

        poly1 = scored[0][1]
        poly2 = scored[1][1] if len(scored) > 1 else None
        if poly2 is None:
            return None

        # Shrink the smaller polygon (less connected)
        area1 = polygon_area(poly1.polygon.points)
        area2 = polygon_area(poly2.polygon.points)
        to_shrink = poly1 if area1 <= area2 else poly2

        original = to_shrink.polygon.points
        orig_bbox = polygon_bbox(original)

        # Get the min spacing for this layer if available
        spacing_buffer = grid * 2  # default 2 grid points
        for rule in pdk.rules:
            if rule.rule_type.value == "min_spacing" and rule.layer in violation.category:
                spacing_buffer = rule.value_um
                break

        # Determine which side of the polygon overlaps and shrink it
        # Find the overlap direction
        shrink_amount = snap_to_grid(
            max(vbox[2] - vbox[0], vbox[3] - vbox[1]) + spacing_buffer, grid
        )

        # Shrink the facing edge
        w = vbox[2] - vbox[0]
        h = vbox[3] - vbox[1]

        new_points = []
        if w >= h:
            # Overlap is wider than tall → shrink horizontally
            # Which side faces the other polygon?
            other = poly2 if to_shrink == poly1 else poly1
            other_bbox = polygon_bbox(other.polygon.points)
            if orig_bbox[2] > other_bbox[0] and orig_bbox[0] < other_bbox[0]:
                # our right edge overlaps their left → shrink right
                for x, y in original:
                    if abs(x - orig_bbox[2]) < grid / 2:
                        new_points.append((snap_to_grid(x - shrink_amount, grid), y))
                    else:
                        new_points.append((x, y))
            else:
                # our left edge overlaps their right → shrink left
                for x, y in original:
                    if abs(x - orig_bbox[0]) < grid / 2:
                        new_points.append((snap_to_grid(x + shrink_amount, grid), y))
                    else:
                        new_points.append((x, y))
        else:
            other = poly2 if to_shrink == poly1 else poly1
            other_bbox = polygon_bbox(other.polygon.points)
            if orig_bbox[3] > other_bbox[1] and orig_bbox[1] < other_bbox[1]:
                for x, y in original:
                    if abs(y - orig_bbox[3]) < grid / 2:
                        new_points.append((x, snap_to_grid(y - shrink_amount, grid)))
                    else:
                        new_points.append((x, y))
            else:
                for x, y in original:
                    if abs(y - orig_bbox[1]) < grid / 2:
                        new_points.append((x, snap_to_grid(y + shrink_amount, grid)))
                    else:
                        new_points.append((x, y))

        if not new_points or new_points == original:
            return None

        # Check the modified polygon isn't degenerate
        new_bbox = polygon_bbox(new_points)
        if new_bbox[2] - new_bbox[0] < grid or new_bbox[3] - new_bbox[1] < grid:
            return FixSuggestion(
                violation_category=violation.category,
                rule_type="short",
                description="Short fix would create degenerate polygon — manual review needed",
                deltas=[],
                confidence=FixConfidence.low,
                priority=1,  # Shorts are highest priority
            )

        delta = PolygonDelta(
            cell_name=to_shrink.polygon.cell_name,
            gds_layer=to_shrink.polygon.gds_layer,
            gds_datatype=to_shrink.polygon.gds_datatype,
            original_points=original,
            modified_points=new_points,
        )

        return FixSuggestion(
            violation_category=violation.category,
            rule_type="short",
            description=(
                f"Shrink polygon by {shrink_amount:.3f}um to resolve short "
                f"(includes {spacing_buffer:.3f}um spacing buffer)"
            ),
            deltas=[delta],
            confidence=FixConfidence.medium,
            priority=1,  # Shorts are always highest priority
        )

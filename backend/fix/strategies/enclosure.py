"""Enclosure fix strategy.

Extend the enclosing metal outward to meet min enclosure of a via.
Never move the via. Check that expansion doesn't violate spacing rules.
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


class EnclosureFix(FixStrategy):
    """Fix min-enclosure violations by extending the enclosing metal layer."""

    @property
    def rule_type(self) -> str:
        return "min_enclosure"

    @property
    def name(self) -> str:
        return "Minimum Enclosure Fix"

    def can_fix(self, violation: Violation) -> bool:
        return violation.rule_type == "min_enclosure"

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
        min_enclosure = violation.value_um
        if min_enclosure is None:
            return None

        grid = pdk.grid_um

        # For enclosure, the edge pair shows where the metal doesn't
        # extend far enough past the via. The gap between the edges
        # is the current enclosure, and we need it >= min_enclosure.
        vbox = ep.bbox
        w = vbox[2] - vbox[0]
        h = vbox[3] - vbox[1]

        # The deficient dimension
        current_enclosure = min(w, h)
        deficit = min_enclosure - current_enclosure

        if deficit <= 0:
            return None

        # Find the enclosing metal polygon (larger one near the violation)
        nearby = spatial_index.query_nearby(vbox, margin=min_enclosure * 2)
        if not nearby:
            return None

        # The metal polygon is typically the larger one
        # The via is typically smaller (exact_size)
        metal_poly = None
        for ip in nearby:
            pbbox = polygon_bbox(ip.polygon.points)
            pw = pbbox[2] - pbbox[0]
            ph = pbbox[3] - pbbox[1]
            # Metal polygon should be larger than the violation region
            if pw > w or ph > h:
                metal_poly = ip
                break

        if metal_poly is None:
            # Fallback: use the first one
            metal_poly = nearby[0]

        original = metal_poly.polygon.points
        orig_bbox = polygon_bbox(original)

        # Determine which edge(s) of the metal need extending
        # Extend outward on the deficient side(s)
        expand = snap_to_grid(deficit, grid)

        # Check which edges of the metal are close to the violation
        new_points = list(original)

        # Determine if the violation is near the left/right/top/bottom edge
        near_left = abs(vbox[0] - orig_bbox[0]) < min_enclosure * 1.5
        near_right = abs(vbox[2] - orig_bbox[2]) < min_enclosure * 1.5
        near_bottom = abs(vbox[1] - orig_bbox[1]) < min_enclosure * 1.5
        near_top = abs(vbox[3] - orig_bbox[3]) < min_enclosure * 1.5

        modified = False
        result_points = []
        for x, y in original:
            nx, ny = x, y
            if near_left and abs(x - orig_bbox[0]) < grid / 2:
                nx = snap_to_grid(x - expand, grid)
                modified = True
            elif near_right and abs(x - orig_bbox[2]) < grid / 2:
                nx = snap_to_grid(x + expand, grid)
                modified = True
            if near_bottom and abs(y - orig_bbox[1]) < grid / 2:
                ny = snap_to_grid(y - expand, grid)
                modified = True
            elif near_top and abs(y - orig_bbox[3]) < grid / 2:
                ny = snap_to_grid(y + expand, grid)
                modified = True
            result_points.append((nx, ny))

        if not modified:
            return None

        delta = PolygonDelta(
            cell_name=metal_poly.polygon.cell_name,
            gds_layer=metal_poly.polygon.gds_layer,
            gds_datatype=metal_poly.polygon.gds_datatype,
            original_points=original,
            modified_points=result_points,
        )

        return FixSuggestion(
            violation_category=violation.category,
            rule_type=self.rule_type,
            description=(
                f"Extend metal by {expand:.3f}um to meet "
                f"min enclosure {min_enclosure:.3f}um"
            ),
            deltas=[delta],
            confidence=FixConfidence.medium,
            priority=violation.severity,
        )

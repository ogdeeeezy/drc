"""Fix pre-validator — checks proposed fixes locally before suggesting them.

Validates that:
1. All coordinates are on the manufacturing grid
2. Modified polygons aren't degenerate (zero area, self-intersecting)
3. Width of modified polygon meets min_width for its layer
4. Spacing between modified polygon and neighbors meets min_spacing
"""

from __future__ import annotations

from backend.core.geometry_utils import (
    bbox_height,
    bbox_width,
    is_on_grid,
    min_edge_width,
    polygon_area,
    polygon_bbox,
    snap_to_grid,
)
from backend.core.spatial_index import SpatialIndex
from backend.fix.fix_models import FixConfidence, FixSuggestion, PolygonDelta
from backend.pdk.schema import PDKConfig


class FixValidator:
    """Pre-validates fix suggestions using local geometry checks.

    This is a fast, approximate validator — it doesn't run full DRC.
    It catches obvious problems like degenerate polygons, off-grid
    coordinates, and basic width/spacing violations.
    """

    def __init__(self, pdk: PDKConfig, spatial_index: SpatialIndex):
        self._pdk = pdk
        self._spatial_index = spatial_index

    def validate(self, suggestion: FixSuggestion) -> FixSuggestion:
        """Validate a fix suggestion and update its confidence/notes.

        Returns the same suggestion with updated validation fields.
        """
        issues: list[str] = []

        for delta in suggestion.deltas:
            issues.extend(self._validate_delta(delta))

        if issues:
            suggestion.creates_new_violations = True
            suggestion.validation_notes = "; ".join(issues)
            suggestion.confidence = FixConfidence.low
        else:
            suggestion.creates_new_violations = False
            suggestion.validation_notes = "Pre-validation passed"
            if suggestion.confidence == FixConfidence.medium:
                suggestion.confidence = FixConfidence.high

        return suggestion

    def _validate_delta(self, delta: PolygonDelta) -> list[str]:
        """Validate a single polygon delta. Returns list of issues."""
        issues = []

        if delta.is_removal:
            return issues  # Removal is always valid

        points = delta.modified_points

        # 1. Grid alignment
        grid = self._pdk.grid_um
        for i, (x, y) in enumerate(points):
            if not is_on_grid(x, grid):
                issues.append(f"Vertex {i} x={x} off-grid (grid={grid})")
            if not is_on_grid(y, grid):
                issues.append(f"Vertex {i} y={y} off-grid (grid={grid})")

        # 2. Degenerate polygon check
        if len(points) < 3:
            issues.append("Polygon has fewer than 3 vertices")
            return issues

        area = polygon_area(points)
        if area < 1e-12:
            issues.append("Polygon has zero area")
            return issues

        bbox = polygon_bbox(points)
        w = bbox_width(bbox)
        h = bbox_height(bbox)

        if w < grid or h < grid:
            issues.append(f"Polygon smaller than grid ({w:.4f} x {h:.4f}um)")

        # 3. Min width check for this layer
        layer_name = self._find_layer_name(delta.gds_layer, delta.gds_datatype)
        if layer_name:
            for rule in self._pdk.get_rules_for_layer(layer_name):
                if rule.rule_type.value == "min_width":
                    edge_width = min_edge_width(points)
                    if edge_width < rule.value_um - grid / 2:
                        issues.append(
                            f"Width {edge_width:.4f}um < min {rule.value_um:.4f}um "
                            f"({rule.rule_id})"
                        )

                if rule.rule_type.value == "min_area":
                    if area < rule.value_um - 1e-9:
                        issues.append(
                            f"Area {area:.6f}um² < min {rule.value_um:.6f}um² "
                            f"({rule.rule_id})"
                        )

        # 4. Min spacing check against neighbors
        if layer_name:
            spacing_issues = self._check_spacing(
                points, bbox, delta.gds_layer, delta.gds_datatype, layer_name
            )
            issues.extend(spacing_issues)

        return issues

    def _check_spacing(
        self,
        points: list[tuple[float, float]],
        bbox: tuple[float, float, float, float],
        gds_layer: int,
        gds_datatype: int,
        layer_name: str,
    ) -> list[str]:
        """Check if modified polygon violates spacing with neighbors."""
        issues = []

        # Find min_spacing rule for this layer
        min_spacing = None
        spacing_rule_id = None
        for rule in self._pdk.get_rules_for_layer(layer_name):
            if rule.rule_type.value == "min_spacing" and rule.layer == layer_name:
                min_spacing = rule.value_um
                spacing_rule_id = rule.rule_id
                break

        if min_spacing is None:
            return issues

        # Query nearby polygons on the same layer
        neighbors = self._spatial_index.query_nearby(
            bbox, margin=min_spacing, layer=gds_layer, datatype=gds_datatype
        )

        for neighbor in neighbors:
            # Skip if same polygon (comparing bbox as proxy)
            n_bbox = neighbor.bbox
            if n_bbox == bbox:
                continue

            # Compute approximate gap between bboxes
            gap_x = max(0, max(n_bbox[0] - bbox[2], bbox[0] - n_bbox[2]))
            gap_y = max(0, max(n_bbox[1] - bbox[3], bbox[1] - n_bbox[3]))
            gap = max(gap_x, gap_y) if gap_x > 0 or gap_y > 0 else 0

            if gap < min_spacing - self._pdk.grid_um / 2:
                issues.append(
                    f"Spacing {gap:.4f}um to neighbor < min {min_spacing:.4f}um "
                    f"({spacing_rule_id})"
                )

        return issues

    def _find_layer_name(self, gds_layer: int, gds_datatype: int) -> str | None:
        """Find PDK layer name for a GDS layer/datatype pair."""
        for name, layer in self._pdk.layers.items():
            if layer.gds_layer == gds_layer and layer.gds_datatype == gds_datatype:
                return name
        return None

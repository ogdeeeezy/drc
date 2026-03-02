"""Density fill fix strategy — adds fill polygons to meet minimum density requirements.

Metal density rules require a minimum fill percentage within a check window.
This strategy generates grid-aligned fill rectangles in empty regions,
respecting spacing rules from the PDK.
"""

from __future__ import annotations

from backend.core.spatial_index import SpatialIndex
from backend.core.violation_models import Violation, ViolationGeometry
from backend.fix.fix_models import FixConfidence, FixSuggestion, PolygonDelta
from backend.fix.strategies.base import FixStrategy
from backend.pdk.schema import PDKConfig

# Default fill parameters (overridden by PDK rules when available)
_DEFAULT_FILL_WIDTH_UM = 1.0
_DEFAULT_FILL_SPACING_UM = 0.5
_DEFAULT_TARGET_DENSITY = 0.25  # 25%


class DensityFillFix(FixStrategy):
    """Fix minimum density violations by adding fill polygons in empty regions.

    Fill polygons are placed in a grid pattern within the violation region,
    respecting spacing rules and grid alignment. Stops once the target
    density is reached.
    """

    @property
    def rule_type(self) -> str:
        return "min_density"

    @property
    def name(self) -> str:
        return "DensityFillFix"

    def can_fix(self, violation: Violation) -> bool:
        return (
            violation.rule_type == "min_density"
            or "density" in (violation.description or "").lower()
        )

    def suggest_fix(
        self,
        violation: Violation,
        geometry: ViolationGeometry,
        pdk: PDKConfig,
        spatial_index: SpatialIndex,
    ) -> FixSuggestion | None:
        bbox = geometry.bbox
        region_width = bbox[2] - bbox[0]
        region_height = bbox[3] - bbox[1]
        region_area = region_width * region_height

        if region_area <= 0:
            return None

        # Resolve layer info from violation category
        gds_layer, gds_datatype, min_spacing, fill_width = self._resolve_layer_params(
            violation, pdk
        )

        grid = pdk.grid_um
        fill_width = _snap(fill_width, grid)
        min_spacing = _snap(max(min_spacing, grid), grid)
        pitch = fill_width + min_spacing

        if pitch <= 0 or fill_width <= 0:
            return None

        # Measure existing density in the violation region
        existing = spatial_index.query_bbox(bbox, layer=gds_layer, datatype=gds_datatype)
        existing_area = sum(_overlap_area(ip.bbox, bbox) for ip in existing)
        current_density = existing_area / region_area

        target = _DEFAULT_TARGET_DENSITY
        if current_density >= target:
            return None

        deficit_area = (target - current_density) * region_area

        # Generate fill grid
        deltas: list[PolygonDelta] = []
        fill_area_total = 0.0
        cell_name = violation.cell_name

        x = _snap(bbox[0] + min_spacing, grid)
        while x + fill_width <= bbox[2] - min_spacing:
            y = _snap(bbox[1] + min_spacing, grid)
            while y + fill_width <= bbox[3] - min_spacing:
                fill_box = (x, y, x + fill_width, y + fill_width)

                # Check no overlap with existing polygons (with spacing margin)
                nearby = spatial_index.query_nearby(
                    fill_box, margin=min_spacing, layer=gds_layer, datatype=gds_datatype
                )
                if not nearby:
                    points = [
                        (x, y),
                        (x + fill_width, y),
                        (x + fill_width, y + fill_width),
                        (x, y + fill_width),
                    ]
                    deltas.append(
                        PolygonDelta(
                            cell_name=cell_name,
                            gds_layer=gds_layer,
                            gds_datatype=gds_datatype,
                            original_points=[],
                            modified_points=points,
                        )
                    )
                    fill_area_total += fill_width * fill_width
                    if fill_area_total >= deficit_area:
                        break

                y = _snap(y + pitch, grid)

            if fill_area_total >= deficit_area:
                break
            x = _snap(x + pitch, grid)

        if not deltas:
            return None

        new_density = (existing_area + fill_area_total) / region_area
        return FixSuggestion(
            violation_category=violation.category,
            rule_type="min_density",
            description=(
                f"Add {len(deltas)} fill polygons ({fill_width:.3f}um squares) "
                f"to increase density from {current_density:.1%} to {new_density:.1%}"
            ),
            deltas=deltas,
            confidence=FixConfidence.medium,
            priority=7,
        )

    def _resolve_layer_params(
        self, violation: Violation, pdk: PDKConfig
    ) -> tuple[int, int, float, float]:
        """Extract GDS layer, spacing, and fill width from PDK rules."""
        gds_layer = 0
        gds_datatype = 0
        min_spacing = _DEFAULT_FILL_SPACING_UM
        fill_width = _DEFAULT_FILL_WIDTH_UM

        # Try to find the layer from the category prefix (e.g. "met1.density")
        layer_name = violation.category.split(".")[0] if "." in violation.category else None
        if layer_name and layer_name in pdk.layers:
            info = pdk.layers[layer_name]
            gds_layer = info.gds_layer
            gds_datatype = info.gds_datatype

            for rule in pdk.rules:
                if rule.layer == layer_name:
                    if rule.rule_type.value == "min_spacing":
                        min_spacing = rule.value_um
                    elif rule.rule_type.value == "min_width":
                        fill_width = max(fill_width, rule.value_um)

        return gds_layer, gds_datatype, min_spacing, fill_width


def _snap(value: float, grid: float) -> float:
    """Snap a value to the nearest grid point."""
    return round(value / grid) * grid


def _overlap_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Approximate overlap area between two bounding boxes."""
    x_overlap = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    y_overlap = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return x_overlap * y_overlap

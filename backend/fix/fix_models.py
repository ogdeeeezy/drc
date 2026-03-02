"""Fix suggestion data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FixConfidence(str, Enum):
    """How confident we are the fix resolves the violation without side effects."""

    high = "high"  # Pre-validated, no conflicts detected
    medium = "medium"  # Likely works, minor uncertainty
    low = "low"  # May introduce new violations


@dataclass
class PolygonDelta:
    """Describes a modification to a single polygon.

    The fix engine uses these to build up a complete fix from individual changes.
    """

    cell_name: str
    gds_layer: int
    gds_datatype: int
    original_points: list[tuple[float, float]]
    modified_points: list[tuple[float, float]]

    @property
    def is_removal(self) -> bool:
        """True if the fix removes this polygon entirely."""
        return len(self.modified_points) == 0

    @property
    def is_addition(self) -> bool:
        """True if the fix adds a new polygon (original was empty)."""
        return len(self.original_points) == 0


@dataclass
class FixSuggestion:
    """A suggested fix for one or more DRC violations.

    Each suggestion contains the deltas needed to apply the fix,
    along with metadata about what it fixes and how confident we are.
    """

    violation_category: str  # e.g. "m1.1"
    rule_type: str  # e.g. "min_width"
    description: str  # Human-readable explanation
    deltas: list[PolygonDelta] = field(default_factory=list)
    confidence: FixConfidence = FixConfidence.medium
    priority: int = 5  # 1 = highest, from PDK fix_weights

    # Set during validation
    creates_new_violations: bool = False
    validation_notes: str = ""

    @property
    def delta_count(self) -> int:
        return len(self.deltas)

    @property
    def affected_layers(self) -> set[tuple[int, int]]:
        return {(d.gds_layer, d.gds_datatype) for d in self.deltas}

"""Violation data models — the structured output of DRC checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GeometryType(str, Enum):
    edge_pair = "edge_pair"
    polygon = "polygon"
    edge = "edge"
    box = "box"


@dataclass(frozen=True)
class EdgePair:
    """Two edges that violate a rule (e.g. too close, too narrow).

    Each edge is defined by start and end points in microns.
    """

    edge1_start: tuple[float, float]
    edge1_end: tuple[float, float]
    edge2_start: tuple[float, float]
    edge2_end: tuple[float, float]

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """Bounding box (xmin, ymin, xmax, ymax) enclosing both edges."""
        xs = [self.edge1_start[0], self.edge1_end[0], self.edge2_start[0], self.edge2_end[0]]
        ys = [self.edge1_start[1], self.edge1_end[1], self.edge2_start[1], self.edge2_end[1]]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def midpoint(self) -> tuple[float, float]:
        """Center point between the two edges."""
        b = self.bbox
        return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


@dataclass(frozen=True)
class ViolationGeometry:
    """Geometry of a single violation marker."""

    geometry_type: GeometryType
    # For edge_pair: edge_pair is set
    # For polygon: points is set
    # For edge: edge1 start/end in edge_pair (edge2 unused)
    # For box: points has 4 corners
    edge_pair: EdgePair | None = None
    points: list[tuple[float, float]] | None = None

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        if self.edge_pair is not None:
            return self.edge_pair.bbox
        if self.points:
            xs = [p[0] for p in self.points]
            ys = [p[1] for p in self.points]
            return (min(xs), min(ys), max(xs), max(ys))
        return (0.0, 0.0, 0.0, 0.0)


@dataclass
class Violation:
    """A single DRC violation with its geometry and rule context."""

    category: str  # Rule name from .lyrdb (e.g. "met1.1")
    description: str  # Human-readable description from category
    cell_name: str
    geometries: list[ViolationGeometry] = field(default_factory=list)

    # Populated by mapping to PDK rules
    rule_id: str | None = None
    rule_type: str | None = None  # RuleType value string
    severity: int = 5
    value_um: float | None = None  # Rule threshold from PDK

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """Combined bounding box of all geometries."""
        if not self.geometries:
            return (0.0, 0.0, 0.0, 0.0)
        bboxes = [g.bbox for g in self.geometries]
        return (
            min(b[0] for b in bboxes),
            min(b[1] for b in bboxes),
            max(b[2] for b in bboxes),
            max(b[3] for b in bboxes),
        )

    @property
    def violation_count(self) -> int:
        """Number of individual violation markers."""
        return len(self.geometries)


@dataclass
class DRCReport:
    """Complete DRC report parsed from a .lyrdb file."""

    description: str
    original_file: str
    generator: str
    top_cell: str
    violations: list[Violation] = field(default_factory=list)

    @property
    def total_violations(self) -> int:
        return sum(v.violation_count for v in self.violations)

    @property
    def categories(self) -> list[str]:
        return [v.category for v in self.violations]

    def get_violations_by_category(self, category: str) -> Violation | None:
        for v in self.violations:
            if v.category == category:
                return v
        return None

    def get_violations_for_cell(self, cell_name: str) -> list[Violation]:
        return [v for v in self.violations if v.cell_name == cell_name]

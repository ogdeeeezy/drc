"""Abstract base class for fix strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.core.spatial_index import SpatialIndex
from backend.core.violation_models import Violation, ViolationGeometry
from backend.fix.fix_models import FixSuggestion
from backend.pdk.schema import PDKConfig


class FixStrategy(ABC):
    """Base class for all DRC fix strategies.

    Each strategy handles one type of violation (min_width, min_spacing, etc.)
    and produces FixSuggestions with concrete polygon deltas.
    """

    @property
    @abstractmethod
    def rule_type(self) -> str:
        """The RuleType this strategy handles (e.g. 'min_width')."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name."""

    @abstractmethod
    def can_fix(self, violation: Violation) -> bool:
        """Check if this strategy can handle the given violation."""

    @abstractmethod
    def suggest_fix(
        self,
        violation: Violation,
        geometry: ViolationGeometry,
        pdk: PDKConfig,
        spatial_index: SpatialIndex,
    ) -> FixSuggestion | None:
        """Generate a fix suggestion for a single violation geometry.

        Args:
            violation: The violation to fix (has rule metadata if PDK-mapped).
            geometry: The specific geometry marker to address.
            pdk: PDK configuration for grid, rule thresholds, etc.
            spatial_index: Spatial index for finding nearby polygons.

        Returns:
            A FixSuggestion with polygon deltas, or None if no fix can be computed.
        """

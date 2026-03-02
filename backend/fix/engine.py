"""Fix engine — orchestrates fix strategies, ranks suggestions, and validates results.

Priority order: shorts > off-grid > width > spacing > enclosure > area
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.spatial_index import SpatialIndex
from backend.core.violation_models import DRCReport, Violation
from backend.fix.clustering import ViolationCluster, cluster_violations
from backend.fix.fix_models import FixSuggestion
from backend.fix.strategies.area import MinAreaFix
from backend.fix.strategies.base import FixStrategy
from backend.fix.strategies.enclosure import EnclosureFix
from backend.fix.strategies.offgrid import OffGridFix
from backend.fix.strategies.short import ShortCircuitFix
from backend.fix.strategies.spacing import MinSpacingFix
from backend.fix.strategies.width import MinWidthFix
from backend.fix.validator import FixValidator
from backend.pdk.schema import PDKConfig


# Default priority order (1 = highest)
DEFAULT_PRIORITY = {
    "short": 1,
    "off_grid": 2,
    "min_width": 3,
    "min_spacing": 4,
    "min_enclosure": 5,
    "min_area": 6,
}


@dataclass
class FixEngineResult:
    """Result of running the fix engine on a DRC report."""

    suggestions: list[FixSuggestion] = field(default_factory=list)
    clusters: list[ViolationCluster] = field(default_factory=list)
    unfixable: list[Violation] = field(default_factory=list)

    @property
    def total_suggestions(self) -> int:
        return len(self.suggestions)

    @property
    def fixable_count(self) -> int:
        return sum(1 for s in self.suggestions if not s.creates_new_violations)

    @property
    def by_rule_type(self) -> dict[str, list[FixSuggestion]]:
        result: dict[str, list[FixSuggestion]] = {}
        for s in self.suggestions:
            result.setdefault(s.rule_type, []).append(s)
        return result


class FixEngine:
    """Orchestrates fix strategies to generate ranked suggestions for DRC violations.

    Usage:
        engine = FixEngine(pdk, spatial_index)
        result = engine.suggest_fixes(drc_report)
        for suggestion in result.suggestions:
            print(f"{suggestion.description} (confidence: {suggestion.confidence})")
    """

    def __init__(
        self,
        pdk: PDKConfig,
        spatial_index: SpatialIndex,
        strategies: list[FixStrategy] | None = None,
    ):
        self._pdk = pdk
        self._spatial_index = spatial_index
        self._validator = FixValidator(pdk, spatial_index)
        self._strategies = strategies or self._default_strategies()

    def _default_strategies(self) -> list[FixStrategy]:
        return [
            ShortCircuitFix(),
            OffGridFix(),
            MinWidthFix(),
            MinSpacingFix(),
            EnclosureFix(),
            MinAreaFix(),
        ]

    def suggest_fixes(
        self,
        report: DRCReport,
        cluster_proximity_um: float = 1.0,
        validate: bool = True,
    ) -> FixEngineResult:
        """Generate fix suggestions for all violations in a DRC report.

        Args:
            report: DRC report with violations (should be PDK-mapped).
            cluster_proximity_um: Clustering distance for related violations.
            validate: Whether to pre-validate suggestions.

        Returns:
            FixEngineResult with ranked suggestions.
        """
        result = FixEngineResult()

        # Cluster violations for context
        result.clusters = cluster_violations(
            report.violations, proximity_um=cluster_proximity_um
        )

        # Process each violation
        for violation in report.violations:
            suggestions = self._suggest_for_violation(violation)
            if suggestions:
                result.suggestions.extend(suggestions)
            else:
                result.unfixable.append(violation)

        # Validate if requested
        if validate:
            for suggestion in result.suggestions:
                self._validator.validate(suggestion)

        # Sort by priority (lower = higher priority), then confidence
        confidence_order = {"high": 0, "medium": 1, "low": 2}
        result.suggestions.sort(
            key=lambda s: (
                s.priority,
                confidence_order.get(s.confidence.value, 9),
            )
        )

        return result

    def suggest_for_violation(self, violation: Violation) -> list[FixSuggestion]:
        """Generate and validate fix suggestions for a single violation."""
        suggestions = self._suggest_for_violation(violation)
        for s in suggestions:
            self._validator.validate(s)
        return suggestions

    def _suggest_for_violation(self, violation: Violation) -> list[FixSuggestion]:
        """Try each strategy on a violation, return all suggestions."""
        suggestions = []

        for strategy in self._strategies:
            if not strategy.can_fix(violation):
                continue

            for geometry in violation.geometries:
                suggestion = strategy.suggest_fix(
                    violation, geometry, self._pdk, self._spatial_index
                )
                if suggestion is not None:
                    # Apply PDK fix weight priority if available
                    fw = self._pdk.fix_weights.get(strategy.rule_type)
                    if fw is not None:
                        suggestion.priority = fw.priority
                        if not fw.enabled:
                            continue
                    elif strategy.rule_type in DEFAULT_PRIORITY:
                        suggestion.priority = DEFAULT_PRIORITY[strategy.rule_type]
                    suggestions.append(suggestion)

        return suggestions

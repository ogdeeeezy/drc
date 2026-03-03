"""Auto-fix runner — loops suggest→filter→apply→re-DRC until clean or stalled."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from backend.core.drc_runner import DRCError, DRCRunner
from backend.core.layout import LayoutManager
from backend.core.spatial_index import SpatialIndex
from backend.core.violation_parser import ViolationParser
from backend.export.gdsii import export_fixed_gds
from backend.fix.engine import FixEngine
from backend.fix.fix_models import FixConfidence, FixSuggestion
from backend.jobs.manager import Job, JobManager, JobStatus
from backend.pdk.schema import PDKConfig

logger = logging.getLogger(__name__)


@dataclass
class IterationRecord:
    """Tracks one iteration of the auto-fix loop."""

    iteration: int
    total_violations: int
    applied_count: int
    flagged_count: int


@dataclass
class AutoFixResult:
    """Result of a full auto-fix run."""

    iterations_run: int = 0
    final_violation_count: int = 0
    fixes_applied_count: int = 0
    fixes_flagged_count: int = 0
    stop_reason: str = ""
    iteration_history: list[IterationRecord] = field(default_factory=list)


def _is_auto_applicable(
    suggestion: FixSuggestion,
    confidence_threshold: str,
) -> bool:
    """Determine if a fix suggestion qualifies for automatic application.

    Rules:
    - Low confidence → always flag
    - is_removal → always flag
    - creates_new_violations → always flag
    - Multi-layer (affects >1 layer) → always flag
    - Medium confidence → auto-apply only if threshold='medium'
    - High confidence + single-layer + no new violations → auto-apply
    """
    # Always flag: removal, creates new violations, low confidence
    if suggestion.confidence == FixConfidence.low:
        return False
    for delta in suggestion.deltas:
        if delta.is_removal:
            return False
    if suggestion.creates_new_violations:
        return False
    # Multi-layer: flag
    if len(suggestion.affected_layers) > 1:
        return False
    # Medium confidence: only if threshold allows
    if suggestion.confidence == FixConfidence.medium:
        return confidence_threshold == "medium"
    # High confidence: auto-apply
    return True


def _flag_reason(suggestion: FixSuggestion, confidence_threshold: str) -> str:
    """Return the reason a fix was flagged (not auto-applied)."""
    if suggestion.confidence == FixConfidence.low:
        return "low_confidence"
    for delta in suggestion.deltas:
        if delta.is_removal:
            return "deletion_fix"
    if suggestion.creates_new_violations:
        return "creates_new_violations"
    if len(suggestion.affected_layers) > 1:
        return "multi_layer"
    if suggestion.confidence == FixConfidence.medium and confidence_threshold == "high":
        return "medium_confidence_in_high_mode"
    return "circuit_intent_unknown"


def _apply_deltas_from_suggestions(
    layout_mgr: LayoutManager,
    suggestions: list[FixSuggestion],
) -> int:
    """Apply polygon deltas from selected suggestions. Returns count of applied deltas."""
    applied = 0
    for suggestion in suggestions:
        for delta in suggestion.deltas:
            try:
                cell = layout_mgr.get_cell(delta.cell_name)
                matched = False
                for i, poly in enumerate(cell.polygons):
                    if poly.layer == delta.gds_layer and poly.datatype == delta.gds_datatype:
                        poly_pts = [(float(p[0]), float(p[1])) for p in poly.points]
                        if _points_match(poly_pts, delta.original_points):
                            if delta.is_removal:
                                layout_mgr.remove_polygon(delta.cell_name, i)
                            else:
                                layout_mgr.replace_polygon(
                                    delta.cell_name, i, delta.modified_points
                                )
                            applied += 1
                            matched = True
                            break
                if not matched and delta.is_addition:
                    layout_mgr.add_polygon(
                        delta.cell_name,
                        delta.modified_points,
                        delta.gds_layer,
                        delta.gds_datatype,
                    )
                    applied += 1
            except (KeyError, IndexError):
                continue
    return applied


def _points_match(
    a: list[tuple[float, float]],
    b: list[tuple[float, float]],
    tolerance: float = 1e-6,
) -> bool:
    """Check if two point lists match within tolerance."""
    if len(a) != len(b):
        return False
    return all(
        abs(p1[0] - p2[0]) < tolerance and abs(p1[1] - p2[1]) < tolerance
        for p1, p2 in zip(a, b)
    )


class AutoFixRunner:
    """Orchestrates the auto-fix loop: suggest → filter → apply → re-DRC → repeat.

    Usage:
        runner = AutoFixRunner(manager, pdk, job)
        result = await runner.run(confidence_threshold="high", max_iterations=10)
    """

    def __init__(
        self,
        manager: JobManager,
        pdk: PDKConfig,
        job: Job,
    ):
        self._manager = manager
        self._pdk = pdk
        self._job = job

    async def run(
        self,
        confidence_threshold: str = "high",
        max_iterations: int = 10,
    ) -> AutoFixResult:
        """Execute the auto-fix loop.

        Args:
            confidence_threshold: 'high' or 'medium'. Controls which fixes are auto-applied.
            max_iterations: Hard cap on loop iterations.

        Returns:
            AutoFixResult with loop outcome and history.
        """
        result = AutoFixResult()
        job = self._job
        job_dir = self._manager.job_dir(job.job_id)
        original_stem = Path(job.filename).stem
        parser = ViolationParser()

        # Get initial violation count from current report
        current_gds_path = Path(job.gds_path) if job.gds_path else None
        current_violations = job.total_violations

        if current_gds_path is None or not current_gds_path.exists():
            result.stop_reason = "no_gds_file"
            return result

        report_path = Path(job.report_path) if job.report_path else None
        if report_path is None or not report_path.exists():
            result.stop_reason = "no_drc_report"
            return result

        for iteration_num in range(1, max_iterations + 1):
            logger.info(
                "Auto-fix iteration %d: %d violations, gds=%s",
                iteration_num,
                current_violations,
                current_gds_path,
            )

            # If already clean, stop
            if current_violations == 0:
                result.stop_reason = "drc_clean"
                break

            # Step 1: Parse current report and suggest fixes
            report = parser.parse_file(report_path)
            parser.map_to_pdk(report, self._pdk)

            layout_mgr = LayoutManager()
            layout_mgr.load(current_gds_path)
            polygons = layout_mgr.get_flattened_polygons()
            spatial_index = SpatialIndex.from_polygons(polygons)

            engine = FixEngine(self._pdk, spatial_index)
            fix_result = engine.suggest_fixes(report)

            if fix_result.total_suggestions == 0:
                result.stop_reason = "no_suggestions"
                result.iteration_history.append(
                    IterationRecord(
                        iteration=iteration_num,
                        total_violations=current_violations,
                        applied_count=0,
                        flagged_count=0,
                    )
                )
                break

            # Step 2: Filter by confidence
            auto_apply: list[FixSuggestion] = []
            flagged: list[FixSuggestion] = []

            for suggestion in fix_result.suggestions:
                if _is_auto_applicable(suggestion, confidence_threshold):
                    auto_apply.append(suggestion)
                else:
                    flagged.append(suggestion)

            iter_flagged = len(flagged)
            result.fixes_flagged_count += iter_flagged

            # Step 3: Check for stall (no applicable fixes)
            if len(auto_apply) == 0:
                result.stop_reason = "stall"
                result.iteration_history.append(
                    IterationRecord(
                        iteration=iteration_num,
                        total_violations=current_violations,
                        applied_count=0,
                        flagged_count=iter_flagged,
                    )
                )
                break

            # Step 4: Apply qualifying fixes
            layout_mgr_apply = LayoutManager()
            layout_mgr_apply.load(current_gds_path)
            applied = _apply_deltas_from_suggestions(layout_mgr_apply, auto_apply)
            result.fixes_applied_count += applied

            # Step 5: Export fixed GDS
            new_iteration = job.iteration + iteration_num
            fixed_path = export_fixed_gds(
                layout_mgr_apply, job_dir, original_stem, new_iteration
            )

            # Update job status
            self._manager.update_status(
                job.job_id,
                JobStatus.running_drc,
                gds_path=str(fixed_path),
                iteration=new_iteration,
            )

            # Step 6: Re-run DRC
            drc_runner = DRCRunner()
            try:
                drc_result = await drc_runner.async_run(
                    gds_path=fixed_path,
                    pdk=self._pdk,
                    top_cell=job.top_cell,
                    output_dir=job_dir,
                )
            except (DRCError, FileNotFoundError) as e:
                self._manager.update_status(
                    job.job_id, JobStatus.drc_failed, error=str(e)
                )
                result.stop_reason = "drc_error"
                result.iteration_history.append(
                    IterationRecord(
                        iteration=iteration_num,
                        total_violations=current_violations,
                        applied_count=applied,
                        flagged_count=iter_flagged,
                    )
                )
                break

            new_violation_count = drc_result.report.total_violations

            # Update job with DRC results
            new_status = (
                JobStatus.complete
                if new_violation_count == 0
                else JobStatus.drc_complete
            )
            self._manager.update_status(
                job.job_id,
                new_status,
                report_path=str(drc_result.report_path),
                top_cell=drc_result.report.top_cell,
                total_violations=new_violation_count,
            )

            # Record iteration
            result.iteration_history.append(
                IterationRecord(
                    iteration=iteration_num,
                    total_violations=new_violation_count,
                    applied_count=applied,
                    flagged_count=iter_flagged,
                )
            )

            result.iterations_run = iteration_num
            result.final_violation_count = new_violation_count

            # Update pointers for next iteration
            current_gds_path = fixed_path
            report_path = drc_result.report_path
            previous_violations = current_violations
            current_violations = new_violation_count

            # Check DRC clean
            if new_violation_count == 0:
                result.stop_reason = "drc_clean"
                break

            # Check regression: violation count increased
            if new_violation_count > previous_violations:
                result.stop_reason = "regression"
                break

        else:
            # max_iterations reached without break
            result.stop_reason = "max_iterations"
            result.iterations_run = max_iterations

        result.final_violation_count = current_violations

        return result

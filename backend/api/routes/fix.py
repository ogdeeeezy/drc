"""Fix route — generate, preview, apply fix suggestions, and re-DRC loop."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_job_manager, get_pdk_registry
from backend.core.drc_runner import DRCError, DRCRunner
from backend.core.layout import LayoutManager
from backend.core.spatial_index import SpatialIndex
from backend.core.violation_parser import ViolationParser
from backend.export.gdsii import export_fixed_gds
from backend.fix.engine import FixEngine, FixEngineResult
from backend.jobs.manager import JobStatus

router = APIRouter(prefix="/jobs", tags=["fix"])

# Cache fix results per job (in-memory)
_fix_results_cache: dict[str, FixEngineResult] = {}


def clear_fix_cache(job_id: str) -> None:
    """Clear cached fix results for a job (called on re-DRC)."""
    _fix_results_cache.pop(job_id, None)


class ApplyFixRequest(BaseModel):
    suggestion_indices: list[int]


@router.post("/{job_id}/fix/suggest")
async def suggest_fixes(job_id: str):
    """Generate fix suggestions for all violations in a DRC report."""
    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        raise HTTPException(404, f"Job '{job_id}' not found")

    if job.report_path is None:
        raise HTTPException(400, "No DRC report available. Run DRC first.")
    if job.gds_path is None:
        raise HTTPException(400, "No GDSII file for this job.")

    gds_path = Path(job.gds_path)
    report_path = Path(job.report_path)

    if not gds_path.exists():
        raise HTTPException(404, "GDSII file not found on disk")
    if not report_path.exists():
        raise HTTPException(404, "DRC report file not found on disk")

    # Load PDK
    registry = get_pdk_registry()
    try:
        pdk = registry.load(job.pdk_name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))

    # Parse report
    parser = ViolationParser()
    report = parser.parse_file(report_path)
    parser.map_to_pdk(report, pdk)

    # Build spatial index from layout
    layout_mgr = LayoutManager()
    layout_mgr.load(gds_path)
    polygons = layout_mgr.get_flattened_polygons()
    spatial_index = SpatialIndex.from_polygons(polygons)

    # Run fix engine
    engine = FixEngine(pdk, spatial_index)
    result = engine.suggest_fixes(report)

    # Cache for preview/apply
    _fix_results_cache[job_id] = result

    manager.update_status(job_id, JobStatus.fixing)

    return {
        "job_id": job_id,
        "total_suggestions": result.total_suggestions,
        "fixable_count": result.fixable_count,
        "unfixable_count": len(result.unfixable),
        "suggestions": [
            {
                "index": i,
                "violation_category": s.violation_category,
                "rule_type": s.rule_type,
                "description": s.description,
                "confidence": s.confidence.value,
                "priority": s.priority,
                "creates_new_violations": s.creates_new_violations,
                "validation_notes": s.validation_notes,
                "delta_count": s.delta_count,
                "affected_layers": [list(lp) for lp in s.affected_layers],
            }
            for i, s in enumerate(result.suggestions)
        ],
    }


@router.get("/{job_id}/fix/preview/{suggestion_index}")
async def preview_fix(job_id: str, suggestion_index: int):
    """Preview a fix suggestion — returns before/after polygon data."""
    result = _fix_results_cache.get(job_id)
    if result is None:
        raise HTTPException(400, "No fix suggestions cached. Run suggest first.")

    if suggestion_index < 0 or suggestion_index >= len(result.suggestions):
        raise HTTPException(
            404,
            f"Suggestion index {suggestion_index} out of range (0-{len(result.suggestions) - 1})",
        )

    suggestion = result.suggestions[suggestion_index]

    return {
        "job_id": job_id,
        "suggestion_index": suggestion_index,
        "description": suggestion.description,
        "confidence": suggestion.confidence.value,
        "deltas": [
            {
                "cell_name": d.cell_name,
                "gds_layer": d.gds_layer,
                "gds_datatype": d.gds_datatype,
                "original_points": d.original_points,
                "modified_points": d.modified_points,
                "is_removal": d.is_removal,
                "is_addition": d.is_addition,
            }
            for d in suggestion.deltas
        ],
    }


@router.post("/{job_id}/fix/apply")
async def apply_fixes(job_id: str, request: ApplyFixRequest):
    """Apply selected fix suggestions to the layout.

    Creates a versioned modified GDSII file. The original is preserved.
    Status transitions to fixes_applied — allowing re-DRC.
    """
    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        raise HTTPException(404, f"Job '{job_id}' not found")

    result = _fix_results_cache.get(job_id)
    if result is None:
        raise HTTPException(400, "No fix suggestions cached. Run suggest first.")

    if job.gds_path is None:
        raise HTTPException(400, "No GDSII file for this job.")

    gds_path = Path(job.gds_path)
    if not gds_path.exists():
        raise HTTPException(404, "GDSII file not found on disk")

    # Validate indices
    for idx in request.suggestion_indices:
        if idx < 0 or idx >= len(result.suggestions):
            raise HTTPException(
                400,
                f"Suggestion index {idx} out of range (0-{len(result.suggestions) - 1})",
            )

    # Load layout
    layout_mgr = LayoutManager()
    layout_mgr.load(gds_path)

    # Apply deltas
    applied = _apply_deltas(layout_mgr, result, request.suggestion_indices)

    # Export versioned fixed GDS
    job_dir = manager.job_dir(job_id)
    original_stem = Path(job.filename).stem
    fixed_path = export_fixed_gds(layout_mgr, job_dir, original_stem, job.iteration)

    # Update job — stays at fixes_applied to allow re-DRC
    manager.update_status(
        job_id,
        JobStatus.fixes_applied,
        gds_path=str(fixed_path),
    )

    return {
        "job_id": job_id,
        "applied_count": applied,
        "total_requested": len(request.suggestion_indices),
        "fixed_gds_path": str(fixed_path),
        "iteration": job.iteration,
        "status": "fixes_applied",
    }


@router.post("/{job_id}/fix/apply-and-recheck")
async def apply_and_recheck(job_id: str, request: ApplyFixRequest):
    """Apply fixes and immediately re-run DRC on the modified layout.

    This is the core re-DRC loop endpoint:
    1. Apply selected fix suggestions
    2. Save modified GDSII (versioned)
    3. Re-run DRC
    4. Increment iteration counter
    5. Return new violation count

    Loop until clean or user stops.
    """
    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        raise HTTPException(404, f"Job '{job_id}' not found")

    result = _fix_results_cache.get(job_id)
    if result is None:
        raise HTTPException(400, "No fix suggestions cached. Run suggest first.")

    if job.gds_path is None:
        raise HTTPException(400, "No GDSII file for this job.")

    gds_path = Path(job.gds_path)
    if not gds_path.exists():
        raise HTTPException(404, "GDSII file not found on disk")

    # Validate indices
    for idx in request.suggestion_indices:
        if idx < 0 or idx >= len(result.suggestions):
            raise HTTPException(
                400,
                f"Suggestion index {idx} out of range (0-{len(result.suggestions) - 1})",
            )

    # Step 1: Apply fixes
    layout_mgr = LayoutManager()
    layout_mgr.load(gds_path)
    applied = _apply_deltas(layout_mgr, result, request.suggestion_indices)

    # Step 2: Save versioned fixed GDS
    job_dir = manager.job_dir(job_id)
    original_stem = Path(job.filename).stem
    fixed_path = export_fixed_gds(layout_mgr, job_dir, original_stem, job.iteration)

    # Increment iteration
    new_iteration = job.iteration + 1
    manager.update_status(
        job_id,
        JobStatus.running_drc,
        gds_path=str(fixed_path),
        iteration=new_iteration,
    )

    # Clear fix cache for fresh suggestions
    clear_fix_cache(job_id)

    # Step 3: Re-run DRC
    registry = get_pdk_registry()
    try:
        pdk = registry.load(job.pdk_name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))

    runner = DRCRunner()
    try:
        drc_result = runner.run(
            gds_path=fixed_path,
            pdk=pdk,
            top_cell=job.top_cell,
            output_dir=job_dir,
        )
    except DRCError as e:
        manager.update_status(job_id, JobStatus.drc_failed, error=str(e))
        raise HTTPException(500, f"Re-DRC failed: {e}")
    except FileNotFoundError as e:
        manager.update_status(job_id, JobStatus.drc_failed, error=str(e))
        raise HTTPException(404, str(e))

    # Step 4: Update with results
    new_status = (
        JobStatus.complete if drc_result.report.total_violations == 0 else JobStatus.drc_complete
    )
    manager.update_status(
        job_id,
        new_status,
        report_path=str(drc_result.report_path),
        top_cell=drc_result.report.top_cell,
        total_violations=drc_result.report.total_violations,
    )

    return {
        "job_id": job_id,
        "applied_count": applied,
        "iteration": new_iteration,
        "status": new_status.value,
        "total_violations": drc_result.report.total_violations,
        "previous_violations": job.total_violations,
        "duration_seconds": round(drc_result.duration_seconds, 2),
        "is_clean": drc_result.report.total_violations == 0,
        "categories": [
            {
                "category": v.category,
                "description": v.description,
                "count": v.violation_count,
            }
            for v in drc_result.report.violations
        ],
    }


def _apply_deltas(
    layout_mgr: LayoutManager,
    result: FixEngineResult,
    indices: list[int],
) -> int:
    """Apply polygon deltas from selected suggestions. Returns count of applied deltas."""
    applied = 0
    for idx in indices:
        suggestion = result.suggestions[idx]
        for delta in suggestion.deltas:
            try:
                cell = layout_mgr.get_cell(delta.cell_name)
                # Find matching polygon by original points
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
        abs(p1[0] - p2[0]) < tolerance and abs(p1[1] - p2[1]) < tolerance for p1, p2 in zip(a, b)
    )

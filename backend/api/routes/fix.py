"""Fix route — generate, preview, and apply fix suggestions."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.deps import get_job_manager, get_pdk_registry
from backend.core.layout import LayoutManager
from backend.core.spatial_index import SpatialIndex
from backend.core.violation_parser import ViolationParser
from backend.fix.engine import FixEngine
from backend.jobs.manager import JobStatus

router = APIRouter(prefix="/jobs", tags=["fix"])

# Cache fix results per job (in-memory for now)
_fix_cache: dict[str, "FixEngine"] = {}
_fix_results_cache: dict[str, object] = {}


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
    from backend.fix.engine import FixEngineResult
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
                "affected_layers": [list(l) for l in s.affected_layers],
            }
            for i, s in enumerate(result.suggestions)
        ],
    }


@router.get("/{job_id}/fix/preview/{suggestion_index}")
async def preview_fix(job_id: str, suggestion_index: int):
    """Preview a fix suggestion — returns before/after polygon data."""
    from backend.fix.engine import FixEngineResult

    result: FixEngineResult | None = _fix_results_cache.get(job_id)
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

    Creates a modified GDSII file. The original is preserved.
    """
    from backend.fix.engine import FixEngineResult

    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        raise HTTPException(404, f"Job '{job_id}' not found")

    result: FixEngineResult | None = _fix_results_cache.get(job_id)
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
    applied = 0
    for idx in request.suggestion_indices:
        suggestion = result.suggestions[idx]
        for delta in suggestion.deltas:
            try:
                cell = layout_mgr.get_cell(delta.cell_name)
                # Find matching polygon by original points
                for i, poly in enumerate(cell.polygons):
                    if (poly.layer == delta.gds_layer
                            and poly.datatype == delta.gds_datatype):
                        poly_pts = [(float(p[0]), float(p[1])) for p in poly.points]
                        if _points_match(poly_pts, delta.original_points):
                            if delta.is_removal:
                                layout_mgr.remove_polygon(delta.cell_name, i)
                            else:
                                layout_mgr.replace_polygon(
                                    delta.cell_name, i, delta.modified_points
                                )
                            applied += 1
                            break
                else:
                    if delta.is_addition:
                        layout_mgr.add_polygon(
                            delta.cell_name,
                            delta.modified_points,
                            delta.gds_layer,
                            delta.gds_datatype,
                        )
                        applied += 1
            except (KeyError, IndexError):
                continue

    # Save modified layout
    job_dir = manager.job_dir(job_id)
    fixed_path = job_dir / f"{gds_path.stem}_fixed.gds"
    layout_mgr.save(fixed_path)

    manager.update_status(
        job_id,
        JobStatus.complete,
        gds_path=str(fixed_path),
    )

    return {
        "job_id": job_id,
        "applied_count": applied,
        "total_requested": len(request.suggestion_indices),
        "fixed_gds_path": str(fixed_path),
        "status": "complete",
    }


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

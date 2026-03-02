"""DRC route — run DRC checks and retrieve violations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.deps import get_job_manager, get_pdk_registry
from backend.core.drc_runner import DRCError, DRCRunner
from backend.jobs.manager import JobStatus

router = APIRouter(prefix="/jobs", tags=["drc"])


@router.post("/{job_id}/drc")
async def run_drc(job_id: str, top_cell: str | None = None):
    """Run DRC on an uploaded or fixed GDSII file.

    Supports re-DRC after fix application — clears fix cache and
    increments iteration when re-running from fixes_applied status.
    """
    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        raise HTTPException(404, f"Job '{job_id}' not found")

    if job.gds_path is None:
        raise HTTPException(400, "No GDSII file uploaded for this job")

    if job.status == JobStatus.running_drc:
        raise HTTPException(409, "DRC already running for this job")

    # Clear fix cache on re-run
    from backend.api.routes.fix import clear_fix_cache

    clear_fix_cache(job_id)

    # Increment iteration on re-DRC after fixes
    if job.status == JobStatus.fixes_applied:
        manager.update_status(job_id, JobStatus.running_drc, iteration=job.iteration + 1)
        job = manager.get(job_id)  # refresh

    # Load PDK
    registry = get_pdk_registry()
    try:
        pdk = registry.load(job.pdk_name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))

    # Update status
    manager.update_status(job_id, JobStatus.running_drc)

    # Run DRC
    runner = DRCRunner()
    job_dir = manager.job_dir(job_id)
    try:
        from pathlib import Path

        result = runner.run(
            gds_path=Path(job.gds_path),
            pdk=pdk,
            top_cell=top_cell,
            output_dir=job_dir,
        )
    except DRCError as e:
        manager.update_status(job_id, JobStatus.drc_failed, error=str(e))
        raise HTTPException(500, f"DRC failed: {e}")
    except FileNotFoundError as e:
        manager.update_status(job_id, JobStatus.drc_failed, error=str(e))
        raise HTTPException(404, str(e))

    # Update job with results
    manager.update_status(
        job_id,
        JobStatus.drc_complete,
        report_path=str(result.report_path),
        top_cell=result.report.top_cell,
        total_violations=result.report.total_violations,
    )

    return {
        "job_id": job_id,
        "status": "drc_complete",
        "total_violations": result.report.total_violations,
        "duration_seconds": round(result.duration_seconds, 2),
        "categories": [
            {
                "category": v.category,
                "description": v.description,
                "count": v.violation_count,
                "severity": v.severity,
                "rule_type": v.rule_type,
            }
            for v in result.report.violations
        ],
    }


@router.get("/{job_id}/violations")
async def get_violations(job_id: str, category: str | None = None):
    """Get parsed violations for a completed DRC job."""
    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        raise HTTPException(404, f"Job '{job_id}' not found")

    if job.report_path is None:
        raise HTTPException(400, "No DRC report available. Run DRC first.")

    # Re-parse the report
    from pathlib import Path

    from backend.core.violation_parser import ViolationParser

    parser = ViolationParser()
    report_path = Path(job.report_path)
    if not report_path.exists():
        raise HTTPException(404, "DRC report file not found on disk")

    report = parser.parse_file(report_path)

    # Map to PDK rules
    registry = get_pdk_registry()
    try:
        pdk = registry.load(job.pdk_name)
        parser.map_to_pdk(report, pdk)
    except FileNotFoundError:
        pass  # Serve violations without PDK mapping

    violations = report.violations
    if category:
        violations = [v for v in violations if v.category == category]

    return {
        "job_id": job_id,
        "total_violations": sum(v.violation_count for v in violations),
        "violations": [
            {
                "category": v.category,
                "description": v.description,
                "cell_name": v.cell_name,
                "rule_id": v.rule_id,
                "rule_type": v.rule_type,
                "severity": v.severity,
                "value_um": v.value_um,
                "count": v.violation_count,
                "bbox": list(v.bbox),
                "geometries": [
                    {
                        "type": g.geometry_type.value,
                        "bbox": list(g.bbox),
                        "edge_pair": {
                            "edge1": [list(g.edge_pair.edge1_start), list(g.edge_pair.edge1_end)],
                            "edge2": [list(g.edge_pair.edge2_start), list(g.edge_pair.edge2_end)],
                        }
                        if g.edge_pair
                        else None,
                        "points": g.points,
                    }
                    for g in v.geometries
                ],
            }
            for v in violations
        ],
    }

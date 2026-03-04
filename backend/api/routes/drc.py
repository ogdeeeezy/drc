"""DRC route — run DRC checks and retrieve violations."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from backend.api.deps import get_job_manager, get_pdk_registry
from backend.core.drc_runner import DRCError, DRCRunner
from backend.core.error_hints import get_hint
from backend.jobs.manager import JobStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["drc"])


async def _run_drc_background(
    job_id: str,
    gds_path: str,
    pdk_name: str,
    top_cell: str | None,
    job_dir: str,
) -> None:
    """Background coroutine that runs DRC and updates job status on completion."""
    manager = get_job_manager()
    registry = get_pdk_registry()

    try:
        pdk = registry.load(pdk_name)
    except FileNotFoundError as e:
        manager.update_status(job_id, JobStatus.drc_failed, error=str(e), hint=get_hint(str(e)))
        return

    runner = DRCRunner()
    try:
        from pathlib import Path

        result = await runner.async_run(
            gds_path=Path(gds_path),
            pdk=pdk,
            top_cell=top_cell,
            output_dir=job_dir,
        )
    except DRCError as e:
        logger.error("DRC failed for job %s: %s", job_id, e)
        manager.update_status(job_id, JobStatus.drc_failed, error=str(e), hint=get_hint(str(e)))
        return
    except FileNotFoundError as e:
        logger.error("File not found during DRC for job %s: %s", job_id, e)
        manager.update_status(job_id, JobStatus.drc_failed, error=str(e), hint=get_hint(str(e)))
        return

    manager.update_status(
        job_id,
        JobStatus.drc_complete,
        report_path=str(result.report_path),
        top_cell=result.report.top_cell,
        total_violations=result.report.total_violations,
    )
    logger.info(
        "DRC complete for job %s: %d violations in %.1fs",
        job_id,
        result.report.total_violations,
        result.duration_seconds,
    )


@router.post("/{job_id}/drc")
async def run_drc(job_id: str, top_cell: str | None = None):
    """Run DRC on an uploaded or fixed GDSII file.

    Returns immediately with status 'running_drc'. DRC runs asynchronously
    in the background — poll GET /api/jobs/{job_id} for completion.

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
    else:
        # Update status to running_drc
        manager.update_status(job_id, JobStatus.running_drc)

    job_dir = str(manager.job_dir(job_id))

    # Launch DRC as a background task — does not block the response
    asyncio.create_task(
        _run_drc_background(job_id, job.gds_path, job.pdk_name, top_cell, job_dir)
    )

    return {
        "job_id": job_id,
        "status": "running_drc",
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

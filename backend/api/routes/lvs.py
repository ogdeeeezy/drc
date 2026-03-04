"""LVS route — upload netlist, run LVS, retrieve mismatch results."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from backend.api.deps import get_job_manager, get_pdk_registry
from backend.core.error_hints import get_hint
from backend.core.lvs_parser import LVSParseError, LVSReportParser
from backend.core.lvs_runner import LVSError, LVSRunner
from backend.jobs.manager import JobStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["lvs"])

ALLOWED_NETLIST_EXTENSIONS = {".spice", ".sp", ".cir", ".net", ".cdl"}
MAX_NETLIST_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/{job_id}/lvs/upload")
async def upload_netlist(job_id: str, file: UploadFile):
    """Upload a SPICE netlist file for LVS comparison.

    The netlist is stored alongside the GDS in the job directory.
    """
    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        raise HTTPException(404, f"Job '{job_id}' not found")

    if file.filename is None:
        raise HTTPException(400, "Filename is required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_NETLIST_EXTENSIONS:
        raise HTTPException(
            400,
            f"Invalid netlist file type '{suffix}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_NETLIST_EXTENSIONS))}",
        )

    job_dir = manager.job_dir(job_id)
    netlist_path = job_dir / file.filename

    try:
        total = 0
        with open(netlist_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_NETLIST_SIZE:
                    netlist_path.unlink(missing_ok=True)
                    max_mb = MAX_NETLIST_SIZE // (1024 * 1024)
                    raise HTTPException(413, f"Netlist too large. Max: {max_mb} MB")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        netlist_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Failed to save netlist: {e}")

    manager.update_status(
        job_id,
        job.status,  # keep current status
        netlist_path=str(netlist_path),
    )

    return {
        "job_id": job_id,
        "netlist_filename": file.filename,
        "netlist_path": str(netlist_path),
    }


async def _run_lvs_background(
    job_id: str,
    gds_path: str,
    netlist_path: str,
    pdk_name: str,
    job_dir: str,
) -> None:
    """Background coroutine that runs LVS and updates job status on completion."""
    manager = get_job_manager()
    registry = get_pdk_registry()

    try:
        pdk = registry.load(pdk_name)
    except FileNotFoundError as e:
        manager.update_status(job_id, JobStatus.lvs_failed, error=str(e), hint=get_hint(str(e)))
        return

    runner = LVSRunner()
    try:
        result = await runner.async_run(
            gds_path=Path(gds_path),
            netlist_path=Path(netlist_path),
            pdk=pdk,
            output_dir=job_dir,
        )
    except LVSError as e:
        logger.error("LVS failed for job %s: %s", job_id, e)
        manager.update_status(job_id, JobStatus.lvs_failed, error=str(e), hint=get_hint(str(e)))
        return
    except FileNotFoundError as e:
        logger.error("File not found during LVS for job %s: %s", job_id, e)
        manager.update_status(job_id, JobStatus.lvs_failed, error=str(e), hint=get_hint(str(e)))
        return

    # Parse the report to get match status
    try:
        parser = LVSReportParser()
        report = parser.parse_file(result.report_path)
        match = report.match
    except (LVSParseError, FileNotFoundError):
        match = False

    manager.update_status(
        job_id,
        JobStatus.lvs_complete,
        lvs_report_path=str(result.report_path),
    )
    logger.info(
        "LVS complete for job %s: %s in %.1fs",
        job_id,
        "match" if match else "mismatch",
        result.duration_seconds,
    )


@router.post("/{job_id}/lvs/run")
async def run_lvs(job_id: str):
    """Run LVS on a job's layout against an uploaded netlist.

    Returns immediately with status 'running_lvs'. LVS runs asynchronously
    in the background — poll GET /api/jobs/{job_id} for completion.
    """
    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        raise HTTPException(404, f"Job '{job_id}' not found")

    if job.gds_path is None:
        raise HTTPException(400, "No GDSII file uploaded for this job. Upload a layout first.")

    if job.netlist_path is None:
        raise HTTPException(400, "No netlist uploaded for this job. Upload a netlist first.")

    if job.status == JobStatus.running_lvs:
        raise HTTPException(409, "LVS already running for this job")

    manager.update_status(job_id, JobStatus.running_lvs)

    job_dir = str(manager.job_dir(job_id))

    asyncio.create_task(
        _run_lvs_background(job_id, job.gds_path, job.netlist_path, job.pdk_name, job_dir)
    )

    return {
        "job_id": job_id,
        "status": "running_lvs",
    }


@router.get("/{job_id}/lvs/results")
async def get_lvs_results(job_id: str):
    """Get parsed LVS results for a completed LVS job."""
    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        raise HTTPException(404, f"Job '{job_id}' not found")

    if job.lvs_report_path is None:
        raise HTTPException(400, "No LVS report available. Run LVS first.")

    report_path = Path(job.lvs_report_path)
    if not report_path.exists():
        raise HTTPException(404, "LVS report file not found on disk")

    parser = LVSReportParser()
    try:
        report = parser.parse_file(report_path)
    except LVSParseError as e:
        raise HTTPException(500, f"Failed to parse LVS report: {e}")

    return {
        "job_id": job_id,
        "match": report.match,
        "devices_matched": report.devices_matched,
        "devices_mismatched": report.devices_mismatched,
        "nets_matched": report.nets_matched,
        "nets_mismatched": report.nets_mismatched,
        "mismatches": [
            {
                "type": m.type.value,
                "name": m.name,
                "expected": m.expected,
                "actual": m.actual,
                "details": m.details,
            }
            for m in report.mismatches
        ],
    }

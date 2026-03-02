"""Upload route — GDSII file upload and job creation."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from backend.api.deps import get_job_manager, get_pdk_registry
from backend.jobs.manager import JobStatus

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_EXTENSIONS = {".gds", ".gds2", ".gdsii"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


@router.post("")
async def upload_gds(file: UploadFile, pdk_name: str = "sky130"):
    """Upload a GDSII file and create a DRC job.

    Returns the job ID for subsequent operations.
    """
    # Validate file extension
    if file.filename is None:
        raise HTTPException(400, "Filename is required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Invalid file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Validate PDK exists
    registry = get_pdk_registry()
    available = registry.list_pdks()
    if pdk_name not in available:
        raise HTTPException(404, f"PDK '{pdk_name}' not found. Available: {available}")

    # Create job
    manager = get_job_manager()
    job = manager.create(filename=file.filename, pdk_name=pdk_name)

    # Save uploaded file
    job_dir = manager.job_dir(job.job_id)
    gds_path = job_dir / file.filename

    try:
        with open(gds_path, "wb") as f:
            # Read in chunks to handle large files
            total = 0
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    gds_path.unlink(missing_ok=True)
                    raise HTTPException(413, f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)} MB")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        gds_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Failed to save file: {e}")

    # Update job with file path
    manager.update_status(
        job.job_id,
        JobStatus.uploaded,
        gds_path=str(gds_path),
    )

    return {
        "job_id": job.job_id,
        "filename": file.filename,
        "pdk_name": pdk_name,
        "status": "uploaded",
    }

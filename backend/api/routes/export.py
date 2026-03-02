"""Export route — download DRC reports in JSON, CSV, or HTML format."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

from backend.api.deps import get_job_manager, get_pdk_registry
from backend.core.violation_parser import ViolationParser
from backend.export.report import export_csv, export_html, export_json

router = APIRouter(prefix="/jobs", tags=["export"])

_FORMATS = {"json", "csv", "html"}


@router.get("/{job_id}/report/{fmt}")
async def download_report(job_id: str, fmt: str):
    """Download DRC report in JSON, CSV, or HTML format."""
    if fmt not in _FORMATS:
        raise HTTPException(400, f"Unsupported format '{fmt}'. Use: json, csv, html")

    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        raise HTTPException(404, f"Job '{job_id}' not found")

    if job.report_path is None:
        raise HTTPException(400, "No DRC report available. Run DRC first.")

    report_path = Path(job.report_path)
    if not report_path.exists():
        raise HTTPException(404, "DRC report file not found on disk")

    # Parse and PDK-map the report
    parser = ViolationParser()
    report = parser.parse_file(report_path)

    registry = get_pdk_registry()
    try:
        pdk = registry.load(job.pdk_name)
        parser.map_to_pdk(report, pdk)
    except FileNotFoundError:
        pass

    if fmt == "json":
        return PlainTextResponse(
            export_json(job, report),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="drc_report_{job_id}.json"'},
        )
    elif fmt == "csv":
        return PlainTextResponse(
            export_csv(job, report),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="drc_report_{job_id}.csv"'},
        )
    else:
        return HTMLResponse(export_html(job, report))

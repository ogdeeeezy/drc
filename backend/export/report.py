"""DRC report export — JSON, CSV, and HTML formats."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from backend.core.violation_models import DRCReport
from backend.jobs.manager import Job


def export_json(job: Job, report: DRCReport) -> str:
    """Export DRC report as structured JSON."""
    data = {
        "report": {
            "job_id": job.job_id,
            "filename": job.filename,
            "pdk_name": job.pdk_name,
            "iteration": job.iteration,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_violations": report.total_violations,
            "top_cell": report.top_cell,
        },
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
            }
            for v in report.violations
        ],
    }
    return json.dumps(data, indent=2)


def export_csv(job: Job, report: DRCReport) -> str:
    """Export violations as CSV — one row per violation category."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "category",
            "description",
            "cell_name",
            "rule_id",
            "rule_type",
            "severity",
            "value_um",
            "count",
            "bbox_xmin",
            "bbox_ymin",
            "bbox_xmax",
            "bbox_ymax",
        ]
    )
    for v in report.violations:
        bbox = v.bbox
        writer.writerow(
            [
                v.category,
                v.description,
                v.cell_name,
                v.rule_id or "",
                v.rule_type or "",
                v.severity,
                v.value_um or "",
                v.violation_count,
                f"{bbox[0]:.4f}",
                f"{bbox[1]:.4f}",
                f"{bbox[2]:.4f}",
                f"{bbox[3]:.4f}",
            ]
        )
    return output.getvalue()


def export_html(job: Job, report: DRCReport) -> str:
    """Export DRC report as a standalone HTML page."""
    rows = ""
    for v in report.violations:
        severity_color = _severity_color(v.severity)
        rows += (
            "        <tr>\n"
            f"            <td>{_esc(v.category)}</td>\n"
            f"            <td>{_esc(v.description)}</td>\n"
            f"            <td>{_esc(v.cell_name)}</td>\n"
            f"            <td>{_esc(v.rule_type or '-')}</td>\n"
            f'            <td style="color:{severity_color};font-weight:bold">{v.severity}</td>\n'
            f"            <td>{v.violation_count}</td>\n"
            "        </tr>\n"
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '    <meta charset="utf-8">\n'
        f"    <title>DRC Report &mdash; {_esc(job.filename)}</title>\n"
        "    <style>\n"
        "        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;"
        " margin: 2rem; background: #f8f9fa; }\n"
        "        h1 { color: #1a1a2e; }\n"
        "        .meta { background: #fff; padding: 1rem; border-radius: 8px;"
        " margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }\n"
        "        .meta span { margin-right: 2rem; }\n"
        "        table { width: 100%; border-collapse: collapse; background: #fff;"
        " border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }\n"
        "        th { background: #1a1a2e; color: #fff; text-align: left;"
        " padding: 0.75rem 1rem; }\n"
        "        td { padding: 0.75rem 1rem; border-bottom: 1px solid #eee; }\n"
        "        tr:hover { background: #f0f4ff; }\n"
        "        .summary { font-size: 1.2rem; color: #e63946; font-weight: bold; }\n"
        "    </style>\n"
        "</head>\n"
        "<body>\n"
        "    <h1>DRC Report</h1>\n"
        '    <div class="meta">\n'
        f"        <span><b>File:</b> {_esc(job.filename)}</span>\n"
        f"        <span><b>PDK:</b> {_esc(job.pdk_name)}</span>\n"
        f"        <span><b>Iteration:</b> {job.iteration}</span>\n"
        f"        <span><b>Top cell:</b> {_esc(report.top_cell)}</span>\n"
        f'        <span class="summary">Total violations: {report.total_violations}</span>\n'
        "    </div>\n"
        "    <table>\n"
        "        <thead>\n"
        "            <tr>\n"
        "                <th>Category</th>\n"
        "                <th>Description</th>\n"
        "                <th>Cell</th>\n"
        "                <th>Rule Type</th>\n"
        "                <th>Severity</th>\n"
        "                <th>Count</th>\n"
        "            </tr>\n"
        "        </thead>\n"
        "        <tbody>\n"
        f"{rows}"
        "        </tbody>\n"
        "    </table>\n"
        f'    <p style="color:#999;margin-top:2rem">Generated by Agentic DRC &mdash; {now}</p>\n'
        "</body>\n"
        "</html>"
    )


def _severity_color(severity: int) -> str:
    if severity >= 8:
        return "#e63946"
    if severity >= 5:
        return "#f4a261"
    return "#2a9d8f"


def _esc(text: str) -> str:
    """Minimal HTML escaping."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

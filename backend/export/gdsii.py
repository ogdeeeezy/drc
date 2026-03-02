"""GDSII export — versioned export of modified layouts."""

from __future__ import annotations

from pathlib import Path

from backend.core.layout import LayoutManager


def export_fixed_gds(
    layout_mgr: LayoutManager,
    job_dir: Path,
    original_stem: str,
    iteration: int = 1,
) -> Path:
    """Export a modified layout with version tracking.

    Naming convention:
    - Iteration 1: {stem}_fixed.gds
    - Iteration N: {stem}_fixed_v{N}.gds
    """
    if iteration <= 1:
        filename = f"{original_stem}_fixed.gds"
    else:
        filename = f"{original_stem}_fixed_v{iteration}.gds"

    output_path = job_dir / filename
    layout_mgr.save(output_path)
    return output_path


def list_fixed_versions(job_dir: Path, original_stem: str) -> list[Path]:
    """List all fixed GDSII versions for a job, ordered by name."""
    return sorted(job_dir.glob(f"{original_stem}_fixed*.gds"))

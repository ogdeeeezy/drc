"""Layout route — serve geometry data for the WebGL viewer."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.api.deps import get_job_manager, get_pdk_registry
from backend.core.layout import LayoutManager

router = APIRouter(prefix="/jobs", tags=["layout"])


@router.get("/{job_id}/layout")
async def get_layout(job_id: str, cell_name: str | None = None):
    """Get layout geometry for the WebGL viewer.

    Returns polygons grouped by layer with PDK colors.
    """
    manager = get_job_manager()
    try:
        job = manager.get(job_id)
    except KeyError:
        raise HTTPException(404, f"Job '{job_id}' not found")

    if job.gds_path is None:
        raise HTTPException(400, "No GDSII file for this job")

    gds_path = Path(job.gds_path)
    if not gds_path.exists():
        raise HTTPException(404, "GDSII file not found on disk")

    # Load layout
    layout_mgr = LayoutManager()
    layout_mgr.load(gds_path)

    # Get cells
    cells = layout_mgr.list_cells()
    if not cells:
        raise HTTPException(400, "Layout has no cells")

    # Get polygons (flattened for viewer)
    polygons = layout_mgr.get_flattened_polygons(cell_name=cell_name)

    # Load PDK for layer colors
    registry = get_pdk_registry()
    layer_colors: dict[str, str] = {}
    layer_names: dict[str, str] = {}
    try:
        pdk = registry.load(job.pdk_name)
        for name, layer in pdk.layers.items():
            key = f"{layer.gds_layer}:{layer.gds_datatype}"
            layer_colors[key] = layer.color
            layer_names[key] = name
    except FileNotFoundError:
        pass

    # Group polygons by layer
    layers: dict[str, dict] = {}
    for poly in polygons:
        key = f"{poly.gds_layer}:{poly.gds_datatype}"
        if key not in layers:
            layers[key] = {
                "gds_layer": poly.gds_layer,
                "gds_datatype": poly.gds_datatype,
                "name": layer_names.get(key, f"L{poly.gds_layer}"),
                "color": layer_colors.get(key, "#808080"),
                "polygons": [],
            }
        layers[key]["polygons"].append(poly.points)

    # Compute overall bounding box
    if polygons:
        all_x = [p[0] for poly in polygons for p in poly.points]
        all_y = [p[1] for poly in polygons for p in poly.points]
        bbox = [min(all_x), min(all_y), max(all_x), max(all_y)]
    else:
        bbox = [0, 0, 0, 0]

    return {
        "job_id": job_id,
        "cells": [
            {
                "name": c.name,
                "polygon_count": c.polygon_count,
                "bbox": list(c.bbox) if c.bbox else None,
            }
            for c in cells
        ],
        "bbox": bbox,
        "layers": list(layers.values()),
        "total_polygons": len(polygons),
    }

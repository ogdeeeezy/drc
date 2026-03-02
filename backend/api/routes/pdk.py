"""PDK route — list and inspect PDK configurations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.deps import get_pdk_registry

router = APIRouter(prefix="/pdks", tags=["pdk"])


@router.get("")
async def list_pdks():
    """List available PDK configurations."""
    registry = get_pdk_registry()
    return {"pdks": registry.list_pdks()}


@router.get("/{pdk_name}")
async def get_pdk(pdk_name: str):
    """Get PDK configuration details."""
    registry = get_pdk_registry()
    try:
        config = registry.load(pdk_name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))

    return {
        "name": config.name,
        "version": config.version,
        "process_node_nm": config.process_node_nm,
        "grid_um": config.grid_um,
        "layer_count": len(config.layers),
        "rule_count": len(config.rules),
        "layers": {
            name: {
                "gds_layer": layer.gds_layer,
                "gds_datatype": layer.gds_datatype,
                "description": layer.description,
                "color": layer.color,
            }
            for name, layer in config.layers.items()
        },
        "rules": [
            {
                "rule_id": r.rule_id,
                "rule_type": r.rule_type.value,
                "layer": r.layer,
                "related_layer": r.related_layer,
                "value_um": r.value_um,
                "severity": r.severity,
            }
            for r in config.rules
        ],
    }

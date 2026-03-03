"""PCell route — generate parameterized cells with self-validation DRC."""

from __future__ import annotations

import json
import logging
import uuid

import gdstk
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import backend.config as cfg
from backend.api.deps import get_pdk_registry
from backend.core.drc_runner import DRCError, DRCRunner
from backend.pcell.base import PCellGenerator, PCellResult
from backend.pcell.capacitor import MIMCapGenerator
from backend.pcell.mosfet import MOSFETGenerator
from backend.pcell.resistor import PolyResistorGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pcell", tags=["pcell"])

# ── Generator registry ─────────────────────────────────────────────────
# Maps (pdk, device_type) → generator instance.
_GENERATORS: dict[tuple[str, str], PCellGenerator] = {
    ("sky130", "nmos"): MOSFETGenerator(),
    ("sky130", "pmos"): MOSFETGenerator(),
    ("sky130", "poly_resistor"): PolyResistorGenerator(),
    ("sky130", "mim_capacitor"): MIMCapGenerator(),
}


def _get_generator(pdk: str, device_type: str) -> PCellGenerator:
    """Look up a generator, raising HTTPException on miss."""
    gen = _GENERATORS.get((pdk, device_type))
    if gen is None:
        supported = [dt for (p, dt) in _GENERATORS if p == pdk]
        if not supported:
            raise HTTPException(400, f"PDK '{pdk}' has no PCell generators")
        raise HTTPException(
            400,
            f"Unsupported device_type '{device_type}' for PDK '{pdk}'. "
            f"Supported: {supported}",
        )
    return gen


def _prepare_params(device_type: str, params: dict) -> dict:
    """Inject device_type into params for MOSFET generators."""
    params = dict(params)
    if device_type in ("nmos", "pmos"):
        params["device_type"] = device_type
    return params


class GenerateRequest(BaseModel):
    pdk: str = "sky130"
    device_type: str = "nmos"
    params: dict | None = None


# ── POST /api/pcell/generate ────────────────────────────────────────────
@router.post("/generate")
async def generate_pcell(req: GenerateRequest):
    """Generate a parameterized cell and self-validate with DRC."""
    pdk = req.pdk
    device_type = req.device_type
    params = req.params or {}

    gen = _get_generator(pdk, device_type)
    params = _prepare_params(device_type, params)

    # ── Validate parameters ─────────────────────────────────────────
    try:
        gen.validate_params(params)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # ── Generate cell ───────────────────────────────────────────────
    result: PCellResult = gen.generate(params)

    # ── Persist GDS ─────────────────────────────────────────────────
    pcell_id = uuid.uuid4().hex[:12]
    pcell_dir = cfg.PCELLS_DIR / pcell_id
    pcell_dir.mkdir(parents=True, exist_ok=True)

    gds_path = pcell_dir / f"{result.cell_name}.gds"
    lib = gdstk.Library(f"pcell_{pcell_id}")
    lib.add(result.cell)
    lib.write_gds(str(gds_path))

    # ── Self-validation DRC ─────────────────────────────────────────
    drc_clean = True
    violation_count = 0
    violations: list[dict] = []

    registry = get_pdk_registry()
    try:
        pdk_cfg = registry.load(pdk)
        runner = DRCRunner()
        drc_result = await runner.async_run(
            gds_path=gds_path,
            pdk=pdk_cfg,
            top_cell=result.cell_name,
            output_dir=pcell_dir,
        )
        drc_clean = not drc_result.has_violations
        violation_count = drc_result.report.total_violations
        violations = [
            {"category": v.category, "count": v.violation_count}
            for v in drc_result.report.violations
        ]
    except (DRCError, FileNotFoundError) as exc:
        logger.warning("PCell self-validation DRC failed: %s", exc)
        # DRC infra issue — still return the GDS but flag as unvalidated
        drc_clean = False
        violation_count = -1
        violations = [{"category": "drc_error", "count": 0, "detail": str(exc)}]

    # ── Persist metadata ────────────────────────────────────────────
    meta = {
        "pcell_id": pcell_id,
        "pdk": pdk,
        "device_type": device_type,
        "params": result.params,
        "cell_name": result.cell_name,
        "drc_clean": drc_clean,
        "violation_count": violation_count,
        "violations": violations,
        "metadata": result.metadata,
        "gds_filename": gds_path.name,
    }
    meta_path = pcell_dir / "metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    return {
        "pcell_id": pcell_id,
        "gds_url": f"/api/pcell/{pcell_id}/download",
        "drc_clean": drc_clean,
        "violation_count": violation_count,
        "violations": violations,
        "params": result.params,
        "metadata": result.metadata,
    }


# ── GET /api/pcell/devices ──────────────────────────────────────────────
# NOTE: must be registered before /{pcell_id} to avoid path conflict.
@router.get("/devices")
async def list_devices():
    """List supported devices per PDK with parameter schemas."""
    devices: dict[str, list[dict]] = {}
    for (pdk, device_type), gen in _GENERATORS.items():
        if pdk not in devices:
            devices[pdk] = []
        devices[pdk].append(
            {
                "device_type": device_type,
                "param_schema": gen.param_schema(),
            }
        )
    return {"devices": devices}


# ── GET /api/pcell/{pcell_id}/download ──────────────────────────────────
@router.get("/{pcell_id}/download")
async def download_pcell(pcell_id: str):
    """Download the generated GDS file for a PCell."""
    pcell_dir = cfg.PCELLS_DIR / pcell_id
    meta_path = pcell_dir / "metadata.json"

    if not meta_path.exists():
        raise HTTPException(404, f"PCell '{pcell_id}' not found")

    meta = json.loads(meta_path.read_text())
    gds_path = pcell_dir / meta["gds_filename"]

    if not gds_path.exists():
        raise HTTPException(404, "GDS file not found on disk")

    return FileResponse(
        path=str(gds_path),
        media_type="application/octet-stream",
        filename=meta["gds_filename"],
    )

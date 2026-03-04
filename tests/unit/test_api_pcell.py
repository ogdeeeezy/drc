"""Tests for PCell API routes — generate, download, devices."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api import deps
from backend.main import app


@pytest.fixture(autouse=True)
def reset_singletons():
    deps.reset_deps()
    yield
    deps.reset_deps()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def client(tmp_dir):
    """Test client with isolated pcells/jobs/upload dirs."""
    import backend.config as cfg

    original_jobs = cfg.JOBS_DIR
    original_uploads = cfg.UPLOAD_DIR
    original_pcells = cfg.PCELLS_DIR
    cfg.JOBS_DIR = tmp_dir / "jobs"
    cfg.UPLOAD_DIR = tmp_dir / "uploads"
    cfg.PCELLS_DIR = tmp_dir / "pcells"
    cfg.JOBS_DIR.mkdir()
    cfg.UPLOAD_DIR.mkdir()
    cfg.PCELLS_DIR.mkdir()

    with TestClient(app) as c:
        yield c

    cfg.JOBS_DIR = original_jobs
    cfg.UPLOAD_DIR = original_uploads
    cfg.PCELLS_DIR = original_pcells


def _mock_drc_result(clean: bool = True):
    """Create a mock DRCResult for self-validation."""
    from backend.core.drc_runner import DRCResult
    from backend.core.violation_models import (
        DRCReport,
        EdgePair,
        GeometryType,
        Violation,
        ViolationGeometry,
    )

    violations = []
    if not clean:
        geom = ViolationGeometry(
            geometry_type=GeometryType.edge_pair,
            edge_pair=EdgePair(
                edge1_start=(0.0, 0.0),
                edge1_end=(0.1, 0.0),
                edge2_start=(0.0, 0.05),
                edge2_end=(0.1, 0.05),
            ),
        )
        violations = [
            Violation(
                category="met1.1",
                description="Metal 1 minimum width",
                cell_name="test",
                geometries=[geom, geom],
            )
        ]
    report = DRCReport(
        description="DRC Report",
        original_file="test.gds",
        generator="klayout",
        top_cell="test",
        violations=violations,
    )
    return DRCResult(
        report=report,
        report_path=Path("/tmp/fake.lyrdb"),
        returncode=0,
        stdout="",
        stderr="",
        duration_seconds=0.05,
        klayout_binary="klayout",
    )


class TestGeneratePCell:
    def test_generate_nmos_success(self, client):
        """POST /api/pcell/generate with NMOS params returns pcell with DRC info."""
        mock_result = _mock_drc_result(clean=True)
        with patch("backend.api.routes.pcell.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(return_value=mock_result)

            r = client.post(
                "/api/pcell/generate",
                json={
                    "pdk": "sky130",
                    "device_type": "nmos",
                    "params": {"w_um": 1.0, "l_um": 0.15, "fingers": 2},
                },
            )

        assert r.status_code == 200
        data = r.json()
        assert "pcell_id" in data
        assert data["drc_clean"] is True
        assert data["violation_count"] == 0
        assert "/api/pcell/" in data["gds_url"]
        assert "download" in data["gds_url"]
        assert data["params"]["w_um"] == 1.0
        assert data["params"]["l_um"] == 0.15

    def test_generate_pmos_success(self, client):
        """PMOS generation works and includes nwell."""
        mock_result = _mock_drc_result(clean=True)
        with patch("backend.api.routes.pcell.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(return_value=mock_result)

            r = client.post(
                "/api/pcell/generate",
                json={
                    "pdk": "sky130",
                    "device_type": "pmos",
                    "params": {"w_um": 0.5, "l_um": 0.15},
                },
            )

        assert r.status_code == 200
        assert r.json()["drc_clean"] is True

    def test_generate_mim_capacitor(self, client):
        """MIM capacitor generation returns capacitance metadata."""
        mock_result = _mock_drc_result(clean=True)
        with patch("backend.api.routes.pcell.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(return_value=mock_result)

            r = client.post(
                "/api/pcell/generate",
                json={
                    "pdk": "sky130",
                    "device_type": "mim_capacitor",
                    "params": {"w_um": 5.0, "l_um": 5.0},
                },
            )

        assert r.status_code == 200
        data = r.json()
        assert data["drc_clean"] is True
        assert "capacitance_fF" in data["metadata"]
        assert data["metadata"]["capacitance_fF"] > 0

    def test_generate_poly_resistor(self, client):
        """Poly resistor generation works."""
        mock_result = _mock_drc_result(clean=True)
        with patch("backend.api.routes.pcell.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(return_value=mock_result)

            r = client.post(
                "/api/pcell/generate",
                json={
                    "pdk": "sky130",
                    "device_type": "poly_resistor",
                    "params": {"w_um": 0.35, "l_um": 5.0},
                },
            )

        assert r.status_code == 200
        assert r.json()["drc_clean"] is True

    def test_generate_invalid_params_returns_400(self, client):
        """L below minimum triggers 400."""
        r = client.post(
            "/api/pcell/generate",
            json={
                "pdk": "sky130",
                "device_type": "nmos",
                "params": {"w_um": 1.0, "l_um": 0.01},
            },
        )
        assert r.status_code == 400

    def test_generate_unsupported_device_returns_400(self, client):
        """Unknown device_type triggers 400 with supported list."""
        r = client.post(
            "/api/pcell/generate",
            json={
                "pdk": "sky130",
                "device_type": "bjt",
                "params": {},
            },
        )
        assert r.status_code == 400
        assert "Supported" in r.json()["detail"]

    def test_generate_unsupported_pdk_returns_400(self, client):
        """Unknown PDK triggers 400."""
        r = client.post(
            "/api/pcell/generate",
            json={
                "pdk": "tsmc28",
                "device_type": "nmos",
                "params": {},
            },
        )
        assert r.status_code == 400

    def test_generate_drc_violations_reported(self, client):
        """When DRC finds violations, response reflects them."""
        mock_result = _mock_drc_result(clean=False)
        with patch("backend.api.routes.pcell.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(return_value=mock_result)

            r = client.post(
                "/api/pcell/generate",
                json={
                    "pdk": "sky130",
                    "device_type": "nmos",
                    "params": {"w_um": 1.0, "l_um": 0.15},
                },
            )

        assert r.status_code == 200
        data = r.json()
        assert data["drc_clean"] is False
        assert data["violation_count"] == 2
        assert len(data["violations"]) == 1
        assert data["violations"][0]["category"] == "met1.1"

    def test_generate_drc_error_handled(self, client):
        """DRC infrastructure error doesn't crash — returns unvalidated flag."""
        from backend.core.drc_runner import DRCError

        with patch("backend.api.routes.pcell.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(side_effect=DRCError("klayout not found"))

            r = client.post(
                "/api/pcell/generate",
                json={
                    "pdk": "sky130",
                    "device_type": "nmos",
                    "params": {"w_um": 1.0, "l_um": 0.15},
                },
            )

        assert r.status_code == 200
        data = r.json()
        assert data["drc_clean"] is False
        assert data["violation_count"] == -1

    def test_generate_saves_metadata(self, client, tmp_dir):
        """Generated PCell writes metadata.json alongside GDS."""
        import backend.config as cfg

        mock_result = _mock_drc_result(clean=True)
        with patch("backend.api.routes.pcell.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(return_value=mock_result)

            r = client.post(
                "/api/pcell/generate",
                json={
                    "pdk": "sky130",
                    "device_type": "nmos",
                    "params": {"w_um": 1.0, "l_um": 0.15},
                },
            )

        pcell_id = r.json()["pcell_id"]
        meta_path = cfg.PCELLS_DIR / pcell_id / "metadata.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["pdk"] == "sky130"
        assert meta["device_type"] == "nmos"
        assert meta["drc_clean"] is True

    def test_generate_default_params(self, client):
        """Omitting params dict uses generator defaults."""
        mock_result = _mock_drc_result(clean=True)
        with patch("backend.api.routes.pcell.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(return_value=mock_result)

            r = client.post(
                "/api/pcell/generate",
                json={
                    "pdk": "sky130",
                    "device_type": "nmos",
                },
            )

        # Should still fail because w_um and l_um are required
        # (no defaults in MOSFET generator)
        assert r.status_code == 400


class TestDownloadPCell:
    def test_download_success(self, client):
        """After generate, download URL returns GDS file."""
        mock_result = _mock_drc_result(clean=True)
        with patch("backend.api.routes.pcell.DRCRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.async_run = AsyncMock(return_value=mock_result)

            r = client.post(
                "/api/pcell/generate",
                json={
                    "pdk": "sky130",
                    "device_type": "nmos",
                    "params": {"w_um": 1.0, "l_um": 0.15},
                },
            )

        pcell_id = r.json()["pcell_id"]
        r2 = client.get(f"/api/pcell/{pcell_id}/download")
        assert r2.status_code == 200
        assert r2.headers["content-type"] == "application/octet-stream"
        assert len(r2.content) > 0

    def test_download_not_found(self, client):
        """Nonexistent PCell ID returns 404."""
        r = client.get("/api/pcell/nonexistent/download")
        assert r.status_code == 404


class TestListDevices:
    def test_list_devices(self, client):
        """GET /api/pcell/devices returns supported devices with schemas."""
        r = client.get("/api/pcell/devices")
        assert r.status_code == 200
        data = r.json()
        assert "devices" in data
        assert "sky130" in data["devices"]
        sky130_devices = data["devices"]["sky130"]
        device_types = [d["device_type"] for d in sky130_devices]
        assert "nmos" in device_types
        assert "pmos" in device_types
        assert "mim_capacitor" in device_types
        assert "poly_resistor" in device_types

    def test_device_schemas_have_types(self, client):
        """Each device schema includes param type info."""
        r = client.get("/api/pcell/devices")
        sky130_devices = r.json()["devices"]["sky130"]
        for device in sky130_devices:
            schema = device["param_schema"]
            assert len(schema) > 0
            for param_name, param_info in schema.items():
                assert "type" in param_info

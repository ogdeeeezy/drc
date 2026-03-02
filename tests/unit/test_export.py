"""Tests for report export (JSON, CSV, HTML) and GDSII versioned export."""

import json
import tempfile
from pathlib import Path

import gdstk
import pytest

from backend.core.violation_models import (
    DRCReport,
    EdgePair,
    GeometryType,
    Violation,
    ViolationGeometry,
)
from backend.export.gdsii import export_fixed_gds, list_fixed_versions
from backend.export.report import export_csv, export_html, export_json
from backend.jobs.manager import Job, JobStatus


@pytest.fixture
def sample_job():
    return Job(
        job_id="abc123",
        filename="inverter.gds",
        pdk_name="sky130",
        status=JobStatus.drc_complete,
        total_violations=3,
        iteration=2,
    )


@pytest.fixture
def sample_report():
    return DRCReport(
        description="DRC Report",
        original_file="inverter.gds",
        generator="klayout",
        top_cell="INV",
        violations=[
            Violation(
                category="met1.1",
                description="Metal 1 minimum width",
                cell_name="INV",
                rule_id="m1.1",
                rule_type="min_width",
                severity=8,
                value_um=0.14,
                geometries=[
                    ViolationGeometry(
                        geometry_type=GeometryType.edge_pair,
                        edge_pair=EdgePair(
                            edge1_start=(0.0, 0.0),
                            edge1_end=(0.1, 0.0),
                            edge2_start=(0.0, 0.05),
                            edge2_end=(0.1, 0.05),
                        ),
                    ),
                ],
            ),
            Violation(
                category="met1.2",
                description="Metal 1 minimum spacing",
                cell_name="INV",
                rule_id="m1.2",
                rule_type="min_spacing",
                severity=7,
                value_um=0.14,
                geometries=[
                    ViolationGeometry(
                        geometry_type=GeometryType.edge_pair,
                        edge_pair=EdgePair(
                            edge1_start=(1.0, 0.0),
                            edge1_end=(1.1, 0.0),
                            edge2_start=(1.0, 0.1),
                            edge2_end=(1.1, 0.1),
                        ),
                    ),
                    ViolationGeometry(
                        geometry_type=GeometryType.edge_pair,
                        edge_pair=EdgePair(
                            edge1_start=(2.0, 0.0),
                            edge1_end=(2.1, 0.0),
                            edge2_start=(2.0, 0.1),
                            edge2_end=(2.1, 0.1),
                        ),
                    ),
                ],
            ),
        ],
    )


class TestExportJSON:
    def test_valid_json(self, sample_job, sample_report):
        result = export_json(sample_job, sample_report)
        data = json.loads(result)
        assert data["report"]["job_id"] == "abc123"
        assert data["report"]["iteration"] == 2
        assert data["report"]["total_violations"] == 3
        assert len(data["violations"]) == 2

    def test_violation_fields(self, sample_job, sample_report):
        data = json.loads(export_json(sample_job, sample_report))
        v = data["violations"][0]
        assert v["category"] == "met1.1"
        assert v["rule_type"] == "min_width"
        assert v["severity"] == 8
        assert v["count"] == 1
        assert len(v["bbox"]) == 4


class TestExportCSV:
    def test_header_and_rows(self, sample_job, sample_report):
        result = export_csv(sample_job, sample_report)
        lines = result.strip().split("\n")
        assert len(lines) == 3  # header + 2 violations
        assert "category" in lines[0]
        assert "met1.1" in lines[1]

    def test_csv_parseable(self, sample_job, sample_report):
        import csv
        import io

        result = export_csv(sample_job, sample_report)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["category"] == "met1.1"
        assert rows[1]["count"] == "2"


class TestExportHTML:
    def test_contains_structure(self, sample_job, sample_report):
        html = export_html(sample_job, sample_report)
        assert "<!DOCTYPE html>" in html
        assert "DRC Report" in html
        assert "inverter.gds" in html
        assert "sky130" in html
        assert "met1.1" in html

    def test_severity_colors(self, sample_job, sample_report):
        html = export_html(sample_job, sample_report)
        assert "#e63946" in html  # severity 8 = red

    def test_html_escaping(self):
        job = Job(
            job_id="x",
            filename="<script>alert(1)</script>.gds",
            pdk_name="sky130",
            iteration=1,
        )
        report = DRCReport(
            description="test",
            original_file="test.gds",
            generator="klayout",
            top_cell="TOP",
        )
        html = export_html(job, report)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestGDSIIExport:
    def test_export_iteration_1(self):
        with tempfile.TemporaryDirectory() as d:
            job_dir = Path(d)
            from backend.core.layout import LayoutManager

            mgr = LayoutManager()
            mgr.new_library("test")
            lib = mgr.library
            cell = gdstk.Cell("TOP")
            cell.add(gdstk.rectangle((0, 0), (1, 1), layer=68, datatype=20))
            lib.add(cell)

            path = export_fixed_gds(mgr, job_dir, "inverter", iteration=1)
            assert path.name == "inverter_fixed.gds"
            assert path.exists()

    def test_export_iteration_n(self):
        with tempfile.TemporaryDirectory() as d:
            job_dir = Path(d)
            from backend.core.layout import LayoutManager

            mgr = LayoutManager()
            mgr.new_library("test")
            lib = mgr.library
            cell = gdstk.Cell("TOP")
            cell.add(gdstk.rectangle((0, 0), (1, 1), layer=68, datatype=20))
            lib.add(cell)

            path = export_fixed_gds(mgr, job_dir, "inverter", iteration=3)
            assert path.name == "inverter_fixed_v3.gds"
            assert path.exists()

    def test_list_versions(self):
        with tempfile.TemporaryDirectory() as d:
            job_dir = Path(d)
            (job_dir / "inverter_fixed.gds").touch()
            (job_dir / "inverter_fixed_v2.gds").touch()
            (job_dir / "inverter_fixed_v3.gds").touch()
            (job_dir / "other.gds").touch()

            versions = list_fixed_versions(job_dir, "inverter")
            assert len(versions) == 3

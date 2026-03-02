"""Tests for .lyrdb violation parser."""

from pathlib import Path

import pytest

from backend.core.violation_models import GeometryType
from backend.core.violation_parser import (
    ViolationParser,
    _clean_category_ref,
    _parse_coord_pair,
    _parse_edge,
    _parse_polygon_points,
    _parse_value,
)
from backend.pdk.schema import DesignRule, PDKConfig, GDSLayer, RuleType, FixStrategyWeight

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "lyrdb"


class TestCoordinateParsing:
    def test_parse_coord_pair(self):
        assert _parse_coord_pair("1.5,2.3") == (1.5, 2.3)

    def test_parse_coord_pair_negative(self):
        assert _parse_coord_pair("-1.0,-2.5") == (-1.0, -2.5)

    def test_parse_coord_pair_integer(self):
        assert _parse_coord_pair("0,0") == (0.0, 0.0)

    def test_parse_edge(self):
        start, end = _parse_edge("(1.0,2.0;3.0,4.0)")
        assert start == (1.0, 2.0)
        assert end == (3.0, 4.0)

    def test_parse_edge_no_parens(self):
        start, end = _parse_edge("1.0,2.0;3.0,4.0")
        assert start == (1.0, 2.0)
        assert end == (3.0, 4.0)

    def test_parse_polygon_points(self):
        pts = _parse_polygon_points("(0,0;1,0;1,1;0,1)")
        assert pts == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]

    def test_parse_polygon_with_hole(self):
        # Hole should be ignored (after /)
        pts = _parse_polygon_points("(0,0;10,0;10,10;0,10/2,2;8,2;8,8;2,8)")
        assert len(pts) == 4
        assert pts[0] == (0.0, 0.0)


class TestValueParsing:
    def test_edge_pair(self):
        geom = _parse_value("edge-pair: (1.0,2.0;1.0,2.5)/(1.1,2.0;1.1,2.5)")
        assert geom is not None
        assert geom.geometry_type == GeometryType.edge_pair
        assert geom.edge_pair is not None
        assert geom.edge_pair.edge1_start == (1.0, 2.0)
        assert geom.edge_pair.edge1_end == (1.0, 2.5)
        assert geom.edge_pair.edge2_start == (1.1, 2.0)
        assert geom.edge_pair.edge2_end == (1.1, 2.5)

    def test_polygon(self):
        geom = _parse_value("polygon: (5.0,5.0;5.2,5.0;5.2,5.1;5.0,5.1)")
        assert geom is not None
        assert geom.geometry_type == GeometryType.polygon
        assert geom.points == [
            (5.0, 5.0), (5.2, 5.0), (5.2, 5.1), (5.0, 5.1)
        ]

    def test_edge(self):
        geom = _parse_value("edge: (0.0,0.0;1.0,1.0)")
        assert geom is not None
        assert geom.geometry_type == GeometryType.edge
        assert geom.edge_pair is not None
        assert geom.edge_pair.edge1_start == (0.0, 0.0)
        assert geom.edge_pair.edge1_end == (1.0, 1.0)

    def test_box(self):
        geom = _parse_value("box: (0.0,0.0;1.0,1.0)")
        assert geom is not None
        assert geom.geometry_type == GeometryType.box
        assert geom.points is not None
        assert len(geom.points) == 4
        assert (0.0, 0.0) in geom.points
        assert (1.0, 1.0) in geom.points

    def test_text_returns_none(self):
        geom = _parse_value("text: some message")
        assert geom is None

    def test_unknown_returns_none(self):
        geom = _parse_value("unknown: data")
        assert geom is None


class TestCategoryRefCleaning:
    def test_quoted_ref(self):
        assert _clean_category_ref("'m1.1'") == "m1.1"

    def test_double_quoted_ref(self):
        assert _clean_category_ref('"m1.1"') == "m1.1"

    def test_unquoted_ref(self):
        assert _clean_category_ref("m1.1") == "m1.1"

    def test_nested_quoted(self):
        assert _clean_category_ref("'parent'.'child'") == "parent.child"

    def test_whitespace(self):
        assert _clean_category_ref("  'm1.1'  ") == "m1.1"


class TestViolationParserFiles:
    def setup_method(self):
        self.parser = ViolationParser()

    def test_parse_sky130_inv(self):
        report = self.parser.parse_file(FIXTURES_DIR / "sky130_inv_violations.lyrdb")
        assert report.description == "DRC Results for sky130 inverter"
        assert report.top_cell == "INV"
        assert report.original_file == "/tmp/test/inv.gds"
        assert "klayout" in report.generator

    def test_sky130_inv_violation_count(self):
        report = self.parser.parse_file(FIXTURES_DIR / "sky130_inv_violations.lyrdb")
        assert report.total_violations == 6
        # 5 categories: m1.1 (2 violations), m1.2 (1), poly.1a (1), via.4a (1), m1.6 (1)
        assert len(report.violations) == 5

    def test_sky130_inv_categories(self):
        report = self.parser.parse_file(FIXTURES_DIR / "sky130_inv_violations.lyrdb")
        cats = sorted(report.categories)
        assert cats == ["m1.1", "m1.2", "m1.6", "poly.1a", "via.4a"]

    def test_sky130_inv_m1_width(self):
        report = self.parser.parse_file(FIXTURES_DIR / "sky130_inv_violations.lyrdb")
        v = report.get_violations_by_category("m1.1")
        assert v is not None
        assert v.violation_count == 2
        assert v.description == "met1 minimum width: 0.14um"
        assert v.cell_name == "INV"

    def test_sky130_inv_polygon_violation(self):
        report = self.parser.parse_file(FIXTURES_DIR / "sky130_inv_violations.lyrdb")
        v = report.get_violations_by_category("m1.6")
        assert v is not None
        assert v.violation_count == 1
        geom = v.geometries[0]
        assert geom.geometry_type == GeometryType.polygon
        assert geom.points is not None
        assert len(geom.points) == 4

    def test_sky130_inv_edge_pair_geometry(self):
        report = self.parser.parse_file(FIXTURES_DIR / "sky130_inv_violations.lyrdb")
        v = report.get_violations_by_category("m1.1")
        assert v is not None
        geom = v.geometries[0]
        assert geom.geometry_type == GeometryType.edge_pair
        assert geom.edge_pair is not None
        assert geom.edge_pair.edge1_start == (1.0, 2.0)

    def test_empty_report(self):
        report = self.parser.parse_file(FIXTURES_DIR / "empty_report.lyrdb")
        assert report.total_violations == 0
        assert report.violations == []
        assert report.top_cell == "TOP"

    def test_multi_cell(self):
        report = self.parser.parse_file(FIXTURES_DIR / "multi_cell.lyrdb")
        # m1.1 in TOP and m1.1 in SUBCELL_A should be separate violations
        assert len(report.violations) == 3
        top_violations = report.get_violations_for_cell("TOP")
        assert len(top_violations) == 2
        sub_violations = report.get_violations_for_cell("SUBCELL_A")
        assert len(sub_violations) == 1

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            self.parser.parse_file("/nonexistent/path.lyrdb")


class TestViolationParserString:
    def setup_method(self):
        self.parser = ViolationParser()

    def test_minimal_xml(self):
        xml = """<?xml version="1.0" ?>
        <report-database>
          <description>test</description>
          <original-file>test.gds</original-file>
          <generator>test</generator>
          <top-cell>TOP</top-cell>
          <categories>
            <category>
              <name>rule1</name>
              <description>A test rule</description>
            </category>
          </categories>
          <cells/>
          <items>
            <item>
              <category>'rule1'</category>
              <cell>TOP</cell>
              <values>
                <value>edge-pair: (0,0;0,1)/(0.5,0;0.5,1)</value>
              </values>
            </item>
          </items>
        </report-database>"""
        report = self.parser.parse_string(xml)
        assert report.total_violations == 1
        v = report.violations[0]
        assert v.category == "rule1"
        assert v.description == "A test rule"

    def test_item_without_values(self):
        xml = """<?xml version="1.0" ?>
        <report-database>
          <description>test</description>
          <original-file/>
          <generator/>
          <top-cell>TOP</top-cell>
          <categories>
            <category>
              <name>r1</name>
              <description>rule 1</description>
            </category>
          </categories>
          <cells/>
          <items>
            <item>
              <category>'r1'</category>
              <cell>TOP</cell>
            </item>
          </items>
        </report-database>"""
        report = self.parser.parse_string(xml)
        assert len(report.violations) == 1
        assert report.violations[0].violation_count == 0

    def test_nested_categories(self):
        xml = """<?xml version="1.0" ?>
        <report-database>
          <description>test</description>
          <original-file/>
          <generator/>
          <top-cell>TOP</top-cell>
          <categories>
            <category>
              <name>metal</name>
              <description>Metal rules</description>
              <categories>
                <category>
                  <name>width</name>
                  <description>Width rules</description>
                </category>
              </categories>
            </category>
          </categories>
          <cells/>
          <items>
            <item>
              <category>'metal.width'</category>
              <cell>TOP</cell>
              <values>
                <value>edge-pair: (0,0;0,1)/(0.1,0;0.1,1)</value>
              </values>
            </item>
          </items>
        </report-database>"""
        report = self.parser.parse_string(xml)
        assert len(report.violations) == 1
        assert report.violations[0].category == "metal.width"


class TestPDKMapping:
    def setup_method(self):
        self.parser = ViolationParser()
        self.pdk = PDKConfig(
            name="test",
            version="1.0",
            process_node_nm=130,
            grid_um=0.005,
            layers={
                "met1": GDSLayer(
                    gds_layer=68, gds_datatype=20, description="Metal 1",
                    color="#0000FF", is_routing=True,
                ),
            },
            rules=[
                DesignRule(
                    rule_id="m1.1", rule_type=RuleType.min_width,
                    layer="met1", value_um=0.140, severity=7,
                ),
                DesignRule(
                    rule_id="m1.2", rule_type=RuleType.min_spacing,
                    layer="met1", value_um=0.140, severity=6,
                ),
            ],
            connectivity=[],
            fix_weights={},
            klayout_drc_deck="test.drc",
        )

    def test_map_known_rules(self):
        report = self.parser.parse_file(FIXTURES_DIR / "sky130_inv_violations.lyrdb")
        self.parser.map_to_pdk(report, self.pdk)
        v = report.get_violations_by_category("m1.1")
        assert v is not None
        assert v.rule_id == "m1.1"
        assert v.rule_type == "min_width"
        assert v.severity == 7
        assert v.value_um == 0.140

    def test_map_unknown_rule_unchanged(self):
        report = self.parser.parse_file(FIXTURES_DIR / "sky130_inv_violations.lyrdb")
        self.parser.map_to_pdk(report, self.pdk)
        v = report.get_violations_by_category("poly.1a")
        assert v is not None
        # poly.1a not in our minimal PDK → defaults
        assert v.rule_id is None
        assert v.severity == 5

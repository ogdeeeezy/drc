"""Parse KLayout .lyrdb (RDB) XML files into structured Violation objects."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from backend.core.violation_models import (
    DRCReport,
    EdgePair,
    GeometryType,
    Violation,
    ViolationGeometry,
)
from backend.pdk.schema import PDKConfig


def _text(elem: ET.Element | None) -> str:
    """Safely extract text from an XML element."""
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _parse_coord_pair(s: str) -> tuple[float, float]:
    """Parse 'x,y' into (float, float)."""
    parts = s.strip().split(",")
    return (float(parts[0]), float(parts[1]))


def _parse_edge(s: str) -> tuple[tuple[float, float], tuple[float, float]]:
    """Parse '(x1,y1;x2,y2)' into two points."""
    s = s.strip().strip("()")
    points = s.split(";")
    return (_parse_coord_pair(points[0]), _parse_coord_pair(points[1]))


def _parse_polygon_points(s: str) -> list[tuple[float, float]]:
    """Parse '(x1,y1;x2,y2;...)' into list of points. Ignores holes (after '/')."""
    s = s.strip().strip("()")
    # Take only the outer ring (before any '/' for holes)
    outer = s.split("/")[0]
    return [_parse_coord_pair(p) for p in outer.split(";") if p.strip()]


def _parse_value(value_str: str) -> ViolationGeometry | None:
    """Parse a <value> string into a ViolationGeometry.

    Formats:
        edge-pair: (x1,y1;x2,y2)/(x3,y3;x4,y4)
        polygon: (x1,y1;x2,y2;...)
        edge: (x1,y1;x2,y2)
        box: (x1,y1;x2,y2)
        text: message
    """
    value_str = value_str.strip()

    if value_str.startswith("edge-pair:"):
        content = value_str[len("edge-pair:") :].strip()
        # Split on '/' to get two edges: (x1,y1;x2,y2)/(x3,y3;x4,y4)
        # Each edge is in parentheses
        halves = re.split(r"\)\s*/\s*\(", content)
        if len(halves) != 2:
            return None
        edge1 = _parse_edge(halves[0])
        edge2 = _parse_edge(halves[1])
        return ViolationGeometry(
            geometry_type=GeometryType.edge_pair,
            edge_pair=EdgePair(
                edge1_start=edge1[0],
                edge1_end=edge1[1],
                edge2_start=edge2[0],
                edge2_end=edge2[1],
            ),
        )

    if value_str.startswith("polygon:"):
        content = value_str[len("polygon:") :].strip()
        points = _parse_polygon_points(content)
        return ViolationGeometry(
            geometry_type=GeometryType.polygon,
            points=points,
        )

    if value_str.startswith("edge:"):
        content = value_str[len("edge:") :].strip()
        start, end = _parse_edge(content)
        return ViolationGeometry(
            geometry_type=GeometryType.edge,
            edge_pair=EdgePair(
                edge1_start=start,
                edge1_end=end,
                edge2_start=start,
                edge2_end=end,
            ),
        )

    if value_str.startswith("box:"):
        content = value_str[len("box:") :].strip()
        content = content.strip("()")
        corners = content.split(";")
        p1 = _parse_coord_pair(corners[0])
        p2 = _parse_coord_pair(corners[1])
        points = [
            p1,
            (p2[0], p1[1]),
            p2,
            (p1[0], p2[1]),
        ]
        return ViolationGeometry(
            geometry_type=GeometryType.box,
            points=points,
        )

    # text: or unknown → skip
    return None


def _parse_categories(categories_elem: ET.Element, prefix: str = "") -> dict[str, str]:
    """Recursively parse category tree into {name: description} mapping."""
    result: dict[str, str] = {}
    for cat in categories_elem.findall("category"):
        name = _text(cat.find("name"))
        desc = _text(cat.find("description"))
        full_name = f"{prefix}{name}" if not prefix else f"{prefix}.{name}"
        if not prefix:
            full_name = name
        result[full_name] = desc
        # Recurse into sub-categories
        sub_cats = cat.find("categories")
        if sub_cats is not None:
            result.update(_parse_categories(sub_cats, prefix=full_name))
    return result


def _clean_category_ref(ref: str) -> str:
    """Clean a category reference from an item.

    Items reference categories like 'met1.1' (with quotes) or met1.1 (without).
    Nested refs use dot notation: 'parent'.'child'
    """
    # Remove surrounding quotes
    ref = ref.strip().strip("'\"")
    # Handle dot-separated quoted segments: 'parent'.'child' → parent.child
    ref = re.sub(r"['\"]\.?['\"]", ".", ref)
    ref = ref.strip("'\"")
    return ref


class ViolationParser:
    """Parse KLayout .lyrdb report database XML into structured violations."""

    def parse_file(self, lyrdb_path: str | Path) -> DRCReport:
        """Parse a .lyrdb file from disk."""
        path = Path(lyrdb_path)
        if not path.exists():
            raise FileNotFoundError(f"Report file not found: {path}")
        tree = ET.parse(path)
        return self._parse_tree(tree.getroot())

    def parse_string(self, xml_content: str) -> DRCReport:
        """Parse .lyrdb XML from a string."""
        root = ET.fromstring(xml_content)
        return self._parse_tree(root)

    def _parse_tree(self, root: ET.Element) -> DRCReport:
        """Parse the XML tree into a DRCReport."""
        description = _text(root.find("description"))
        original_file = _text(root.find("original-file"))
        generator = _text(root.find("generator"))
        top_cell = _text(root.find("top-cell"))

        # Parse category definitions
        categories: dict[str, str] = {}
        cats_elem = root.find("categories")
        if cats_elem is not None:
            categories = _parse_categories(cats_elem)

        # Parse items, grouped by category
        violations_by_cat: dict[str, Violation] = {}
        items_elem = root.find("items")
        if items_elem is not None:
            for item in items_elem.findall("item"):
                cat_ref = _clean_category_ref(_text(item.find("category")))
                cell_ref = _text(item.find("cell"))
                # Cell ref can be "CELLNAME" or "CELLNAME:variant"
                cell_name = cell_ref.split(":")[0] if cell_ref else top_cell

                # Parse geometry values
                values_elem = item.find("values")
                geoms: list[ViolationGeometry] = []
                if values_elem is not None:
                    for val in values_elem.findall("value"):
                        if val.text:
                            geom = _parse_value(val.text)
                            if geom is not None:
                                geoms.append(geom)

                # Get or create violation for this category
                key = f"{cat_ref}:{cell_name}"
                if key not in violations_by_cat:
                    violations_by_cat[key] = Violation(
                        category=cat_ref,
                        description=categories.get(cat_ref, ""),
                        cell_name=cell_name,
                    )
                violations_by_cat[key].geometries.extend(geoms)

        return DRCReport(
            description=description,
            original_file=original_file,
            generator=generator,
            top_cell=top_cell,
            violations=list(violations_by_cat.values()),
        )

    def map_to_pdk(self, report: DRCReport, pdk: PDKConfig) -> DRCReport:
        """Enrich violations with PDK rule metadata.

        Maps violation categories to PDK rule IDs and populates
        rule_type, severity, and value_um fields.
        """
        for violation in report.violations:
            rule = pdk.get_rule(violation.category)
            if rule is not None:
                violation.rule_id = rule.rule_id
                violation.rule_type = rule.rule_type.value
                violation.severity = rule.severity
                violation.value_um = rule.value_um
            else:
                # Try matching by partial category name
                # DRC decks sometimes use "layer.rule_number" format
                for pdk_rule in pdk.rules:
                    cat = violation.category
                    if pdk_rule.rule_id in cat or cat in pdk_rule.rule_id:
                        violation.rule_id = pdk_rule.rule_id
                        violation.rule_type = pdk_rule.rule_type.value
                        violation.severity = pdk_rule.severity
                        violation.value_um = pdk_rule.value_um
                        break
        return report

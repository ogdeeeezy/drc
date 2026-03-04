"""Tests for .lvsdb LVS report parser."""

from pathlib import Path

import pytest

from backend.core.lvs_models import LVSMismatchType, LVSReport
from backend.core.lvs_parser import (
    LVSDB_HEADER,
    LVSParseError,
    LVSReportParser,
    _find_block,
    _iter_blocks,
    _parse_id,
    _tokenize,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "lvsdb"


# ---------------------------------------------------------------------------
# Tokenizer tests
# ---------------------------------------------------------------------------


class TestTokenizer:
    def test_simple_tokens(self):
        tokens = _tokenize("layout( top(INVERTER) )")
        assert tokens == ["layout", "(", "top", "(", "INVERTER", ")", ")"]

    def test_comments_stripped(self):
        tokens = _tokenize("# comment\nlayout(\n# another\n)")
        assert tokens == ["layout", "(", ")"]

    def test_quoted_string(self):
        tokens = _tokenize("layer(l3 'NWELL (1/0)')")
        assert tokens == ["layer", "(", "l3", "NWELL (1/0)", ")"]

    def test_double_quoted_string(self):
        tokens = _tokenize('description("parameter mismatch")')
        assert tokens == ["description", "(", "parameter mismatch", ")"]

    def test_escaped_chars_in_quotes(self):
        tokens = _tokenize("name('it\\'s')")
        assert tokens == ["name", "(", "it's", ")"]

    def test_comma_separator(self):
        tokens = _tokenize("connect(l3, l3)")
        assert tokens == ["connect", "(", "l3", "l3", ")"]

    def test_empty_parens(self):
        tokens = _tokenize("device(() 3 nomatch)")
        assert tokens == ["device", "(", "(", ")", "3", "nomatch", ")"]

    def test_numbers(self):
        tokens = _tokenize("param(L 0.25)")
        assert tokens == ["param", "(", "L", "0.25", ")"]


# ---------------------------------------------------------------------------
# Block helper tests
# ---------------------------------------------------------------------------


class TestBlockHelpers:
    def test_find_block(self):
        tokens = _tokenize("xref( net(1 2 match) )")
        result = _find_block(tokens, "xref")
        assert result is not None
        start, end = result
        # Content should contain net(1 2 match)
        content = tokens[start:end]
        assert "net" in content

    def test_find_block_not_found(self):
        tokens = _tokenize("layout( )")
        result = _find_block(tokens, "xref")
        assert result is None

    def test_iter_blocks(self):
        tokens = _tokenize("xref( net(1 2 match) net(3 4 match) )")
        xref = _find_block(tokens, "xref")
        assert xref is not None
        blocks = list(_iter_blocks(tokens, "net", *xref))
        assert len(blocks) == 2

    def test_parse_id_number(self):
        tokens = ["3", "match"]
        val, pos = _parse_id(tokens, 0)
        assert val == "3"
        assert pos == 1

    def test_parse_id_empty(self):
        tokens = ["(", ")", "3", "nomatch"]
        val, pos = _parse_id(tokens, 0)
        assert val is None
        assert pos == 2


# ---------------------------------------------------------------------------
# Clean report parsing
# ---------------------------------------------------------------------------


class TestCleanReport:
    def test_parse_file(self):
        parser = LVSReportParser()
        report = parser.parse_file(FIXTURES_DIR / "clean_inverter.lvsdb")

        assert report.match is True
        assert report.devices_matched == 2
        assert report.devices_mismatched == 0
        assert report.nets_matched == 4
        assert report.nets_mismatched == 0
        assert report.mismatches == []

    def test_parse_string(self):
        parser = LVSReportParser()
        content = (FIXTURES_DIR / "clean_inverter.lvsdb").read_text()
        report = parser.parse_string(content)

        assert report.match is True
        assert report.mismatches == []


# ---------------------------------------------------------------------------
# Mismatched report parsing
# ---------------------------------------------------------------------------


class TestMismatchedReport:
    @pytest.fixture()
    def report(self) -> LVSReport:
        parser = LVSReportParser()
        return parser.parse_file(FIXTURES_DIR / "mismatched_inverter.lvsdb")

    def test_overall_nomatch(self, report: LVSReport):
        assert report.match is False

    def test_device_counts(self, report: LVSReport):
        assert report.devices_matched == 2
        assert report.devices_mismatched == 2  # extra NMOS + missing RES

    def test_net_counts(self, report: LVSReport):
        assert report.nets_matched == 4
        assert report.nets_mismatched == 1  # EXTRA_NET

    def test_mismatch_count(self, report: LVSReport):
        assert len(report.mismatches) == 3  # 1 net + 2 device mismatches

    def test_mismatch_types_present(self, report: LVSReport):
        types = {m.type for m in report.mismatches}
        assert LVSMismatchType.extra_device in types
        assert LVSMismatchType.missing_device in types
        assert LVSMismatchType.net_mismatch in types

    def test_extra_device_details(self, report: LVSReport):
        extra = [
            m for m in report.mismatches if m.type == LVSMismatchType.extra_device
        ]
        assert len(extra) == 1
        m = extra[0]
        assert "NMOS" in m.name
        assert m.expected == "(not in schematic)"
        assert "NMOS" in m.actual

    def test_missing_device_details(self, report: LVSReport):
        missing = [
            m for m in report.mismatches if m.type == LVSMismatchType.missing_device
        ]
        assert len(missing) == 1
        m = missing[0]
        assert "RES" in m.name
        assert "RES" in m.expected
        assert "R=1000" in m.expected
        assert m.actual == "(not in layout)"

    def test_net_mismatch_details(self, report: LVSReport):
        net_mm = [
            m for m in report.mismatches if m.type == LVSMismatchType.net_mismatch
        ]
        assert len(net_mm) == 1
        m = net_mm[0]
        assert "EXTRA_NET" in m.name
        assert m.expected == "(not in schematic)"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_empty_string_raises(self):
        parser = LVSReportParser()
        with pytest.raises(LVSParseError, match="Empty"):
            parser.parse_string("")

    def test_invalid_header_raises(self):
        parser = LVSReportParser()
        with pytest.raises(LVSParseError, match="Not a valid"):
            parser.parse_string("this is not a valid lvsdb file")

    def test_file_not_found_raises(self):
        parser = LVSReportParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_file("/nonexistent/path.lvsdb")

    def test_header_only_returns_match(self):
        """A file with just the header and no xref → treated as match."""
        parser = LVSReportParser()
        report = parser.parse_string(f"{LVSDB_HEADER}\n")
        assert report.match is True
        assert report.mismatches == []

    def test_xref_only_minimal(self):
        """Minimal file with xref but no layout/reference sections."""
        content = f"""{LVSDB_HEADER}
xref(
 circuit(TOP TOP match
  xref(
   net(1 1 match)
   device(1 1 match)
  )
 )
)
"""
        parser = LVSReportParser()
        report = parser.parse_string(content)
        assert report.match is True
        assert report.devices_matched == 1
        assert report.nets_matched == 1


# ---------------------------------------------------------------------------
# Parameter mismatch
# ---------------------------------------------------------------------------


class TestParameterMismatch:
    def test_device_parameter_mismatch(self):
        content = f"""{LVSDB_HEADER}
layout(
 class(NMOS MOS4)
 circuit(TOP
  net(1 name(VSS))
  net(2 name(IN))
  device(1 NMOS
   name($1)
   param(L 0.25)
   param(W 2.0)
  )
 )
)
reference(
 class(NMOS MOS4)
 circuit(TOP
  net(1 name(VSS))
  net(2 name(IN))
  device(1 NMOS
   name(N1)
   param(L 0.25)
   param(W 1.0)
  )
 )
)
xref(
 circuit(TOP TOP mismatch
  xref(
   net(1 1 match)
   net(2 2 match)
   device(1 1 mismatch)
  )
 )
)
"""
        parser = LVSReportParser()
        report = parser.parse_string(content)

        assert report.match is False
        assert report.devices_matched == 0
        assert report.devices_mismatched == 1
        assert len(report.mismatches) == 1

        m = report.mismatches[0]
        assert m.type == LVSMismatchType.parameter_mismatch
        assert "NMOS" in m.name
        # Expected shows reference device params
        assert "W=1.0" in m.expected
        # Actual shows layout device params
        assert "W=2.0" in m.actual

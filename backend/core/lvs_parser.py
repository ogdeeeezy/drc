"""Parse KLayout .lvsdb report files into structured LVS data.

The .lvsdb format is a KLayout-specific text format (NOT XML) using
S-expression-like syntax. It contains three main sections:
  - layout(...)     — extracted netlist from layout
  - reference(...)  — reference netlist from schematic
  - xref(...)       — cross-reference pairing results

Status values in xref: match, mismatch, nomatch, warning, skipped.
Short-form equivalents: 1, 0, X, W, S.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.core.lvs_models import LVSMismatch, LVSMismatchType, LVSReport

LVSDB_HEADER = "#%lvsdb-klayout"

# Section keyword aliases (long → short form)
_KEYWORD_ALIASES: dict[str, set[str]] = {
    "layout": {"layout", "J"},
    "reference": {"reference", "H"},
    "xref": {"xref", "Z"},
    "circuit": {"circuit", "X"},
    "net": {"net", "N"},
    "device": {"device", "D"},
    "pin": {"pin", "P"},
    "name": {"name"},
    "param": {"param"},
    "description": {"description", "B"},
}

# Status normalization (long and short forms → canonical)
_STATUS_MAP: dict[str, str] = {
    "match": "match",
    "nomatch": "nomatch",
    "mismatch": "mismatch",
    "warning": "warning",
    "skipped": "skipped",
    "1": "match",
    "0": "mismatch",
    "S": "skipped",
}

# Match-equivalent statuses (count as matched in device/net tallies)
_MATCH_STATUSES = {"match", "warning"}


class LVSParseError(Exception):
    """Raised when a .lvsdb file cannot be parsed."""

    def __init__(self, message: str, context: str = ""):
        self.context = context
        full = message + (f" (context: {context})" if context else "")
        super().__init__(full)


@dataclass
class _DeviceInfo:
    """Device info extracted from layout/reference circuit."""

    device_id: str
    device_class: str
    name: str = ""
    params: dict[str, str] = field(default_factory=dict)


@dataclass
class _CircuitInfo:
    """Circuit device/net info from layout/reference sections."""

    name: str
    devices: dict[str, _DeviceInfo] = field(default_factory=dict)
    nets: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def _tokenize(content: str) -> list[str]:
    """Tokenize .lvsdb content into a flat token list.

    Tokens: '(', ')', and string values (keywords, numbers, quoted strings).
    Comments (# to EOL) are stripped. Whitespace/commas are separators.
    """
    tokens: list[str] = []
    i = 0
    n = len(content)
    while i < n:
        c = content[i]
        if c == "#":
            while i < n and content[i] != "\n":
                i += 1
        elif c in "()":
            tokens.append(c)
            i += 1
        elif c in " \t\n\r,":
            i += 1
        elif c in "\"'":
            quote = c
            i += 1
            chars: list[str] = []
            while i < n and content[i] != quote:
                if content[i] == "\\" and i + 1 < n:
                    i += 1
                    chars.append(content[i])
                else:
                    chars.append(content[i])
                i += 1
            if i < n:
                i += 1  # skip closing quote
            tokens.append("".join(chars))
        else:
            chars = []
            while i < n and content[i] not in "() \t\n\r,#":
                chars.append(content[i])
                i += 1
            if chars:
                tokens.append("".join(chars))
    return tokens


# ---------------------------------------------------------------------------
# Block navigation helpers
# ---------------------------------------------------------------------------


def _find_block(
    tokens: list[str],
    keyword: str,
    start: int = 0,
    end: int | None = None,
) -> tuple[int, int] | None:
    """Find first ``keyword(...)`` and return (content_start, content_end).

    content_end is the index of the closing ``)``, so content tokens are
    ``tokens[content_start : content_end]``.
    """
    aliases = _KEYWORD_ALIASES.get(keyword, {keyword})
    if end is None:
        end = len(tokens)
    i = start
    while i < end:
        if tokens[i] in aliases and i + 1 < end and tokens[i + 1] == "(":
            depth = 1
            j = i + 2
            while j < len(tokens) and depth > 0:
                if tokens[j] == "(":
                    depth += 1
                elif tokens[j] == ")":
                    depth -= 1
                j += 1
            return (i + 2, j - 1)
        i += 1
    return None


def _iter_blocks(
    tokens: list[str],
    keyword: str,
    start: int,
    end: int,
):
    """Yield ``(keyword_pos, content_start, content_end)`` for each ``keyword(...)``."""
    aliases = _KEYWORD_ALIASES.get(keyword, {keyword})
    i = start
    while i < end:
        if tokens[i] in aliases and i + 1 < end and tokens[i + 1] == "(":
            depth = 1
            j = i + 2
            while j < len(tokens) and depth > 0:
                if tokens[j] == "(":
                    depth += 1
                elif tokens[j] == ")":
                    depth -= 1
                j += 1
            yield (i, i + 2, j - 1)
            i = j
        else:
            i += 1


def _parse_id(tokens: list[str], pos: int) -> tuple[str | None, int]:
    """Parse an ID (number/name) or ``()`` for empty/unmatched."""
    if (
        pos < len(tokens)
        and tokens[pos] == "("
        and pos + 1 < len(tokens)
        and tokens[pos + 1] == ")"
    ):
        return None, pos + 2
    if pos < len(tokens) and tokens[pos] not in ("(", ")"):
        return tokens[pos], pos + 1
    return None, pos


def _normalize_status(token: str) -> str:
    """Normalize a status token to its canonical form."""
    return _STATUS_MAP.get(token, token)


# ---------------------------------------------------------------------------
# Circuit extraction (layout / reference sections)
# ---------------------------------------------------------------------------


def _extract_circuits(
    tokens: list[str], start: int, end: int
) -> dict[str, _CircuitInfo]:
    """Extract circuit device/net info from a layout or reference section."""
    circuits: dict[str, _CircuitInfo] = {}

    for _, cstart, cend in _iter_blocks(tokens, "circuit", start, end):
        if cstart >= cend:
            continue
        circuit_name = tokens[cstart]
        circuit = _CircuitInfo(name=circuit_name)

        # Extract nets: net(id name(NAME) ...)
        for _, nstart, nend in _iter_blocks(tokens, "net", cstart, cend):
            if nstart >= nend:
                continue
            net_id = tokens[nstart]
            net_name = net_id  # default to ID
            name_block = _find_block(tokens, "name", nstart, nend)
            if name_block:
                ns, ne = name_block
                if ns < ne:
                    net_name = tokens[ns]
            circuit.nets[net_id] = net_name

        # Extract devices: device(id CLASS name(NAME) param(K V) ...)
        for _, dstart, dend in _iter_blocks(tokens, "device", cstart, cend):
            if dstart >= dend:
                continue
            dev_id = tokens[dstart]
            dev_class = tokens[dstart + 1] if dstart + 1 < dend else ""
            # Skip if dev_class looks like a sub-block keyword (e.g. 'name(')
            if dev_class in ("(", ")"):
                dev_class = ""
            dev = _DeviceInfo(device_id=dev_id, device_class=dev_class)

            name_block = _find_block(tokens, "name", dstart, dend)
            if name_block:
                ns, ne = name_block
                if ns < ne:
                    dev.name = tokens[ns]

            for _, pstart, pend in _iter_blocks(tokens, "param", dstart, dend):
                if pstart + 1 <= pend:
                    dev.params[tokens[pstart]] = tokens[pstart + 1]

            circuit.devices[dev_id] = dev

        circuits[circuit_name] = circuit

    return circuits


def _format_device(dev: _DeviceInfo | None) -> str:
    """Format device info for human-readable mismatch description."""
    if dev is None:
        return "unknown"
    parts = [dev.device_class]
    if dev.name:
        parts.append(f"({dev.name})")
    if dev.params:
        param_str = ", ".join(f"{k}={v}" for k, v in dev.params.items())
        parts.append(f"[{param_str}]")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------


class LVSReportParser:
    """Parse KLayout .lvsdb report files into structured LVSReport objects."""

    def parse_file(self, path: str | Path) -> LVSReport:
        """Parse a .lvsdb file from disk."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Report file not found: {path}")
        try:
            content = path.read_text()
        except (OSError, UnicodeDecodeError) as e:
            raise LVSParseError(f"Cannot read file: {e}", context=str(path)) from e
        return self.parse_string(content)

    def parse_string(self, content: str) -> LVSReport:
        """Parse .lvsdb content from a string."""
        content = content.strip()
        if not content:
            raise LVSParseError("Empty file content")

        if not content.startswith(LVSDB_HEADER):
            raise LVSParseError(
                "Not a valid .lvsdb file",
                context="Missing #%lvsdb-klayout header",
            )

        try:
            tokens = _tokenize(content)
        except Exception as e:
            raise LVSParseError(f"Tokenization failed: {e}") from e

        if not tokens:
            # Header-only file with no sections → treat as clean match
            return LVSReport(match=True)

        return self._parse_tokens(tokens)

    def _parse_tokens(self, tokens: list[str]) -> LVSReport:
        """Parse tokenized .lvsdb content into an LVSReport."""
        n = len(tokens)

        # Extract layout circuit info for name lookups
        layout_circuits: dict[str, _CircuitInfo] = {}
        layout_block = _find_block(tokens, "layout", 0, n)
        if layout_block:
            layout_circuits = _extract_circuits(tokens, *layout_block)

        # Extract reference circuit info for name lookups
        ref_circuits: dict[str, _CircuitInfo] = {}
        ref_block = _find_block(tokens, "reference", 0, n)
        if ref_block:
            ref_circuits = _extract_circuits(tokens, *ref_block)

        # Parse cross-reference section
        xref_block = _find_block(tokens, "xref", 0, n)
        if xref_block is None:
            # No xref → treat as clean match (extraction-only report)
            return LVSReport(match=True)

        overall_match = True
        devices_matched = 0
        devices_mismatched = 0
        nets_matched = 0
        nets_mismatched = 0
        mismatches: list[LVSMismatch] = []

        xstart, xend = xref_block

        for _, cstart, cend in _iter_blocks(tokens, "circuit", xstart, xend):
            pos = cstart
            layout_name, pos = _parse_id(tokens, pos)
            ref_name, pos = _parse_id(tokens, pos)
            circuit_status = _normalize_status(
                tokens[pos] if pos < cend else "match"
            )

            if circuit_status not in _MATCH_STATUSES:
                overall_match = False

            # Look up circuit info for name resolution
            layout_circuit = layout_circuits.get(
                layout_name or "", _CircuitInfo(name="")
            )
            ref_circuit = ref_circuits.get(ref_name or "", _CircuitInfo(name=""))

            # Find inner xref block
            inner_xref = _find_block(tokens, "xref", cstart, cend)
            if inner_xref is None:
                continue

            ixstart, ixend = inner_xref

            # --- Net pairs ---
            for _, nstart, nend in _iter_blocks(tokens, "net", ixstart, ixend):
                npos = nstart
                lid, npos = _parse_id(tokens, npos)
                rid, npos = _parse_id(tokens, npos)
                status = _normalize_status(
                    tokens[npos] if npos < nend else "match"
                )
                msg = _extract_description(tokens, npos, nend)

                if status in _MATCH_STATUSES:
                    nets_matched += 1
                else:
                    nets_mismatched += 1
                    layout_net = layout_circuit.nets.get(
                        lid or "", lid or "(not in layout)"
                    )
                    ref_net = ref_circuit.nets.get(
                        rid or "", rid or "(not in schematic)"
                    )
                    mismatches.append(
                        LVSMismatch(
                            type=LVSMismatchType.net_mismatch,
                            name=layout_net if lid else ref_net,
                            expected=ref_net if rid else "(not in schematic)",
                            actual=layout_net if lid else "(not in layout)",
                            details=msg or f"Net {status}",
                        )
                    )

            # --- Pin pairs ---
            for _, pstart, pend in _iter_blocks(tokens, "pin", ixstart, ixend):
                ppos = pstart
                lid, ppos = _parse_id(tokens, ppos)
                rid, ppos = _parse_id(tokens, ppos)
                status = _normalize_status(
                    tokens[ppos] if ppos < pend else "match"
                )
                msg = _extract_description(tokens, ppos, pend)

                if status not in _MATCH_STATUSES:
                    mismatches.append(
                        LVSMismatch(
                            type=LVSMismatchType.pin_mismatch,
                            name=f"pin {lid or rid or '?'}",
                            expected=str(rid) if rid else "(not in schematic)",
                            actual=str(lid) if lid else "(not in layout)",
                            details=msg or f"Pin {status}",
                        )
                    )

            # --- Device pairs ---
            for _, dstart, dend in _iter_blocks(tokens, "device", ixstart, ixend):
                dpos = dstart
                lid, dpos = _parse_id(tokens, dpos)
                rid, dpos = _parse_id(tokens, dpos)
                status = _normalize_status(
                    tokens[dpos] if dpos < dend else "match"
                )
                msg = _extract_description(tokens, dpos, dend)

                if status in _MATCH_STATUSES:
                    devices_matched += 1
                else:
                    devices_mismatched += 1
                    layout_dev = layout_circuit.devices.get(lid or "")
                    ref_dev = ref_circuit.devices.get(rid or "")

                    if lid and not rid:
                        mtype = LVSMismatchType.extra_device
                        name = (
                            f"{layout_dev.device_class} {layout_dev.name}"
                            if layout_dev
                            else f"device {lid}"
                        )
                        expected = "(not in schematic)"
                        actual = (
                            _format_device(layout_dev)
                            if layout_dev
                            else f"device {lid}"
                        )
                    elif rid and not lid:
                        mtype = LVSMismatchType.missing_device
                        name = (
                            f"{ref_dev.device_class} {ref_dev.name}"
                            if ref_dev
                            else f"device {rid}"
                        )
                        expected = (
                            _format_device(ref_dev) if ref_dev else f"device {rid}"
                        )
                        actual = "(not in layout)"
                    else:
                        mtype = LVSMismatchType.parameter_mismatch
                        name = (
                            f"{ref_dev.device_class} {ref_dev.name}"
                            if ref_dev
                            else f"device {lid}"
                        )
                        expected = (
                            _format_device(ref_dev) if ref_dev else str(rid)
                        )
                        actual = (
                            _format_device(layout_dev) if layout_dev else str(lid)
                        )

                    mismatches.append(
                        LVSMismatch(
                            type=mtype,
                            name=name.strip(),
                            expected=expected,
                            actual=actual,
                            details=msg or f"Device {status}",
                        )
                    )

        return LVSReport(
            match=overall_match,
            devices_matched=devices_matched,
            devices_mismatched=devices_mismatched,
            nets_matched=nets_matched,
            nets_mismatched=nets_mismatched,
            mismatches=mismatches,
        )


def _extract_description(tokens: list[str], start: int, end: int) -> str:
    """Extract a description(...) message from a token range."""
    desc_block = _find_block(tokens, "description", start, end)
    if desc_block:
        ds, de = desc_block
        if ds < de:
            return tokens[ds]
    return ""

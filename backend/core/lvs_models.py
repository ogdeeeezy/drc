"""LVS data models — structured output of Layout vs Schematic checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LVSMismatchType(str, Enum):
    missing_device = "missing_device"
    extra_device = "extra_device"
    net_mismatch = "net_mismatch"
    pin_mismatch = "pin_mismatch"
    parameter_mismatch = "parameter_mismatch"


@dataclass
class LVSMismatch:
    """A single LVS mismatch between layout and schematic."""

    type: LVSMismatchType
    name: str
    expected: str
    actual: str
    details: str = ""


@dataclass
class LVSReport:
    """Complete LVS report parsed from a .lvsdb file."""

    match: bool
    devices_matched: int = 0
    devices_mismatched: int = 0
    nets_matched: int = 0
    nets_mismatched: int = 0
    mismatches: list[LVSMismatch] = field(default_factory=list)

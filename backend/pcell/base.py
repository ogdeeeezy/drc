"""Base class for parameterized cell generators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import gdstk


@dataclass
class PCellResult:
    """Result from PCell generation."""

    cell: gdstk.Cell
    cell_name: str
    params: dict  # echo back the input parameters
    metadata: dict = field(default_factory=dict)  # e.g., calculated capacitance


class PCellGenerator(ABC):
    """Abstract base class for parameterized cell generators.

    Subclasses implement generate() to produce a gdstk.Cell
    with the correct geometry for a specific device type.
    """

    @abstractmethod
    def generate(self, params: dict) -> PCellResult:
        """Generate a GDS cell from parameters.

        Args:
            params: Device-specific parameters (W, L, fingers, etc.)

        Returns:
            PCellResult with the generated cell and metadata.

        Raises:
            ValueError: If parameters are invalid.
        """
        ...

    @abstractmethod
    def validate_params(self, params: dict) -> None:
        """Validate parameters, raise ValueError if invalid.

        Called internally by generate() before layout construction.
        """
        ...

    @abstractmethod
    def param_schema(self) -> dict:
        """Return parameter schema describing accepted parameters.

        Returns:
            Dict with param names as keys, each containing:
            - type: str (e.g., "float", "int", "str")
            - description: str
            - default: optional default value
            - min/max: optional bounds
            - choices: optional list of valid values
        """
        ...

    @staticmethod
    def snap_to_grid(value: float, grid: float = 0.005) -> float:
        """Snap a value to the manufacturing grid."""
        return round(value / grid) * grid

    @staticmethod
    def cell_name_format(pdk: str, device: str, **params: float | int) -> str:
        """Generate a deterministic cell name from parameters.

        Floats are formatted with 'p' replacing '.', e.g., 0.42 → '0p42'.
        """
        parts = [pdk, device]
        for key, val in params.items():
            if isinstance(val, float):
                formatted = f"{val:.3f}".rstrip("0").rstrip(".")
                formatted = formatted.replace(".", "p")
            else:
                formatted = str(val)
            parts.append(f"{key}{formatted}")
        return "_".join(parts)

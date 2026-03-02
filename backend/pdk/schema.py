"""PDK configuration schema — the abstraction layer that makes new PDKs = config, not code."""

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class RuleType(str, Enum):
    min_width = "min_width"
    min_spacing = "min_spacing"
    min_area = "min_area"
    min_enclosure = "min_enclosure"
    min_extension = "min_extension"
    exact_size = "exact_size"  # for fixed-size vias
    off_grid = "off_grid"


class GDSLayer(BaseModel):
    """A single GDS layer with its layer/datatype pair."""

    gds_layer: int = Field(ge=0)
    gds_datatype: int = Field(ge=0)
    description: str
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    is_routing: bool = False
    is_via: bool = False

    @property
    def layer_pair(self) -> tuple[int, int]:
        return (self.gds_layer, self.gds_datatype)


class DesignRule(BaseModel):
    """A single design rule with threshold and metadata."""

    rule_id: str  # e.g. "m1.1"
    rule_type: RuleType
    layer: str  # e.g. "met1"
    related_layer: str | None = None  # for enclosure/separation rules
    value_um: float = Field(gt=0, description="Threshold in microns")
    description: str = ""
    severity: int = Field(default=5, ge=1, le=10)

    @field_validator("rule_id")
    @classmethod
    def rule_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rule_id must not be empty")
        return v


class ConnectivityRule(BaseModel):
    """Defines a via connection between two metal/routing layers."""

    via_layer: str  # e.g. "via"
    lower_layer: str  # e.g. "met1"
    upper_layer: str  # e.g. "met2"


class FixStrategyWeight(BaseModel):
    """Per-rule-type fix strategy configuration."""

    enabled: bool = True
    priority: int = Field(default=5, ge=1, le=10, description="1 = highest priority")
    prefer_move: bool = True  # for spacing: move vs shrink
    max_iterations: int = Field(default=3, ge=1)


class PDKConfig(BaseModel):
    """Complete PDK configuration — everything needed to run DRC and suggest fixes."""

    name: str
    version: str
    process_node_nm: int = Field(gt=0)
    grid_um: float = Field(gt=0, description="Manufacturing grid in microns")
    layers: dict[str, GDSLayer]
    rules: list[DesignRule]
    connectivity: list[ConnectivityRule]
    fix_weights: dict[str, FixStrategyWeight]
    klayout_drc_deck: str = Field(description="Filename of KLayout DRC deck")

    def get_layer(self, name: str) -> GDSLayer:
        """Get layer by name, raise KeyError if not found."""
        if name not in self.layers:
            raise KeyError(f"Layer '{name}' not found in PDK '{self.name}'")
        return self.layers[name]

    def get_rules_for_layer(self, layer_name: str) -> list[DesignRule]:
        """Get all rules that apply to a given layer."""
        return [
            r for r in self.rules if r.layer == layer_name or r.related_layer == layer_name
        ]

    def get_rule(self, rule_id: str) -> DesignRule | None:
        """Get a rule by its ID."""
        for r in self.rules:
            if r.rule_id == rule_id:
                return r
        return None

    def get_routing_layers(self) -> list[str]:
        """Get names of all routing layers, ordered by GDS layer number."""
        routing = [(name, layer) for name, layer in self.layers.items() if layer.is_routing]
        routing.sort(key=lambda x: (x[1].gds_layer, x[1].gds_datatype))
        return [name for name, _ in routing]

    def get_via_layers(self) -> list[str]:
        """Get names of all via layers."""
        return [name for name, layer in self.layers.items() if layer.is_via]

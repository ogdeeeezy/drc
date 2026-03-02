"""PDK discovery and loading."""

import json
from pathlib import Path

from backend.config import PDK_CONFIGS_DIR
from backend.pdk.schema import PDKConfig


class PDKRegistry:
    """Discovers and loads PDK configurations from the configs directory."""

    def __init__(self, configs_dir: Path = PDK_CONFIGS_DIR):
        self._configs_dir = configs_dir
        self._cache: dict[str, PDKConfig] = {}

    def list_pdks(self) -> list[str]:
        """List available PDK names (directory names under configs/)."""
        if not self._configs_dir.exists():
            return []
        return sorted(
            d.name
            for d in self._configs_dir.iterdir()
            if d.is_dir() and (d / "pdk.json").exists()
        )

    def load(self, pdk_name: str) -> PDKConfig:
        """Load a PDK config by name. Caches after first load."""
        if pdk_name in self._cache:
            return self._cache[pdk_name]

        config_path = self._configs_dir / pdk_name / "pdk.json"
        if not config_path.exists():
            available = self.list_pdks()
            raise FileNotFoundError(
                f"PDK '{pdk_name}' not found at {config_path}. "
                f"Available PDKs: {available}"
            )

        with open(config_path) as f:
            data = json.load(f)

        config = PDKConfig.model_validate(data)
        self._cache[pdk_name] = config
        return config

    def reload(self, pdk_name: str) -> PDKConfig:
        """Force reload a PDK config (clears cache)."""
        self._cache.pop(pdk_name, None)
        return self.load(pdk_name)

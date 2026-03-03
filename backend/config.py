"""Application configuration."""

import shutil
from dataclasses import dataclass
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = Path(__file__).parent
PDK_CONFIGS_DIR = BACKEND_DIR / "pdk" / "configs"
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
JOBS_DIR = PROJECT_ROOT / "data" / "jobs"
DATABASE_PATH = JOBS_DIR / "jobs.db"


def _find_klayout() -> str:
    """Find klayout binary: PATH first, then macOS app bundle."""
    on_path = shutil.which("klayout")
    if on_path:
        return on_path
    mac_app = Path("/Applications/KLayout/klayout.app/Contents/MacOS/klayout")
    if mac_app.exists():
        return str(mac_app)
    return "klayout"


# DRC settings
KLAYOUT_BINARY = _find_klayout()
DRC_TIMEOUT_SECONDS = 2700  # 45 min — large tiled runs at throttled CPU need headroom
DRC_NICE_LEVEL = 10  # Lower scheduling priority (0-20, higher = nicer to other processes)
DRC_CPU_LIMIT_PERCENT = 60  # Hard CPU cap via cpulimit (ignored if cpulimit not installed)

# Grid
DEFAULT_GRID_UM = 0.005


# Adaptive DRC — auto-select mode/threads based on GDS file size to prevent OOM on 8GB machines.
@dataclass(frozen=True)
class DRCStrategy:
    """DRC execution strategy selected by file size."""

    threads: int
    mode: str  # "deep" or "tiled"
    tile_size_um: float | None = None  # only used when mode == "tiled"


# Thresholds in bytes
DRC_SMALL_THRESHOLD = 20 * 1024 * 1024  # 20 MB
DRC_LARGE_THRESHOLD = 80 * 1024 * 1024  # 80 MB
DRC_TILE_SIZE_UM = 1000.0

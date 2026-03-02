"""Application configuration."""

from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = Path(__file__).parent
PDK_CONFIGS_DIR = BACKEND_DIR / "pdk" / "configs"
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
JOBS_DIR = PROJECT_ROOT / "data" / "jobs"
DATABASE_PATH = JOBS_DIR / "jobs.db"

# DRC settings
KLAYOUT_BINARY = "klayout"
DRC_TIMEOUT_SECONDS = 300

# Grid
DEFAULT_GRID_UM = 0.005

"""Shared dependencies for API routes — singleton managers."""

from __future__ import annotations

from backend.jobs.manager import JobManager
from backend.pdk.registry import PDKRegistry

_job_manager: JobManager | None = None
_pdk_registry: PDKRegistry | None = None


def get_job_manager() -> JobManager:
    global _job_manager
    if _job_manager is None:
        import backend.config as cfg
        _job_manager = JobManager(jobs_dir=cfg.JOBS_DIR)
    return _job_manager


def get_pdk_registry() -> PDKRegistry:
    global _pdk_registry
    if _pdk_registry is None:
        _pdk_registry = PDKRegistry()
    return _pdk_registry


def reset_deps() -> None:
    """Reset singletons (for testing)."""
    global _job_manager, _pdk_registry
    _job_manager = None
    _pdk_registry = None

"""Shared dependencies for API routes — singleton managers."""

from __future__ import annotations

from backend.jobs.manager import JobManager
from backend.pdk.knowledge import KnowledgeBase
from backend.pdk.registry import PDKRegistry

_job_manager: JobManager | None = None
_pdk_registry: PDKRegistry | None = None
_knowledge_base: KnowledgeBase | None = None


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


def get_knowledge_base() -> KnowledgeBase:
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = KnowledgeBase()
    return _knowledge_base


def reset_deps() -> None:
    """Reset singletons (for testing)."""
    global _job_manager, _pdk_registry, _knowledge_base
    _job_manager = None
    _pdk_registry = None
    _knowledge_base = None

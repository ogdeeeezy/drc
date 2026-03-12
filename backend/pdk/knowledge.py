"""PDK knowledge layer — assembles universal and PDK-specific domain knowledge."""

from __future__ import annotations

import logging
from pathlib import Path

from backend.config import BACKEND_DIR, PDK_CONFIGS_DIR

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = BACKEND_DIR / "pdk" / "knowledge"

# Valid task types for future filtering
TASK_TYPES = frozenset(
    {"deck_generation", "fix_suggestion", "triage", "lvs", "general"}
)


class KnowledgeBase:
    """Discovers and serves PDK knowledge files.

    Usage:
        kb = KnowledgeBase()
        context = kb.get_context("sky130")              # universal + sky130
        context = kb.get_context("gf180", task="lvs")   # universal + gf180 (if exists)
    """

    def __init__(
        self,
        knowledge_dir: Path = KNOWLEDGE_DIR,
        configs_dir: Path = PDK_CONFIGS_DIR,
    ):
        self._knowledge_dir = knowledge_dir
        self._configs_dir = configs_dir
        self._cache: dict[str, str] = {}

    def get_universal(self) -> str:
        """Return concatenated universal knowledge (drc-universal.md + rule-taxonomy.md)."""
        parts: list[str] = []
        for filename in ("drc-universal.md", "rule-taxonomy.md"):
            content = self._load_file(self._knowledge_dir / filename)
            if content:
                parts.append(content)
        return "\n\n".join(parts)

    def get_pdk_knowledge(self, pdk_name: str) -> str:
        """Return PDK-specific knowledge, or empty string if not found."""
        knowledge_path = self._configs_dir / pdk_name / f"{pdk_name}-knowledge.md"
        return self._load_file(knowledge_path)

    def get_context(self, pdk_name: str, task: str = "general") -> str:
        """Assemble universal + PDK-specific knowledge for a given task.

        Args:
            pdk_name: PDK identifier (e.g. "sky130", "gf180").
            task: Task type for future filtering. Currently unused but reserved.

        Returns:
            Combined knowledge string. Universal knowledge is always included.
            PDK-specific knowledge is appended if a knowledge file exists.
        """
        if task not in TASK_TYPES:
            logger.warning("Unknown task type '%s', using 'general'", task)

        sections: list[str] = []

        universal = self.get_universal()
        if universal:
            sections.append(universal)

        pdk_knowledge = self.get_pdk_knowledge(pdk_name)
        if pdk_knowledge:
            sections.append(pdk_knowledge)

        return "\n\n".join(sections)

    def _load_file(self, path: Path) -> str:
        """Load a markdown file, returning empty string on failure."""
        cache_key = str(path)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not path.exists():
            logger.debug("Knowledge file not found: %s", path)
            return ""

        try:
            content = path.read_text(encoding="utf-8").strip()
            self._cache[cache_key] = content
            return content
        except OSError:
            logger.warning("Failed to read knowledge file: %s", path, exc_info=True)
            return ""

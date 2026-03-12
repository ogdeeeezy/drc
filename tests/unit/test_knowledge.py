"""Tests for PDK knowledge layer."""

from pathlib import Path

import pytest

from backend.pdk.knowledge import KnowledgeBase


@pytest.fixture()
def knowledge_base():
    """KnowledgeBase pointing at real project files."""
    return KnowledgeBase()


@pytest.fixture()
def empty_knowledge_base(tmp_path):
    """KnowledgeBase pointing at empty directories."""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    return KnowledgeBase(knowledge_dir=knowledge_dir, configs_dir=configs_dir)


class TestLoadUniversalKnowledge:
    def test_load_universal_knowledge(self, knowledge_base):
        universal = knowledge_base.get_universal()
        assert len(universal) > 0
        assert "Grid Precision" in universal or "DRC Universal" in universal

    def test_universal_includes_rule_taxonomy(self, knowledge_base):
        universal = knowledge_base.get_universal()
        assert "Rule Taxonomy" in universal or "RuleType" in universal

    def test_empty_knowledge_dir(self, empty_knowledge_base):
        universal = empty_knowledge_base.get_universal()
        assert universal == ""


class TestLoadPDKKnowledge:
    def test_load_pdk_knowledge(self, knowledge_base):
        sky130 = knowledge_base.get_pdk_knowledge("sky130")
        assert len(sky130) > 0
        assert "SKY130" in sky130

    def test_missing_pdk_knowledge_graceful(self, knowledge_base):
        result = knowledge_base.get_pdk_knowledge("nonexistent_pdk")
        assert result == ""

    def test_empty_configs_dir(self, empty_knowledge_base):
        result = empty_knowledge_base.get_pdk_knowledge("sky130")
        assert result == ""


class TestGetContext:
    def test_get_context_assembles_both(self, knowledge_base):
        context = knowledge_base.get_context("sky130")
        # Must contain universal content
        assert "DRC Universal" in context or "Grid Precision" in context
        # Must contain SKY130-specific content
        assert "SKY130" in context

    def test_get_context_unknown_pdk(self, knowledge_base):
        context = knowledge_base.get_context("gf180")
        # Universal knowledge still present
        assert "DRC Universal" in context or "Grid Precision" in context
        # No crash, just no PDK-specific section
        assert "GF180" not in context

    def test_get_context_with_task(self, knowledge_base):
        context = knowledge_base.get_context("sky130", task="lvs")
        assert len(context) > 0

    def test_get_context_unknown_task_no_crash(self, knowledge_base):
        # Unknown task type logs a warning but doesn't crash
        context = knowledge_base.get_context("sky130", task="unknown_task")
        assert len(context) > 0

    def test_caching(self, knowledge_base):
        """Second call uses cache — same result, no re-read."""
        context1 = knowledge_base.get_context("sky130")
        context2 = knowledge_base.get_context("sky130")
        assert context1 == context2

"""Tests for centralized error hints mapping."""

import pytest

from backend.core.error_hints import get_hint


class TestGetHint:
    """Test that each error pattern produces the correct hint."""

    def test_empty_string_returns_none(self):
        assert get_hint("") is None

    def test_unrecognized_error_returns_none(self):
        assert get_hint("Something completely unexpected happened") is None

    def test_exec_format_error(self):
        hint = get_hint("Failed to execute KLayout: [Errno 8] Exec format error: '/usr/bin/klayout'")
        assert hint is not None
        assert "architecture" in hint

    def test_permission_denied(self):
        hint = get_hint("Failed to execute KLayout: [Errno 13] Permission denied: '/usr/bin/klayout'")
        assert hint is not None
        assert "Permission" in hint or "permission" in hint
        assert "Gatekeeper" in hint

    def test_no_such_file_klayout(self):
        hint = get_hint("[Errno 2] No such file or directory: 'klayout'")
        assert hint is not None
        assert "KLAYOUT_BINARY" in hint

    def test_failed_to_execute_klayout(self):
        hint = get_hint("Failed to execute KLayout: [Errno 99] Unknown error")
        assert hint is not None
        assert "install" in hint.lower()

    def test_drc_timeout(self):
        hint = get_hint("DRC timed out after 2700s")
        assert hint is not None
        assert "DRC_TIMEOUT_SECONDS" in hint

    def test_lvs_timeout(self):
        hint = get_hint("LVS timed out after 2700s")
        assert hint is not None
        assert "DRC_TIMEOUT_SECONDS" in hint or "timeout" in hint.lower()

    def test_drc_deck_not_found(self):
        hint = get_hint("DRC deck not found: /path/to/deck.drc. Expected 'sky130.drc' in /pdk/configs/sky130")
        assert hint is not None
        assert "backend/pdk/configs" in hint

    def test_lvs_deck_not_found(self):
        hint = get_hint("LVS deck not found: /path/to/deck.lvs")
        assert hint is not None
        assert "pdk.json" in hint or "klayout_lvs_deck" in hint

    def test_lvs_deck_not_configured(self):
        hint = get_hint("PDK 'sky130' does not have an LVS deck configured.")
        assert hint is not None
        assert "klayout_lvs_deck" in hint

    def test_klayout_exit_code(self):
        hint = get_hint("KLayout DRC failed (exit code 1): some stderr output")
        assert hint is not None
        assert "corrupted" in hint.lower() or "GDSII" in hint

    def test_no_report_generated(self):
        hint = get_hint("KLayout completed but no report file generated. Check that the DRC deck uses report()")
        assert hint is not None
        assert "report()" in hint

    def test_binary_not_found_with_install(self):
        hint = get_hint("KLayout binary 'klayout' not found. Install with: brew install klayout")
        assert hint is not None
        assert "install" in hint.lower()

    def test_gdsii_not_found(self):
        hint = get_hint("GDSII file not found: /tmp/layout.gds")
        assert hint is not None
        assert "re-upload" in hint.lower()

    def test_netlist_not_found(self):
        hint = get_hint("Netlist file not found: /tmp/circuit.spice")
        assert hint is not None
        assert "re-upload" in hint.lower()

    def test_pdk_not_found(self):
        hint = get_hint("PDK 'gf180' not found")
        assert hint is not None
        assert "PDK" in hint or "/api/pdks" in hint

    def test_first_match_wins(self):
        """Exec format error should match the specific hint, not generic OSError."""
        hint = get_hint("Failed to execute KLayout: [Errno 8] Exec format error")
        assert "architecture" in hint

    def test_case_insensitive(self):
        hint = get_hint("PERMISSION DENIED running klayout")
        assert hint is not None
        assert "permission" in hint.lower() or "Permission" in hint

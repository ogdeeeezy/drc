"""Centralized error-to-hint mapping for user-facing error guidance.

Maps raw error messages (from DRC/LVS runners) to actionable hints
that help users resolve issues. Uses regex matching against error strings.
"""

from __future__ import annotations

import re

# (compiled_regex, hint_string) — first match wins
_HINT_RULES: list[tuple[re.Pattern[str], str]] = [
    # OSError variants
    (
        re.compile(r"Exec format error", re.IGNORECASE),
        "KLayout binary is for a different architecture. "
        "Reinstall KLayout for your platform (arm64 vs x86_64).",
    ),
    (
        re.compile(r"Permission denied", re.IGNORECASE),
        "Permission denied running KLayout. Check file permissions. "
        "On macOS, bypass Gatekeeper: sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app",
    ),
    (
        re.compile(r"No such file or directory.*klayout|klayout.*not found", re.IGNORECASE),
        "KLayout not found at the configured path. "
        "Install KLayout or set the KLAYOUT_BINARY environment variable.",
    ),
    (
        re.compile(r"Failed to execute KLayout", re.IGNORECASE),
        "Could not start KLayout process. Verify KLayout is installed and accessible. "
        "On macOS: brew install klayout. On Linux: apt install klayout.",
    ),
    # Timeout
    (
        re.compile(r"timed out after \d+s", re.IGNORECASE),
        "Design may be too large or complex. Try increasing DRC_TIMEOUT_SECONDS "
        "or simplifying the layout hierarchy.",
    ),
    # Deck not found
    (
        re.compile(r"DRC deck not found", re.IGNORECASE),
        "DRC deck file missing. Expected directory structure: "
        "backend/pdk/configs/<pdk_name>/<deck_file>.",
    ),
    (
        re.compile(r"LVS deck not found|does not have an LVS deck", re.IGNORECASE),
        "LVS deck file missing or not configured. Check that klayout_lvs_deck "
        "is set in pdk.json and the file exists in backend/pdk/configs/<pdk_name>/.",
    ),
    # KLayout crash (non-zero exit)
    (
        re.compile(r"failed \(exit code", re.IGNORECASE),
        "KLayout exited with an error. Common causes: corrupted GDSII, "
        "incompatible deck version, or missing layers in the design.",
    ),
    # No report generated
    (
        re.compile(r"no report file generated|no.*report.*generated", re.IGNORECASE),
        "KLayout ran but did not produce a report. The deck may be missing "
        "a report() call or may have silently failed on this design.",
    ),
    # Binary not found (generic)
    (
        re.compile(r"not found.*Install with", re.IGNORECASE),
        "KLayout is not installed. On macOS: brew install klayout. "
        "On Linux: apt install klayout. Then bypass Gatekeeper if needed.",
    ),
    # GDSII file not found
    (
        re.compile(r"GDSII file not found", re.IGNORECASE),
        "The GDSII layout file is missing. Try re-uploading the file.",
    ),
    # Netlist file not found
    (
        re.compile(r"Netlist file not found", re.IGNORECASE),
        "The SPICE netlist file is missing. Try re-uploading the netlist.",
    ),
    # PDK not found
    (
        re.compile(r"PDK.*not found|pdk\.json", re.IGNORECASE),
        "PDK configuration not found. Check available PDKs via the dropdown or GET /api/pdks.",
    ),
]


def get_hint(error_message: str) -> str | None:
    """Return an actionable hint for the given error message, or None if unrecognized.

    Scans _HINT_RULES in order and returns the hint for the first regex match.
    """
    if not error_message:
        return None
    for pattern, hint in _HINT_RULES:
        if pattern.search(error_message):
            return hint
    return None

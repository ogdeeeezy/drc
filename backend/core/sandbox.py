"""Sandboxed GDS/OASIS parsing — run untrusted file parsing in a subprocess with resource limits.

klayout and gdstk are C++ parsers processing untrusted binary formats (GDS, OASIS).
Parsing in-process risks memory bombs, infinite loops, or exploits in the C++ parser.
This module wraps parsing in a subprocess with:
  - timeout (prevents infinite loops / hangs)
  - max memory via resource.setrlimit (prevents memory bombs)
  - max CPU time via resource.setrlimit (prevents CPU exhaustion)
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_MEMORY_MB = 2048
DEFAULT_MAX_CPU_SECONDS = 60


@dataclass
class SandboxedParseResult:
    """Result of a sandboxed GDS parse."""

    success: bool
    cell_count: int
    top_cell_names: list[str]
    total_polygons: int
    error: str | None = None
    file_size_bytes: int = 0


# The script that runs inside the subprocess.
# It imports gdstk, sets resource limits, parses the file, and prints JSON to stdout.
_PARSE_SCRIPT = textwrap.dedent("""\
    import json
    import os
    import platform
    import resource
    import sys

    def set_limits(max_memory_bytes: int, max_cpu_seconds: int) -> None:
        \"\"\"Set resource limits for this process. Linux/macOS only.\"\"\"
        # Memory limit (RLIMIT_AS = address space)
        # On macOS, RLIMIT_AS is not always effective; use RLIMIT_DATA as fallback.
        if platform.system() == "Linux":
            try:
                resource.setrlimit(resource.RLIMIT_AS, (max_memory_bytes, max_memory_bytes))
            except (ValueError, OSError):
                pass
        else:
            # macOS: RLIMIT_DATA is more reliable than RLIMIT_AS
            try:
                resource.setrlimit(resource.RLIMIT_DATA, (max_memory_bytes, max_memory_bytes))
            except (ValueError, OSError):
                pass

        # CPU time limit
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_seconds, max_cpu_seconds))
        except (ValueError, OSError):
            pass

    def main() -> None:
        file_path = sys.argv[1]
        max_memory_bytes = int(sys.argv[2])
        max_cpu_seconds = int(sys.argv[3])

        set_limits(max_memory_bytes, max_cpu_seconds)

        try:
            import gdstk
            lib = gdstk.read_gds(file_path)
            top_cells = list(lib.top_level())
            total_polys = sum(len(c.polygons) for c in lib.cells)
            result = {
                "success": True,
                "cell_count": len(lib.cells),
                "top_cell_names": [c.name for c in top_cells],
                "total_polygons": total_polys,
                "error": None,
            }
        except MemoryError:
            result = {
                "success": False,
                "cell_count": 0,
                "top_cell_names": [],
                "total_polygons": 0,
                "error": "MemoryError: file too large or malformed",
            }
        except Exception as e:
            result = {
                "success": False,
                "cell_count": 0,
                "top_cell_names": [],
                "total_polygons": 0,
                "error": f"{type(e).__name__}: {e}",
            }

        json.dump(result, sys.stdout)

    main()
""")


def parse_gds_sandboxed(
    file_path: str | Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
    max_cpu_seconds: int = DEFAULT_MAX_CPU_SECONDS,
) -> SandboxedParseResult:
    """Parse a GDS file in a sandboxed subprocess with resource limits.

    This is a security boundary: the C++ parser (gdstk) runs in a child process
    with strict memory, CPU, and wall-clock limits. If the file is malicious
    (memory bomb, infinite loop, exploit), the subprocess is killed without
    affecting the main application.

    Args:
        file_path: Path to the GDS file.
        timeout: Wall-clock timeout in seconds (subprocess.run timeout).
        max_memory_mb: Maximum memory in MB (via RLIMIT_AS/RLIMIT_DATA).
        max_cpu_seconds: Maximum CPU time in seconds (via RLIMIT_CPU).

    Returns:
        SandboxedParseResult with parse metadata or error details.

    Raises:
        FileNotFoundError: If the GDS file doesn't exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"GDS file not found: {path}")

    file_size = path.stat().st_size
    max_memory_bytes = max_memory_mb * 1024 * 1024

    logger.info(
        "Sandboxed GDS parse: %s (%.1f MB, timeout=%ds, max_mem=%dMB, max_cpu=%ds)",
        path.name,
        file_size / (1024 * 1024),
        timeout,
        max_memory_mb,
        max_cpu_seconds,
    )

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                _PARSE_SCRIPT,
                str(path),
                str(max_memory_bytes),
                str(max_cpu_seconds),
            ],
            timeout=timeout,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Sandboxed GDS parse timed out after %ds: %s", timeout, path.name)
        return SandboxedParseResult(
            success=False,
            cell_count=0,
            top_cell_names=[],
            total_polygons=0,
            error=f"Parsing timed out after {timeout}s — file may be malicious or too large",
            file_size_bytes=file_size,
        )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or f"Subprocess exited with code {result.returncode}"
        # Check for signals (negative return code = killed by signal)
        if result.returncode < 0:
            signal_num = -result.returncode
            signal_names = {9: "SIGKILL (memory limit)", 24: "SIGXCPU (CPU limit)"}
            signal_name = signal_names.get(signal_num, f"signal {signal_num}")
            error_msg = f"Parser killed by {signal_name} — file may be malicious or too large"
        logger.warning("Sandboxed GDS parse failed: %s — %s", path.name, error_msg)
        return SandboxedParseResult(
            success=False,
            cell_count=0,
            top_cell_names=[],
            total_polygons=0,
            error=error_msg,
            file_size_bytes=file_size,
        )

    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Sandboxed GDS parse returned invalid JSON: %s", e)
        return SandboxedParseResult(
            success=False,
            cell_count=0,
            top_cell_names=[],
            total_polygons=0,
            error=f"Parser returned invalid output: {e}",
            file_size_bytes=file_size,
        )

    parsed = SandboxedParseResult(
        success=data.get("success", False),
        cell_count=data.get("cell_count", 0),
        top_cell_names=data.get("top_cell_names", []),
        total_polygons=data.get("total_polygons", 0),
        error=data.get("error"),
        file_size_bytes=file_size,
    )

    if parsed.success:
        logger.info(
            "Sandboxed parse OK: %d cells, %d polygons",
            parsed.cell_count,
            parsed.total_polygons,
        )
    else:
        logger.warning("Sandboxed parse reported error: %s", parsed.error)

    return parsed

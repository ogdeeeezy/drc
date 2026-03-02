"""KLayout DRC runner — execute DRC checks via KLayout batch mode subprocess."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.config import DRC_TIMEOUT_SECONDS, KLAYOUT_BINARY, PDK_CONFIGS_DIR
from backend.core.violation_models import DRCReport
from backend.core.violation_parser import ViolationParser
from backend.pdk.schema import PDKConfig


class DRCError(Exception):
    """Raised when DRC execution fails."""

    def __init__(self, message: str, returncode: int = -1, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


@dataclass
class DRCResult:
    """Result of a DRC run."""

    report: DRCReport
    report_path: Path
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    klayout_binary: str

    @property
    def has_violations(self) -> bool:
        return self.report.total_violations > 0

    @property
    def violation_summary(self) -> dict[str, int]:
        """Category → count mapping."""
        return {v.category: v.violation_count for v in self.report.violations}


class DRCRunner:
    """Execute KLayout DRC in batch mode as a subprocess.

    Usage:
        runner = DRCRunner()
        result = runner.run(Path("layout.gds"), pdk_config)
        for violation in result.report.violations:
            print(f"{violation.category}: {violation.violation_count} violations")
    """

    def __init__(
        self,
        klayout_binary: str = KLAYOUT_BINARY,
        timeout: int = DRC_TIMEOUT_SECONDS,
    ):
        self._binary = klayout_binary
        self._timeout = timeout
        self._parser = ViolationParser()

    @property
    def binary(self) -> str:
        return self._binary

    def check_klayout_available(self) -> bool:
        """Check if KLayout binary is available on PATH."""
        return shutil.which(self._binary) is not None

    def get_drc_deck_path(self, pdk: PDKConfig) -> Path:
        """Resolve the DRC deck file path for a PDK."""
        # Look in the PDK config directory
        pdk_dir = PDK_CONFIGS_DIR / pdk.name.lower().replace(" ", "_")
        deck_path = pdk_dir / pdk.klayout_drc_deck
        if not deck_path.exists():
            raise FileNotFoundError(
                f"DRC deck not found: {deck_path}. "
                f"Expected '{pdk.klayout_drc_deck}' in {pdk_dir}"
            )
        return deck_path

    def build_command(
        self,
        gds_path: Path,
        drc_deck_path: Path,
        report_path: Path,
        top_cell: str | None = None,
    ) -> list[str]:
        """Build the klayout batch command.

        Command format:
            klayout -b -r <deck.drc> -rd input=<gds> -rd report=<report.lyrdb> [-rd topcell=<name>]
        """
        cmd = [
            self._binary,
            "-b",  # batch mode (no GUI)
            "-r", str(drc_deck_path),
            "-rd", f"input={gds_path}",
            "-rd", f"report={report_path}",
        ]
        if top_cell:
            cmd.extend(["-rd", f"topcell={top_cell}"])
        return cmd

    def run(
        self,
        gds_path: str | Path,
        pdk: PDKConfig,
        top_cell: str | None = None,
        output_dir: str | Path | None = None,
        map_to_pdk: bool = True,
    ) -> DRCResult:
        """Run DRC on a GDSII file using the PDK's KLayout DRC deck.

        Args:
            gds_path: Path to input GDSII file.
            pdk: PDK configuration with DRC deck reference.
            top_cell: Top cell to check (auto-detected if None).
            output_dir: Directory for report output. Uses temp dir if None.
            map_to_pdk: Whether to map violations to PDK rules.

        Returns:
            DRCResult with parsed violations and execution metadata.

        Raises:
            DRCError: If KLayout is not available, DRC deck not found, or execution fails.
            FileNotFoundError: If GDSII file doesn't exist.
        """
        gds_path = Path(gds_path)
        if not gds_path.exists():
            raise FileNotFoundError(f"GDSII file not found: {gds_path}")

        if not self.check_klayout_available():
            raise DRCError(
                f"KLayout binary '{self._binary}' not found. "
                "Install with: brew install klayout (macOS) or apt install klayout (Linux)"
            )

        drc_deck_path = self.get_drc_deck_path(pdk)

        # Set up output directory
        use_temp = output_dir is None
        if use_temp:
            temp_dir = tempfile.mkdtemp(prefix="agentic_drc_")
            out_dir = Path(temp_dir)
        else:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

        report_path = out_dir / f"{gds_path.stem}_drc.lyrdb"

        cmd = self.build_command(gds_path, drc_deck_path, report_path, top_cell)

        start_time = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise DRCError(
                f"DRC timed out after {self._timeout}s",
                returncode=-1,
                stderr=str(e),
            )
        except OSError as e:
            raise DRCError(
                f"Failed to execute KLayout: {e}",
                returncode=-1,
                stderr=str(e),
            )
        duration = time.monotonic() - start_time

        # KLayout returns 0 on success, even when violations are found
        if proc.returncode != 0:
            raise DRCError(
                f"KLayout DRC failed (exit code {proc.returncode}): {proc.stderr}",
                returncode=proc.returncode,
                stderr=proc.stderr,
            )

        # Parse the report
        if not report_path.exists():
            raise DRCError(
                "KLayout completed but no report file generated. "
                "Check that the DRC deck uses report() to output results.",
                returncode=proc.returncode,
                stderr=proc.stderr,
            )

        report = self._parser.parse_file(report_path)
        if map_to_pdk:
            self._parser.map_to_pdk(report, pdk)

        return DRCResult(
            report=report,
            report_path=report_path,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_seconds=duration,
            klayout_binary=self._binary,
        )

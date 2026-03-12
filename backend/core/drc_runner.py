"""KLayout DRC runner — execute DRC checks via KLayout batch mode subprocess."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from backend.config import (
    DRC_CPU_LIMIT_PERCENT,
    DRC_LARGE_THRESHOLD,
    DRC_NICE_LEVEL,
    DRC_SMALL_THRESHOLD,
    DRC_TILE_SIZE_UM,
    DRC_TIMEOUT_SECONDS,
    KLAYOUT_BINARY,
    PDK_CONFIGS_DIR,
    DRCStrategy,
)

logger = logging.getLogger(__name__)
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
    strategy: DRCStrategy | None = None

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
        """Check if KLayout binary is available."""
        if Path(self._binary).is_absolute():
            return Path(self._binary).exists()
        return shutil.which(self._binary) is not None

    @staticmethod
    def adaptive_strategy(file_size_bytes: int) -> DRCStrategy:
        """Select DRC execution strategy based on GDS file size.

        | File Size | Threads | Mode                |
        |-----------|---------|---------------------|
        | < 20 MB   | 4       | deep                |
        | 20-80 MB  | 2       | deep                |
        | > 80 MB   | 1       | tiled (1000 µm)     |
        """
        if file_size_bytes < DRC_SMALL_THRESHOLD:
            return DRCStrategy(threads=4, mode="deep")
        if file_size_bytes < DRC_LARGE_THRESHOLD:
            return DRCStrategy(threads=2, mode="deep")
        return DRCStrategy(threads=1, mode="tiled", tile_size_um=DRC_TILE_SIZE_UM)

    def get_drc_deck_path(self, pdk: PDKConfig) -> Path:
        """Resolve the DRC deck file path for a PDK."""
        # Look in the PDK config directory
        pdk_dir = PDK_CONFIGS_DIR / pdk.name.lower().replace(" ", "_")
        deck_path = pdk_dir / pdk.klayout_drc_deck
        if not deck_path.exists():
            raise FileNotFoundError(
                f"DRC deck not found: {deck_path}. Expected '{pdk.klayout_drc_deck}' in {pdk_dir}"
            )
        return deck_path

    # SKY130 DRC deck defaults all rule groups to "false" — we enable them since
    # the whole point of this tool is to run all checks.
    DEFAULT_DRC_FLAGS: dict[str, str] = {
        "feol": "true",
        "beol": "true",
        "offgrid": "true",
        "floating_met": "true",
        "seal": "false",
    }

    def build_command(
        self,
        gds_path: Path,
        drc_deck_path: Path,
        report_path: Path,
        top_cell: str | None = None,
        strategy: DRCStrategy | None = None,
        drc_flags: dict[str, str] | None = None,
        pdk: PDKConfig | None = None,
    ) -> list[str]:
        """Build the klayout batch command.

        Command format:
            klayout -b -r <deck.drc> -rd input=<gds> -rd report=<report.lyrdb>
                    [-rd topcell=<name>] [-rd thr=<n>] [-rd drc_mode=<mode>]
                    [-rd tile_size=<um>] [-rd feol=true] ...

        Flag priority: per-call drc_flags > pdk.drc_flags > DEFAULT_DRC_FLAGS.
        """
        cmd = [
            self._binary,
            "-b",  # batch mode (no GUI)
            "-r",
            str(drc_deck_path),
            "-rd",
            f"input={gds_path}",
            "-rd",
            f"report={report_path}",
        ]
        if top_cell:
            cmd.extend(["-rd", f"topcell={top_cell}"])
        if strategy:
            cmd.extend(["-rd", f"thr={strategy.threads}"])
            cmd.extend(["-rd", f"drc_mode={strategy.mode}"])
            if strategy.mode == "tiled" and strategy.tile_size_um is not None:
                cmd.extend(["-rd", f"tile_size={strategy.tile_size_um}"])
        # Flag priority: per-call overrides > PDK-defined flags > class defaults
        base_flags = (pdk.drc_flags if pdk and pdk.drc_flags else self.DEFAULT_DRC_FLAGS)
        flags = {**base_flags, **(drc_flags or {})}
        for key, val in flags.items():
            cmd.extend(["-rd", f"{key}={val}"])
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

        # Select adaptive strategy based on file size
        strategy = self.adaptive_strategy(gds_path.stat().st_size)

        # Set up output directory
        use_temp = output_dir is None
        if use_temp:
            temp_dir = tempfile.mkdtemp(prefix="agentic_drc_")
            out_dir = Path(temp_dir)
        else:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

        report_path = out_dir / f"{gds_path.stem}_drc.lyrdb"

        cmd = self.build_command(gds_path, drc_deck_path, report_path, top_cell, strategy, pdk=pdk)

        # Throttle CPU with layered approach:
        #   1. taskpolicy -b  — macOS background QoS (efficiency cores, lowest priority)
        #   2. nice -n 10     — scheduling priority fallback (works on all Unix)
        #   3. cpulimit -l N  — hard duty-cycle cap via SIGSTOP/SIGCONT
        import platform

        if platform.system() == "Darwin" and shutil.which("taskpolicy"):
            cmd = ["taskpolicy", "-b"] + cmd
        cmd = ["nice", "-n", str(DRC_NICE_LEVEL)] + cmd

        start_time = time.monotonic()
        cpulimit_proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            logger.info("DRC started (pid %d, nice %d)", proc.pid, DRC_NICE_LEVEL)

            # Attach cpulimit for hard CPU cap if available
            cpulimit_bin = shutil.which("cpulimit")
            if cpulimit_bin and DRC_CPU_LIMIT_PERCENT < 100:
                try:
                    cpulimit_proc = subprocess.Popen(
                        [cpulimit_bin, "-p", str(proc.pid), "-l", str(DRC_CPU_LIMIT_PERCENT)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    logger.info("CPU capped at %d%% via cpulimit (pid %d)", DRC_CPU_LIMIT_PERCENT, proc.pid)
                except OSError:
                    pass

            try:
                stdout, stderr = proc.communicate(timeout=self._timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise DRCError(
                    f"DRC timed out after {self._timeout}s",
                    returncode=-1,
                    stderr="timeout",
                )
        except OSError as e:
            raise DRCError(
                f"Failed to execute KLayout: {e}",
                returncode=-1,
                stderr=str(e),
            )
        finally:
            if cpulimit_proc:
                cpulimit_proc.terminate()
                cpulimit_proc.wait()
        duration = time.monotonic() - start_time

        # KLayout returns 0 on success, even when violations are found
        if proc.returncode != 0:
            raise DRCError(
                f"KLayout DRC failed (exit code {proc.returncode}): {stderr}",
                returncode=proc.returncode,
                stderr=stderr,
            )

        # Parse the report
        if not report_path.exists():
            raise DRCError(
                "KLayout completed but no report file generated. "
                "Check that the DRC deck uses report() to output results.",
                returncode=proc.returncode,
                stderr=stderr,
            )

        report = self._parser.parse_file(report_path)
        if map_to_pdk:
            self._parser.map_to_pdk(report, pdk)

        return DRCResult(
            report=report,
            report_path=report_path,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            klayout_binary=self._binary,
            strategy=strategy,
        )

    async def async_run(
        self,
        gds_path: str | Path,
        pdk: PDKConfig,
        top_cell: str | None = None,
        output_dir: str | Path | None = None,
        map_to_pdk: bool = True,
    ) -> DRCResult:
        """Run DRC asynchronously — does not block the event loop.

        Same interface as run() but uses asyncio.create_subprocess_exec
        so the uvicorn worker thread stays free during long DRC runs.

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

        # Select adaptive strategy based on file size
        strategy = self.adaptive_strategy(gds_path.stat().st_size)

        # Set up output directory
        use_temp = output_dir is None
        if use_temp:
            temp_dir = tempfile.mkdtemp(prefix="agentic_drc_")
            out_dir = Path(temp_dir)
        else:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

        report_path = out_dir / f"{gds_path.stem}_drc.lyrdb"

        cmd = self.build_command(gds_path, drc_deck_path, report_path, top_cell, strategy, pdk=pdk)

        # Throttle CPU with layered approach
        import platform

        if platform.system() == "Darwin" and shutil.which("taskpolicy"):
            cmd = ["taskpolicy", "-b"] + cmd
        cmd = ["nice", "-n", str(DRC_NICE_LEVEL)] + cmd

        start_time = time.monotonic()
        cpulimit_proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info("DRC started async (pid %d, nice %d)", proc.pid, DRC_NICE_LEVEL)

            # Attach cpulimit for hard CPU cap if available
            cpulimit_bin = shutil.which("cpulimit")
            if cpulimit_bin and DRC_CPU_LIMIT_PERCENT < 100:
                try:
                    cpulimit_proc = subprocess.Popen(
                        [cpulimit_bin, "-p", str(proc.pid), "-l", str(DRC_CPU_LIMIT_PERCENT)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    logger.info(
                        "CPU capped at %d%% via cpulimit (pid %d)",
                        DRC_CPU_LIMIT_PERCENT,
                        proc.pid,
                    )
                except OSError:
                    pass

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout
                )
                stdout = stdout_bytes.decode() if stdout_bytes else ""
                stderr = stderr_bytes.decode() if stderr_bytes else ""
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise DRCError(
                    f"DRC timed out after {self._timeout}s",
                    returncode=-1,
                    stderr="timeout",
                )
        except OSError as e:
            raise DRCError(
                f"Failed to execute KLayout: {e}",
                returncode=-1,
                stderr=str(e),
            )
        finally:
            if cpulimit_proc:
                cpulimit_proc.terminate()
                cpulimit_proc.wait()
        duration = time.monotonic() - start_time

        if proc.returncode != 0:
            raise DRCError(
                f"KLayout DRC failed (exit code {proc.returncode}): {stderr}",
                returncode=proc.returncode,
                stderr=stderr,
            )

        if not report_path.exists():
            raise DRCError(
                "KLayout completed but no report file generated. "
                "Check that the DRC deck uses report() to output results.",
                returncode=proc.returncode,
                stderr=stderr,
            )

        report = self._parser.parse_file(report_path)
        if map_to_pdk:
            self._parser.map_to_pdk(report, pdk)

        return DRCResult(
            report=report,
            report_path=report_path,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            klayout_binary=self._binary,
            strategy=strategy,
        )

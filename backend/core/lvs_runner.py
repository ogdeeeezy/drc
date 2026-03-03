"""KLayout LVS runner — execute LVS checks via KLayout batch mode subprocess."""

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
    DRC_NICE_LEVEL,
    DRC_TIMEOUT_SECONDS,
    KLAYOUT_BINARY,
    PDK_CONFIGS_DIR,
)
from backend.pdk.schema import PDKConfig

logger = logging.getLogger(__name__)

# Default LVS timeout — LVS can be slower than DRC on complex designs
LVS_TIMEOUT_SECONDS = DRC_TIMEOUT_SECONDS  # 2700s (45 min)


class LVSError(Exception):
    """Raised when LVS execution fails."""

    def __init__(self, message: str, returncode: int = -1, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


@dataclass
class LVSResult:
    """Result of an LVS run."""

    report_path: Path
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    match: bool


class LVSRunner:
    """Execute KLayout LVS in batch mode as a subprocess.

    Usage:
        runner = LVSRunner()
        result = await runner.async_run(
            Path("layout.gds"), Path("circuit.spice"), pdk_config
        )
        print(f"LVS {'match' if result.match else 'mismatch'}")
    """

    def __init__(
        self,
        klayout_binary: str = KLAYOUT_BINARY,
        timeout: int = LVS_TIMEOUT_SECONDS,
    ):
        self._binary = klayout_binary
        self._timeout = timeout

    @property
    def binary(self) -> str:
        return self._binary

    def check_klayout_available(self) -> bool:
        """Check if KLayout binary is available."""
        if Path(self._binary).is_absolute():
            return Path(self._binary).exists()
        return shutil.which(self._binary) is not None

    def get_lvs_deck_path(self, pdk: PDKConfig) -> Path:
        """Resolve the LVS deck file path for a PDK."""
        if not hasattr(pdk, "klayout_lvs_deck") or not pdk.klayout_lvs_deck:
            raise FileNotFoundError(
                f"PDK '{pdk.name}' does not have an LVS deck configured. "
                "Set klayout_lvs_deck in pdk.json."
            )
        pdk_dir = PDK_CONFIGS_DIR / pdk.name.lower().replace(" ", "_")
        deck_path = pdk_dir / pdk.klayout_lvs_deck
        if not deck_path.exists():
            raise FileNotFoundError(
                f"LVS deck not found: {deck_path}. "
                f"Expected '{pdk.klayout_lvs_deck}' in {pdk_dir}"
            )
        return deck_path

    def build_command(
        self,
        gds_path: Path,
        netlist_path: Path,
        lvs_deck_path: Path,
        report_path: Path,
    ) -> list[str]:
        """Build the klayout LVS batch command.

        Command format:
            klayout -b -r <deck.lvs> -rd input=<gds> -rd schematic=<spice>
                    -rd report=<report.lvsdb>
        """
        return [
            self._binary,
            "-b",  # batch mode (no GUI)
            "-r",
            str(lvs_deck_path),
            "-rd",
            f"input={gds_path}",
            "-rd",
            f"schematic={netlist_path}",
            "-rd",
            f"report={report_path}",
        ]

    def run(
        self,
        gds_path: str | Path,
        netlist_path: str | Path,
        pdk: PDKConfig,
        output_dir: str | Path | None = None,
    ) -> LVSResult:
        """Run LVS on a GDSII file against a SPICE netlist.

        Args:
            gds_path: Path to input GDSII file.
            netlist_path: Path to SPICE netlist file.
            pdk: PDK configuration with LVS deck reference.
            output_dir: Directory for report output. Uses temp dir if None.

        Returns:
            LVSResult with report path and match status.

        Raises:
            LVSError: If KLayout is not available, LVS deck not found, or execution fails.
            FileNotFoundError: If GDSII or netlist file doesn't exist.
        """
        gds_path = Path(gds_path)
        netlist_path = Path(netlist_path)

        if not gds_path.exists():
            raise FileNotFoundError(f"GDSII file not found: {gds_path}")
        if not netlist_path.exists():
            raise FileNotFoundError(f"Netlist file not found: {netlist_path}")
        if not self.check_klayout_available():
            raise LVSError(
                f"KLayout binary '{self._binary}' not found. "
                "Install with: brew install klayout (macOS) or apt install klayout (Linux)"
            )

        lvs_deck_path = self.get_lvs_deck_path(pdk)

        # Set up output directory
        if output_dir is None:
            temp_dir = tempfile.mkdtemp(prefix="agentic_lvs_")
            out_dir = Path(temp_dir)
        else:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

        report_path = out_dir / f"{gds_path.stem}_lvs.lvsdb"
        cmd = self.build_command(gds_path, netlist_path, lvs_deck_path, report_path)

        # CPU throttling: same triple-layer as DRC
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
            logger.info("LVS started (pid %d, nice %d)", proc.pid, DRC_NICE_LEVEL)

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
                stdout, stderr = proc.communicate(timeout=self._timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise LVSError(
                    f"LVS timed out after {self._timeout}s",
                    returncode=-1,
                    stderr="timeout",
                )
        except OSError as e:
            raise LVSError(
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
            raise LVSError(
                f"KLayout LVS failed (exit code {proc.returncode}): {stderr}",
                returncode=proc.returncode,
                stderr=stderr,
            )

        if not report_path.exists():
            raise LVSError(
                "KLayout completed but no LVS report file generated. "
                "Check that the LVS deck writes a report to the specified path.",
                returncode=proc.returncode,
                stderr=stderr,
            )

        # Determine match status from return code (0 = success, report determines match)
        # We'll set match=True here; the parser (P5-LV-002) will refine this from the report
        return LVSResult(
            report_path=report_path,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            match=True,  # Placeholder; parser determines actual match status
        )

    async def async_run(
        self,
        gds_path: str | Path,
        netlist_path: str | Path,
        pdk: PDKConfig,
        output_dir: str | Path | None = None,
    ) -> LVSResult:
        """Run LVS asynchronously — does not block the event loop.

        Same interface as run() but uses asyncio.create_subprocess_exec.

        Args:
            gds_path: Path to input GDSII file.
            netlist_path: Path to SPICE netlist file.
            pdk: PDK configuration with LVS deck reference.
            output_dir: Directory for report output. Uses temp dir if None.

        Returns:
            LVSResult with report path and match status.

        Raises:
            LVSError: If KLayout is not available, LVS deck not found, or execution fails.
            FileNotFoundError: If GDSII or netlist file doesn't exist.
        """
        gds_path = Path(gds_path)
        netlist_path = Path(netlist_path)

        if not gds_path.exists():
            raise FileNotFoundError(f"GDSII file not found: {gds_path}")
        if not netlist_path.exists():
            raise FileNotFoundError(f"Netlist file not found: {netlist_path}")
        if not self.check_klayout_available():
            raise LVSError(
                f"KLayout binary '{self._binary}' not found. "
                "Install with: brew install klayout (macOS) or apt install klayout (Linux)"
            )

        lvs_deck_path = self.get_lvs_deck_path(pdk)

        # Set up output directory
        if output_dir is None:
            temp_dir = tempfile.mkdtemp(prefix="agentic_lvs_")
            out_dir = Path(temp_dir)
        else:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

        report_path = out_dir / f"{gds_path.stem}_lvs.lvsdb"
        cmd = self.build_command(gds_path, netlist_path, lvs_deck_path, report_path)

        # CPU throttling: same triple-layer as DRC
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
            logger.info("LVS started async (pid %d, nice %d)", proc.pid, DRC_NICE_LEVEL)

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
                raise LVSError(
                    f"LVS timed out after {self._timeout}s",
                    returncode=-1,
                    stderr="timeout",
                )
        except OSError as e:
            raise LVSError(
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
            raise LVSError(
                f"KLayout LVS failed (exit code {proc.returncode}): {stderr}",
                returncode=proc.returncode,
                stderr=stderr,
            )

        if not report_path.exists():
            raise LVSError(
                "KLayout completed but no LVS report file generated. "
                "Check that the LVS deck writes a report to the specified path.",
                returncode=proc.returncode,
                stderr=stderr,
            )

        return LVSResult(
            report_path=report_path,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            match=True,  # Placeholder; parser determines actual match status
        )

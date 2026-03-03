"""Tests for KLayout LVS runner — uses mocked subprocess since KLayout CLI may not be installed."""

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.lvs_runner import LVSError, LVSResult, LVSRunner
from backend.pdk.schema import (
    DesignRule,
    FixStrategyWeight,
    GDSLayer,
    PDKConfig,
    RuleType,
)


@pytest.fixture()
def pdk_config_with_lvs(tmp_path):
    """A minimal PDK config with LVS deck configured."""
    pdk_dir = tmp_path / "pdk" / "configs" / "test_pdk"
    pdk_dir.mkdir(parents=True)
    lvs_deck = pdk_dir / "test.lvs"
    lvs_deck.write_text("# stub LVS deck")
    drc_deck = pdk_dir / "test.drc"
    drc_deck.write_text("# stub DRC deck")

    return PDKConfig(
        name="test_pdk",
        version="1.0",
        process_node_nm=130,
        grid_um=0.005,
        layers={
            "met1": GDSLayer(
                gds_layer=68,
                gds_datatype=20,
                description="Metal 1",
                color="#0000FF",
                is_routing=True,
            ),
        },
        rules=[
            DesignRule(
                rule_id="m1.1",
                rule_type=RuleType.min_width,
                layer="met1",
                value_um=0.140,
                severity=7,
            ),
        ],
        connectivity=[],
        fix_weights={"min_width": FixStrategyWeight(priority=3)},
        klayout_drc_deck="test.drc",
        klayout_lvs_deck="test.lvs",
    )


@pytest.fixture()
def pdk_config_no_lvs(tmp_path):
    """A PDK config without LVS deck."""
    pdk_dir = tmp_path / "pdk" / "configs" / "test_pdk"
    pdk_dir.mkdir(parents=True)
    drc_deck = pdk_dir / "test.drc"
    drc_deck.write_text("# stub DRC deck")

    return PDKConfig(
        name="test_pdk",
        version="1.0",
        process_node_nm=130,
        grid_um=0.005,
        layers={
            "met1": GDSLayer(
                gds_layer=68,
                gds_datatype=20,
                description="Metal 1",
                color="#0000FF",
                is_routing=True,
            ),
        },
        rules=[],
        connectivity=[],
        fix_weights={},
        klayout_drc_deck="test.drc",
    )


@pytest.fixture()
def sample_gds(tmp_path):
    """Create a minimal GDSII file for testing."""
    import gdstk

    lib = gdstk.Library()
    cell = lib.new_cell("TOP")
    cell.add(gdstk.Polygon([(0, 0), (1, 0), (1, 1), (0, 1)], layer=68, datatype=20))
    gds_path = tmp_path / "test.gds"
    lib.write_gds(str(gds_path))
    return gds_path


@pytest.fixture()
def sample_netlist(tmp_path):
    """Create a minimal SPICE netlist file for testing."""
    netlist_path = tmp_path / "test.spice"
    netlist_path.write_text(
        "* Test inverter netlist\n"
        ".subckt INV VDD VSS IN OUT\n"
        "M1 OUT IN VDD VDD sky130_fd_pr__pfet_01v8 W=1u L=0.15u\n"
        "M2 OUT IN VSS VSS sky130_fd_pr__nfet_01v8 W=0.5u L=0.15u\n"
        ".ends INV\n"
    )
    return netlist_path


@pytest.fixture()
def lvsdb_content():
    """Sample .lvsdb XML content that KLayout would produce."""
    return '<?xml version="1.0" encoding="utf-8"?>\n<lvsdb/>\n'


class TestLVSRunnerInit:
    def test_default_binary(self):
        runner = LVSRunner()
        assert "klayout" in runner.binary.lower()

    def test_custom_binary(self):
        runner = LVSRunner(klayout_binary="/usr/local/bin/klayout")
        assert runner.binary == "/usr/local/bin/klayout"

    def test_custom_timeout(self):
        runner = LVSRunner(timeout=600)
        assert runner._timeout == 600


class TestLVSRunnerAvailability:
    @patch("shutil.which", return_value="/usr/local/bin/klayout")
    def test_available_returns_true(self, mock_which):
        runner = LVSRunner()
        assert runner.check_klayout_available() is True

    def test_unavailable_returns_false(self):
        runner = LVSRunner(klayout_binary="/nonexistent/path/to/klayout")
        assert runner.check_klayout_available() is False


class TestBuildLVSCommand:
    def test_basic_command(self):
        runner = LVSRunner(klayout_binary="klayout")
        cmd = runner.build_command(
            gds_path=Path("/tmp/test.gds"),
            netlist_path=Path("/tmp/test.spice"),
            lvs_deck_path=Path("/tmp/sky130.lvs"),
            report_path=Path("/tmp/report.lvsdb"),
        )
        assert cmd[0] == "klayout"
        assert "-b" in cmd
        assert "-r" in cmd
        assert str(Path("/tmp/sky130.lvs")) in cmd
        assert "input=/tmp/test.gds" in cmd
        assert "schematic=/tmp/test.spice" in cmd
        assert "report=/tmp/report.lvsdb" in cmd

    def test_all_rd_parameters_present(self):
        runner = LVSRunner(klayout_binary="klayout")
        cmd = runner.build_command(
            gds_path=Path("/tmp/layout.gds"),
            netlist_path=Path("/tmp/circuit.spice"),
            lvs_deck_path=Path("/tmp/deck.lvs"),
            report_path=Path("/tmp/out.lvsdb"),
        )
        # Verify -rd flags for each parameter
        rd_indices = [i for i, c in enumerate(cmd) if c == "-rd"]
        rd_values = [cmd[i + 1] for i in rd_indices]
        assert "input=/tmp/layout.gds" in rd_values
        assert "schematic=/tmp/circuit.spice" in rd_values
        assert "report=/tmp/out.lvsdb" in rd_values

    def test_custom_binary(self):
        runner = LVSRunner(klayout_binary="/opt/klayout/bin/klayout")
        cmd = runner.build_command(
            gds_path=Path("/tmp/test.gds"),
            netlist_path=Path("/tmp/test.spice"),
            lvs_deck_path=Path("/tmp/sky130.lvs"),
            report_path=Path("/tmp/report.lvsdb"),
        )
        assert cmd[0] == "/opt/klayout/bin/klayout"


class TestLVSDeckResolution:
    def test_deck_found(self, pdk_config_with_lvs, tmp_path):
        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            path = runner.get_lvs_deck_path(pdk_config_with_lvs)
            assert path.exists()
            assert path.name == "test.lvs"

    def test_deck_not_found(self, pdk_config_with_lvs, tmp_path):
        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "empty"):
            with pytest.raises(FileNotFoundError, match="LVS deck not found"):
                runner.get_lvs_deck_path(pdk_config_with_lvs)

    def test_no_lvs_deck_configured(self, pdk_config_no_lvs, tmp_path):
        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            with pytest.raises(FileNotFoundError, match="does not have an LVS deck"):
                runner.get_lvs_deck_path(pdk_config_no_lvs)


class TestLVSRunMocked:
    """Test LVS execution with mocked subprocess (no KLayout required)."""

    @patch("backend.core.lvs_runner.LVSRunner.check_klayout_available", return_value=True)
    @patch("subprocess.Popen")
    def test_successful_run(
        self,
        mock_popen,
        mock_avail,
        pdk_config_with_lvs,
        sample_gds,
        sample_netlist,
        lvsdb_content,
        tmp_path,
    ):
        def side_effect(cmd, **kwargs):
            for arg in cmd:
                if arg.startswith("report="):
                    rpath = Path(arg.split("=", 1)[1])
                    rpath.write_text(lvsdb_content)
                    break
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = ("", "")
            return mock_proc

        mock_popen.side_effect = side_effect

        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            result = runner.run(
                sample_gds, sample_netlist, pdk_config_with_lvs, output_dir=tmp_path
            )

        assert result.returncode == 0
        assert result.report_path.exists()
        assert result.duration_seconds >= 0

    @patch("backend.core.lvs_runner.LVSRunner.check_klayout_available", return_value=True)
    @patch("subprocess.Popen")
    def test_command_built_correctly(
        self,
        mock_popen,
        mock_avail,
        pdk_config_with_lvs,
        sample_gds,
        sample_netlist,
        lvsdb_content,
        tmp_path,
    ):
        """Verify the subprocess command includes all -rd parameters."""
        captured_cmd = []

        def side_effect(cmd, **kwargs):
            captured_cmd.extend(cmd)
            for arg in cmd:
                if arg.startswith("report="):
                    rpath = Path(arg.split("=", 1)[1])
                    rpath.write_text(lvsdb_content)
                    break
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = ("", "")
            return mock_proc

        mock_popen.side_effect = side_effect

        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            runner.run(sample_gds, sample_netlist, pdk_config_with_lvs, output_dir=tmp_path)

        # Check that the command includes all expected -rd parameters
        assert any(f"input={sample_gds}" in arg for arg in captured_cmd)
        assert any(f"schematic={sample_netlist}" in arg for arg in captured_cmd)
        assert any("report=" in arg for arg in captured_cmd)

    @patch("backend.core.lvs_runner.LVSRunner.check_klayout_available", return_value=False)
    def test_klayout_not_available(
        self, mock_avail, pdk_config_with_lvs, sample_gds, sample_netlist
    ):
        runner = LVSRunner()
        with pytest.raises(LVSError, match="not found"):
            runner.run(sample_gds, sample_netlist, pdk_config_with_lvs)

    def test_gds_not_found(self, pdk_config_with_lvs, sample_netlist):
        runner = LVSRunner()
        with pytest.raises(FileNotFoundError, match="GDSII file not found"):
            runner.run(Path("/nonexistent/file.gds"), sample_netlist, pdk_config_with_lvs)

    def test_netlist_not_found(self, pdk_config_with_lvs, sample_gds):
        runner = LVSRunner()
        with pytest.raises(FileNotFoundError, match="Netlist file not found"):
            runner.run(sample_gds, Path("/nonexistent/file.spice"), pdk_config_with_lvs)

    @patch("backend.core.lvs_runner.LVSRunner.check_klayout_available", return_value=True)
    @patch("subprocess.Popen")
    def test_klayout_failure(
        self, mock_popen, mock_avail, pdk_config_with_lvs, sample_gds, sample_netlist, tmp_path
    ):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = ("", "LVS script error")
        mock_popen.return_value = mock_proc

        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            with pytest.raises(LVSError, match="failed"):
                runner.run(
                    sample_gds, sample_netlist, pdk_config_with_lvs, output_dir=tmp_path
                )

    @patch("backend.core.lvs_runner.LVSRunner.check_klayout_available", return_value=True)
    @patch("subprocess.Popen")
    def test_timeout(
        self, mock_popen, mock_avail, pdk_config_with_lvs, sample_gds, sample_netlist, tmp_path
    ):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="klayout", timeout=300)
        mock_popen.return_value = mock_proc

        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            with pytest.raises(LVSError, match="timed out"):
                runner.run(
                    sample_gds, sample_netlist, pdk_config_with_lvs, output_dir=tmp_path
                )

    @patch("backend.core.lvs_runner.LVSRunner.check_klayout_available", return_value=True)
    @patch("subprocess.Popen")
    def test_no_report_generated(
        self, mock_popen, mock_avail, pdk_config_with_lvs, sample_gds, sample_netlist, tmp_path
    ):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = ("", "")
        mock_popen.return_value = mock_proc

        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            with pytest.raises(LVSError, match="no LVS report file"):
                runner.run(
                    sample_gds, sample_netlist, pdk_config_with_lvs, output_dir=tmp_path
                )


class TestLVSResult:
    def test_result_attributes(self):
        result = LVSResult(
            report_path=Path("/tmp/test.lvsdb"),
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=1.5,
            match=True,
        )
        assert result.match is True
        assert result.returncode == 0
        assert result.duration_seconds == 1.5


class TestLVSError:
    def test_error_attributes(self):
        err = LVSError("test failure", returncode=1, stderr="details")
        assert str(err) == "test failure"
        assert err.returncode == 1
        assert err.stderr == "details"

    def test_defaults(self):
        err = LVSError("simple")
        assert err.returncode == -1
        assert err.stderr == ""


class TestAsyncLVSRun:
    """Test async LVS execution with mocked asyncio subprocess."""

    @patch("backend.core.lvs_runner.LVSRunner.check_klayout_available", return_value=True)
    @patch("asyncio.create_subprocess_exec")
    async def test_successful_async_run(
        self,
        mock_create_subprocess,
        mock_avail,
        pdk_config_with_lvs,
        sample_gds,
        sample_netlist,
        lvsdb_content,
        tmp_path,
    ):
        async def side_effect(*cmd, **kwargs):
            for arg in cmd:
                if isinstance(arg, str) and arg.startswith("report="):
                    rpath = Path(arg.split("=", 1)[1])
                    rpath.write_text(lvsdb_content)
                    break
            mock_proc = AsyncMock()
            mock_proc.pid = 12345
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.kill = AsyncMock()
            mock_proc.wait = AsyncMock()
            return mock_proc

        mock_create_subprocess.side_effect = side_effect

        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            result = await runner.async_run(
                sample_gds, sample_netlist, pdk_config_with_lvs, output_dir=tmp_path
            )

        assert result.returncode == 0
        assert result.report_path.exists()
        assert result.duration_seconds >= 0

    @patch("backend.core.lvs_runner.LVSRunner.check_klayout_available", return_value=False)
    async def test_klayout_not_available_async(
        self, mock_avail, pdk_config_with_lvs, sample_gds, sample_netlist
    ):
        runner = LVSRunner()
        with pytest.raises(LVSError, match="not found"):
            await runner.async_run(sample_gds, sample_netlist, pdk_config_with_lvs)

    async def test_gds_not_found_async(self, pdk_config_with_lvs, sample_netlist):
        runner = LVSRunner()
        with pytest.raises(FileNotFoundError, match="GDSII file not found"):
            await runner.async_run(
                Path("/nonexistent/file.gds"), sample_netlist, pdk_config_with_lvs
            )

    async def test_netlist_not_found_async(self, pdk_config_with_lvs, sample_gds):
        runner = LVSRunner()
        with pytest.raises(FileNotFoundError, match="Netlist file not found"):
            await runner.async_run(
                sample_gds, Path("/nonexistent/file.spice"), pdk_config_with_lvs
            )

    @patch("backend.core.lvs_runner.LVSRunner.check_klayout_available", return_value=True)
    @patch("asyncio.create_subprocess_exec")
    async def test_timeout_async(
        self,
        mock_create_subprocess,
        mock_avail,
        pdk_config_with_lvs,
        sample_gds,
        sample_netlist,
        tmp_path,
    ):
        async def side_effect(*cmd, **kwargs):
            mock_proc = AsyncMock()
            mock_proc.pid = 12345
            mock_proc.communicate.side_effect = asyncio.TimeoutError()
            mock_proc.kill = MagicMock()
            return mock_proc

        mock_create_subprocess.side_effect = side_effect

        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            with pytest.raises(LVSError, match="timed out"):
                await runner.async_run(
                    sample_gds, sample_netlist, pdk_config_with_lvs, output_dir=tmp_path
                )

    @patch("backend.core.lvs_runner.LVSRunner.check_klayout_available", return_value=True)
    @patch("asyncio.create_subprocess_exec")
    async def test_klayout_failure_async(
        self,
        mock_create_subprocess,
        mock_avail,
        pdk_config_with_lvs,
        sample_gds,
        sample_netlist,
        tmp_path,
    ):
        async def side_effect(*cmd, **kwargs):
            mock_proc = AsyncMock()
            mock_proc.pid = 12345
            mock_proc.returncode = 1
            mock_proc.communicate.return_value = (b"", b"LVS script error")
            return mock_proc

        mock_create_subprocess.side_effect = side_effect

        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            with pytest.raises(LVSError, match="failed"):
                await runner.async_run(
                    sample_gds, sample_netlist, pdk_config_with_lvs, output_dir=tmp_path
                )

    @patch("backend.core.lvs_runner.LVSRunner.check_klayout_available", return_value=True)
    @patch("asyncio.create_subprocess_exec")
    async def test_no_report_generated_async(
        self,
        mock_create_subprocess,
        mock_avail,
        pdk_config_with_lvs,
        sample_gds,
        sample_netlist,
        tmp_path,
    ):
        async def side_effect(*cmd, **kwargs):
            mock_proc = AsyncMock()
            mock_proc.pid = 12345
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"", b"")
            return mock_proc

        mock_create_subprocess.side_effect = side_effect

        runner = LVSRunner()
        with patch("backend.core.lvs_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            with pytest.raises(LVSError, match="no LVS report file"):
                await runner.async_run(
                    sample_gds, sample_netlist, pdk_config_with_lvs, output_dir=tmp_path
                )

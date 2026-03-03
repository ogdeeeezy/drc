"""Tests for KLayout DRC runner — uses mocked subprocess since KLayout CLI may not be installed."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.config import DRC_LARGE_THRESHOLD, DRC_SMALL_THRESHOLD, DRCStrategy
from backend.core.drc_runner import DRCError, DRCResult, DRCRunner
from backend.pdk.schema import (
    DesignRule,
    FixStrategyWeight,
    GDSLayer,
    PDKConfig,
    RuleType,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
LYRDB_DIR = FIXTURES_DIR / "lyrdb"


@pytest.fixture()
def pdk_config(tmp_path):
    """A minimal PDK config for testing."""
    # Create a fake DRC deck file
    pdk_dir = tmp_path / "pdk" / "configs" / "test_pdk"
    pdk_dir.mkdir(parents=True)
    deck = pdk_dir / "test.drc"
    deck.write_text("# stub DRC deck")

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
def lyrdb_content():
    """Sample .lyrdb content that KLayout would produce."""
    return (LYRDB_DIR / "sky130_inv_violations.lyrdb").read_text()


class TestDRCRunnerInit:
    def test_default_binary(self):
        runner = DRCRunner()
        # KLAYOUT_BINARY resolves to app bundle path if installed, or bare "klayout"
        assert "klayout" in runner.binary.lower()

    def test_custom_binary(self):
        runner = DRCRunner(klayout_binary="/usr/local/bin/klayout")
        assert runner.binary == "/usr/local/bin/klayout"


class TestDRCRunnerAvailability:
    def test_check_available(self):
        runner = DRCRunner()
        # We can't guarantee KLayout is installed, just test the method works
        result = runner.check_klayout_available()
        assert isinstance(result, bool)

    @patch("shutil.which", return_value="/usr/local/bin/klayout")
    def test_available_returns_true(self, mock_which):
        runner = DRCRunner()
        assert runner.check_klayout_available() is True

    def test_unavailable_returns_false(self):
        runner = DRCRunner(klayout_binary="/nonexistent/path/to/klayout")
        assert runner.check_klayout_available() is False


class TestBuildCommand:
    def test_basic_command(self):
        runner = DRCRunner(klayout_binary="klayout")
        cmd = runner.build_command(
            gds_path=Path("/tmp/test.gds"),
            drc_deck_path=Path("/tmp/sky130.drc"),
            report_path=Path("/tmp/report.lyrdb"),
        )
        # Core args
        assert cmd[0] == "klayout"
        assert "-b" in cmd
        assert "input=/tmp/test.gds" in cmd
        assert "report=/tmp/report.lyrdb" in cmd
        # Default DRC flags are included
        assert "feol=true" in cmd
        assert "beol=true" in cmd
        assert "offgrid=true" in cmd

    def test_with_top_cell(self):
        runner = DRCRunner()
        cmd = runner.build_command(
            gds_path=Path("/tmp/test.gds"),
            drc_deck_path=Path("/tmp/sky130.drc"),
            report_path=Path("/tmp/report.lyrdb"),
            top_cell="INV",
        )
        assert "-rd" in cmd
        assert "topcell=INV" in cmd

    def test_custom_binary(self):
        runner = DRCRunner(klayout_binary="/opt/klayout/bin/klayout")
        cmd = runner.build_command(
            gds_path=Path("/tmp/test.gds"),
            drc_deck_path=Path("/tmp/sky130.drc"),
            report_path=Path("/tmp/report.lyrdb"),
        )
        assert cmd[0] == "/opt/klayout/bin/klayout"

    def test_custom_drc_flags(self):
        """Custom flags override defaults."""
        runner = DRCRunner(klayout_binary="klayout")
        cmd = runner.build_command(
            gds_path=Path("/tmp/test.gds"),
            drc_deck_path=Path("/tmp/sky130.drc"),
            report_path=Path("/tmp/report.lyrdb"),
            drc_flags={"feol": "false", "seal": "true"},
        )
        assert "feol=false" in cmd
        assert "seal=true" in cmd


class TestDRCDeckResolution:
    def test_deck_found(self, pdk_config, tmp_path):
        runner = DRCRunner()
        with patch("backend.core.drc_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            path = runner.get_drc_deck_path(pdk_config)
            assert path.exists()
            assert path.name == "test.drc"

    def test_deck_not_found(self, pdk_config, tmp_path):
        runner = DRCRunner()
        with patch("backend.core.drc_runner.PDK_CONFIGS_DIR", tmp_path / "empty"):
            with pytest.raises(FileNotFoundError, match="DRC deck not found"):
                runner.get_drc_deck_path(pdk_config)


class TestDRCRunMocked:
    """Test DRC execution with mocked subprocess (no KLayout required)."""

    @patch("backend.core.drc_runner.DRCRunner.check_klayout_available", return_value=True)
    @patch("subprocess.Popen")
    def test_successful_run(
        self, mock_popen, mock_avail, pdk_config, sample_gds, lyrdb_content, tmp_path
    ):
        # Set up the mock: klayout "runs" and produces a .lyrdb file
        def side_effect(cmd, **kwargs):
            # Simulate KLayout writing a report file
            for arg in cmd:
                if arg.startswith("report="):
                    rpath = Path(arg.split("=", 1)[1])
                    rpath.write_text(lyrdb_content)
                    break
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = ("", "")
            return mock_proc

        mock_popen.side_effect = side_effect

        runner = DRCRunner()
        with patch("backend.core.drc_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            # Create fake DRC deck
            deck_dir = tmp_path / "pdk" / "configs" / "test_pdk"
            deck_dir.mkdir(parents=True, exist_ok=True)
            (deck_dir / "test.drc").write_text("# stub")

            result = runner.run(sample_gds, pdk_config, output_dir=tmp_path, map_to_pdk=False)

        assert result.returncode == 0
        assert result.has_violations is True
        assert result.report.total_violations == 6
        assert result.duration_seconds >= 0
        assert "m1.1" in result.violation_summary

    @patch("backend.core.drc_runner.DRCRunner.check_klayout_available", return_value=False)
    def test_klayout_not_available(self, mock_avail, pdk_config, sample_gds):
        runner = DRCRunner()
        with pytest.raises(DRCError, match="not found"):
            runner.run(sample_gds, pdk_config)

    def test_gds_not_found(self, pdk_config):
        runner = DRCRunner()
        with pytest.raises(FileNotFoundError, match="GDSII file not found"):
            runner.run(Path("/nonexistent/file.gds"), pdk_config)

    @patch("backend.core.drc_runner.DRCRunner.check_klayout_available", return_value=True)
    @patch("subprocess.Popen")
    def test_klayout_failure(self, mock_popen, mock_avail, pdk_config, sample_gds, tmp_path):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = ("", "DRC script error")
        mock_popen.return_value = mock_proc
        runner = DRCRunner()
        with patch("backend.core.drc_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            deck_dir = tmp_path / "pdk" / "configs" / "test_pdk"
            deck_dir.mkdir(parents=True, exist_ok=True)
            (deck_dir / "test.drc").write_text("# stub")

            with pytest.raises(DRCError, match="failed"):
                runner.run(sample_gds, pdk_config, output_dir=tmp_path)

    @patch("backend.core.drc_runner.DRCRunner.check_klayout_available", return_value=True)
    @patch("subprocess.Popen")
    def test_timeout(self, mock_popen, mock_avail, pdk_config, sample_gds, tmp_path):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="klayout", timeout=300)
        mock_popen.return_value = mock_proc

        runner = DRCRunner()
        with patch("backend.core.drc_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            deck_dir = tmp_path / "pdk" / "configs" / "test_pdk"
            deck_dir.mkdir(parents=True, exist_ok=True)
            (deck_dir / "test.drc").write_text("# stub")

            with pytest.raises(DRCError, match="timed out"):
                runner.run(sample_gds, pdk_config, output_dir=tmp_path)

    @patch("backend.core.drc_runner.DRCRunner.check_klayout_available", return_value=True)
    @patch("subprocess.Popen")
    def test_no_report_generated(self, mock_popen, mock_avail, pdk_config, sample_gds, tmp_path):
        # KLayout succeeds but no report file created
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = ("", "")
        mock_popen.return_value = mock_proc
        runner = DRCRunner()
        with patch("backend.core.drc_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            deck_dir = tmp_path / "pdk" / "configs" / "test_pdk"
            deck_dir.mkdir(parents=True, exist_ok=True)
            (deck_dir / "test.drc").write_text("# stub")

            with pytest.raises(DRCError, match="no report file"):
                runner.run(sample_gds, pdk_config, output_dir=tmp_path)


class TestDRCResult:
    def test_violation_summary(self):
        from backend.core.violation_models import (
            DRCReport,
            EdgePair,
            GeometryType,
            Violation,
            ViolationGeometry,
        )

        report = DRCReport(
            description="test",
            original_file="",
            generator="",
            top_cell="TOP",
            violations=[
                Violation(
                    category="m1.1",
                    description="width",
                    cell_name="TOP",
                    geometries=[
                        ViolationGeometry(
                            geometry_type=GeometryType.edge_pair,
                            edge_pair=EdgePair((0, 0), (1, 0), (0, 1), (1, 1)),
                        ),
                        ViolationGeometry(
                            geometry_type=GeometryType.edge_pair,
                            edge_pair=EdgePair((2, 2), (3, 2), (2, 3), (3, 3)),
                        ),
                    ],
                ),
                Violation(
                    category="m1.2",
                    description="spacing",
                    cell_name="TOP",
                    geometries=[
                        ViolationGeometry(
                            geometry_type=GeometryType.edge_pair,
                            edge_pair=EdgePair((5, 5), (6, 5), (5, 6), (6, 6)),
                        ),
                    ],
                ),
            ],
        )
        result = DRCResult(
            report=report,
            report_path=Path("/tmp/test.lyrdb"),
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=1.5,
            klayout_binary="klayout",
        )
        assert result.has_violations is True
        assert result.violation_summary == {"m1.1": 2, "m1.2": 1}

    def test_no_violations(self):
        from backend.core.violation_models import DRCReport

        report = DRCReport(description="clean", original_file="", generator="", top_cell="TOP")
        result = DRCResult(
            report=report,
            report_path=Path("/tmp/test.lyrdb"),
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=0.5,
            klayout_binary="klayout",
        )
        assert result.has_violations is False
        assert result.violation_summary == {}


class TestDRCError:
    def test_error_attributes(self):
        err = DRCError("test failure", returncode=1, stderr="details")
        assert str(err) == "test failure"
        assert err.returncode == 1
        assert err.stderr == "details"

    def test_defaults(self):
        err = DRCError("simple")
        assert err.returncode == -1
        assert err.stderr == ""


class TestAdaptiveStrategy:
    """Test adaptive DRC strategy selection based on file size."""

    def test_small_file_deep_4_threads(self):
        """< 20 MB → deep mode, 4 threads."""
        strategy = DRCRunner.adaptive_strategy(10 * 1024 * 1024)  # 10 MB
        assert strategy.mode == "deep"
        assert strategy.threads == 4
        assert strategy.tile_size_um is None

    def test_medium_file_deep_2_threads(self):
        """20-80 MB → deep mode, 2 threads."""
        strategy = DRCRunner.adaptive_strategy(50 * 1024 * 1024)  # 50 MB
        assert strategy.mode == "deep"
        assert strategy.threads == 2
        assert strategy.tile_size_um is None

    def test_large_file_tiled_1_thread(self):
        """> 80 MB → tiled mode, 1 thread."""
        strategy = DRCRunner.adaptive_strategy(100 * 1024 * 1024)  # 100 MB
        assert strategy.mode == "tiled"
        assert strategy.threads == 1
        assert strategy.tile_size_um == 1000.0

    def test_boundary_small_to_medium(self):
        """Exactly 20 MB → medium tier (20-80 MB)."""
        strategy = DRCRunner.adaptive_strategy(DRC_SMALL_THRESHOLD)
        assert strategy.mode == "deep"
        assert strategy.threads == 2

    def test_boundary_medium_to_large(self):
        """Exactly 80 MB → large tier (> 80 MB)."""
        strategy = DRCRunner.adaptive_strategy(DRC_LARGE_THRESHOLD)
        assert strategy.mode == "tiled"
        assert strategy.threads == 1

    def test_zero_size(self):
        """0 bytes → small tier."""
        strategy = DRCRunner.adaptive_strategy(0)
        assert strategy.mode == "deep"
        assert strategy.threads == 4

    def test_just_under_small_threshold(self):
        strategy = DRCRunner.adaptive_strategy(DRC_SMALL_THRESHOLD - 1)
        assert strategy.mode == "deep"
        assert strategy.threads == 4


class TestBuildCommandWithStrategy:
    """Test command building with adaptive strategy parameters."""

    def test_deep_strategy(self):
        runner = DRCRunner()
        strategy = DRCStrategy(threads=4, mode="deep")
        cmd = runner.build_command(
            gds_path=Path("/tmp/test.gds"),
            drc_deck_path=Path("/tmp/sky130.drc"),
            report_path=Path("/tmp/report.lyrdb"),
            strategy=strategy,
        )
        assert "thr=4" in cmd
        assert "drc_mode=deep" in cmd
        # No tile_size for deep mode
        assert all("tile_size=" not in arg for arg in cmd)

    def test_tiled_strategy(self):
        runner = DRCRunner()
        strategy = DRCStrategy(threads=1, mode="tiled", tile_size_um=1000.0)
        cmd = runner.build_command(
            gds_path=Path("/tmp/test.gds"),
            drc_deck_path=Path("/tmp/sky130.drc"),
            report_path=Path("/tmp/report.lyrdb"),
            strategy=strategy,
        )
        assert "thr=1" in cmd
        assert "drc_mode=tiled" in cmd
        assert "tile_size=1000.0" in cmd

    def test_no_strategy(self):
        """Without strategy, no thr/drc_mode params are added (backward compat)."""
        runner = DRCRunner()
        cmd = runner.build_command(
            gds_path=Path("/tmp/test.gds"),
            drc_deck_path=Path("/tmp/sky130.drc"),
            report_path=Path("/tmp/report.lyrdb"),
        )
        assert all("thr=" not in arg for arg in cmd)
        assert all("drc_mode=" not in arg for arg in cmd)
        # But DRC flags are still present
        assert "feol=true" in cmd

    def test_strategy_with_top_cell(self):
        runner = DRCRunner()
        strategy = DRCStrategy(threads=2, mode="deep")
        cmd = runner.build_command(
            gds_path=Path("/tmp/test.gds"),
            drc_deck_path=Path("/tmp/sky130.drc"),
            report_path=Path("/tmp/report.lyrdb"),
            top_cell="INV",
            strategy=strategy,
        )
        assert "topcell=INV" in cmd
        assert "thr=2" in cmd
        assert "drc_mode=deep" in cmd


class TestRunIncludesStrategy:
    """Verify that run() populates strategy in the result."""

    @patch("backend.core.drc_runner.DRCRunner.check_klayout_available", return_value=True)
    @patch("subprocess.Popen")
    def test_result_has_strategy(
        self, mock_popen, mock_avail, pdk_config, sample_gds, lyrdb_content, tmp_path
    ):
        def side_effect(cmd, **kwargs):
            for arg in cmd:
                if arg.startswith("report="):
                    Path(arg.split("=", 1)[1]).write_text(lyrdb_content)
                    break
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = ("", "")
            return mock_proc

        mock_popen.side_effect = side_effect

        runner = DRCRunner()
        with patch("backend.core.drc_runner.PDK_CONFIGS_DIR", tmp_path / "pdk" / "configs"):
            deck_dir = tmp_path / "pdk" / "configs" / "test_pdk"
            deck_dir.mkdir(parents=True, exist_ok=True)
            (deck_dir / "test.drc").write_text("# stub")

            result = runner.run(sample_gds, pdk_config, output_dir=tmp_path, map_to_pdk=False)

        assert result.strategy is not None
        # sample_gds is tiny, so should be small tier
        assert result.strategy.mode == "deep"
        assert result.strategy.threads == 4

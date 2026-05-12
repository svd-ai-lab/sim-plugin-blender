from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sim_plugin_blender import BlenderDriver


FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_detects_blender_python_script() -> None:
    assert BlenderDriver().detect(FIXTURES / "blender_ok.py") is True


def test_rejects_ordinary_python_script() -> None:
    assert BlenderDriver().detect(FIXTURES / "not_blender.py") is False


def test_missing_detect_returns_false(tmp_path: Path) -> None:
    assert BlenderDriver().detect(tmp_path / "missing.py") is False


def test_lint_parses_python() -> None:
    result = BlenderDriver().lint(FIXTURES / "blender_ok.py")
    assert result.ok is True


def test_lint_missing_file_returns_diagnostic(tmp_path: Path) -> None:
    result = BlenderDriver().lint(tmp_path / "missing.py")
    assert result.ok is False
    assert result.diagnostics


def test_parse_output_uses_last_json_line() -> None:
    parsed = BlenderDriver().parse_output('noise\n{"a": 1}\n{"b": 2}\n')
    assert parsed == {"b": 2}


def test_connect_not_installed(monkeypatch) -> None:
    from sim_plugin_blender import driver as drv

    monkeypatch.setattr(drv, "_INSTALL_FINDERS", [lambda: []])
    info = BlenderDriver().connect()
    assert info.status == "not_installed"


def test_make_install_records_version(monkeypatch, tmp_path: Path) -> None:
    from sim_plugin_blender import driver as drv

    exe = tmp_path / "blender.exe"
    exe.write_text("fake exe")
    monkeypatch.setattr(drv, "_probe_version", lambda _exe, timeout_s=15.0: "5.1.1")

    install = drv._make_install(exe, "test")

    assert install is not None
    assert install.version == "5.1.1"


def test_run_file_constructs_background_command(monkeypatch) -> None:
    from sim_plugin_blender import driver as drv

    monkeypatch.setattr(drv.BlenderDriver, "_selected_executable", lambda self: "/usr/bin/blender")
    recorded = {}

    def fake_run(command, capture_output, text):
        recorded["command"] = command
        return SimpleNamespace(returncode=0, stdout='{"status":"ok"}\n', stderr="")

    monkeypatch.setattr("sim.runner.subprocess.run", fake_run)
    result = BlenderDriver().run_file(FIXTURES / "blender_ok.py")
    assert result.exit_code == 0
    assert recorded["command"] == [
        "/usr/bin/blender",
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(FIXTURES / "blender_ok.py"),
    ]


def test_launch_constructs_cli_bridge_command(monkeypatch, tmp_path: Path) -> None:
    from sim_plugin_blender import driver as drv

    class FakeProcess:
        pid = 1234
        returncode = None

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

    recorded = {}

    def fake_popen(command, stdout, stderr, cwd, text):
        recorded["command"] = command
        recorded["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr(drv.BlenderDriver, "_selected_executable", lambda self: "/usr/bin/blender")
    monkeypatch.setattr(drv.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(drv.BlenderDriver, "_wait_for_bridge", lambda self, timeout_s: None)
    monkeypatch.setattr(drv.BlenderDriver, "health", lambda self: {"ok": True, "connected": True})

    driver = BlenderDriver()
    info = driver.launch(ui_mode="gui", workspace=str(tmp_path), port=9876)
    command = recorded["command"]

    assert info["ok"] is True
    assert command[0] == "/usr/bin/blender"
    assert "--background" not in command
    assert "--python-exit-code" in command
    assert "--python" in command
    assert "--" in command
    assert "--sim-port" in command
    assert "9876" in command


def test_launch_headless_adds_background(monkeypatch, tmp_path: Path) -> None:
    from sim_plugin_blender import driver as drv

    class FakeProcess:
        pid = 1234

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    recorded = {}
    monkeypatch.setattr(drv.BlenderDriver, "_selected_executable", lambda self: "/usr/bin/blender")

    def fake_popen(command, **kwargs):
        recorded["command"] = command
        return FakeProcess()

    monkeypatch.setattr(drv.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(drv.BlenderDriver, "_wait_for_bridge", lambda self, timeout_s: None)
    monkeypatch.setattr(drv.BlenderDriver, "health", lambda self: {"ok": True, "connected": True})

    BlenderDriver().launch(ui_mode="no_gui", workspace=str(tmp_path), port=9877)
    assert "--background" in recorded["command"]

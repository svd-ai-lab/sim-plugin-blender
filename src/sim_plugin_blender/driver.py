"""Blender driver for sim-cli.

The driver is import-safe: it never imports ``bpy``. Live editing is provided
by launching Blender with the packaged bridge script via Blender's documented
command-line Python bootstrap.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Callable

from sim.driver import ConnectionInfo, Diagnostic, LintResult, RunResult, SolverInstall
from sim.runner import run_subprocess


_PY_SUFFIX = ".py"
_BLEND_SUFFIX = ".blend"
_ACCEPTED_SUFFIXES = (_PY_SUFFIX, _BLEND_SUFFIX)
_DEFAULT_BRIDGE_TIMEOUT_S = 300.0


def _is_executable_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _candidates_from_env_exe() -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    for var in ("SIM_BLENDER_EXE", "BLENDER_EXE"):
        value = os.environ.get(var)
        if value:
            out.append((Path(value), f"env:{var}"))
    return out


def _root_binary_candidates(root: Path) -> list[Path]:
    return [
        root / "blender",
        root / "blender.exe",
        root / "Blender",
        root / "Contents" / "MacOS" / "Blender",
        root / "Blender.app" / "Contents" / "MacOS" / "Blender",
    ]


def _candidates_from_env_root() -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    for var in ("SIM_BLENDER_ROOT", "BLENDER_ROOT"):
        value = os.environ.get(var)
        if not value:
            continue
        root = Path(value)
        for candidate in _root_binary_candidates(root):
            out.append((candidate, f"env:{var}"))
    return out


def _candidates_from_path() -> list[tuple[Path, str]]:
    exe = shutil.which("blender")
    return [(Path(exe), "path:blender")] if exe else []


def _candidates_from_macos_defaults() -> list[tuple[Path, str]]:
    return [
        (
            Path("/Applications/Blender.app/Contents/MacOS/Blender"),
            "default-path:/Applications/Blender.app",
        )
    ]


def _candidates_from_windows_defaults() -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    bases = [
        Path(r"C:\Program Files\Blender Foundation"),
        Path(r"C:\Program Files (x86)\Blender Foundation"),
    ]
    for base in bases:
        try:
            children = sorted(base.glob("Blender*"), reverse=True)
        except OSError:
            continue
        for child in children:
            out.append((child / "blender.exe", f"default-path:{base}"))
    return out


def _candidates_from_linux_defaults() -> list[tuple[Path, str]]:
    return [
        (Path("/usr/bin/blender"), "default-path:/usr/bin"),
        (Path("/usr/local/bin/blender"), "default-path:/usr/local/bin"),
        (Path("/snap/bin/blender"), "default-path:/snap/bin"),
    ]


_INSTALL_FINDERS: list[Callable[[], list[tuple[Path, str]]]] = [
    _candidates_from_env_exe,
    _candidates_from_env_root,
    _candidates_from_path,
    _candidates_from_macos_defaults,
    _candidates_from_windows_defaults,
    _candidates_from_linux_defaults,
]


def _make_install(exe: Path, source: str) -> SolverInstall | None:
    if not _is_executable_file(exe):
        return None
    try:
        resolved = exe.resolve()
    except OSError:
        resolved = exe
    return SolverInstall(
        name="blender",
        version=_probe_version(str(resolved), timeout_s=5.0) or "unknown",
        path=str(resolved.parent),
        source=source,
        extra={"exe": str(resolved)},
    )


def _scan_blender_installs() -> list[SolverInstall]:
    found: dict[str, SolverInstall] = {}
    for finder in _INSTALL_FINDERS:
        try:
            candidates = finder()
        except Exception:
            continue
        for exe, source in candidates:
            inst = _make_install(exe, source)
            if inst is None:
                continue
            key = inst.extra["exe"]
            found.setdefault(key, inst)
    return list(found.values())


def _parse_version(stdout: str) -> str | None:
    match = re.search(r"Blender\s+([0-9][^\s]*)", stdout)
    return match.group(1) if match else None


def _probe_version(exe: str, timeout_s: float = 15.0) -> str | None:
    try:
        proc = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except Exception:
        return None
    return _parse_version((proc.stdout or "") + "\n" + (proc.stderr or ""))


def _json_line_tail(stdout: str) -> dict:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _tail(path: Path | None, limit: int = 4000) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]


class BlenderDriver:
    """Blender driver with one-shot and persistent live-editing support."""

    def __init__(self) -> None:
        self._session_id: str | None = None
        self._host = "127.0.0.1"
        self._port: int | None = None
        self._proc: subprocess.Popen | None = None
        self._sim_dir = Path.cwd() / ".sim"
        self._log_path: Path | None = None
        self._log_handle = None
        self._connected_at: float | None = None
        self._launch_options: dict = {}
        self._last_run: dict | None = None
        self._run_count = 0
        self._close_on_disconnect = True

    @property
    def name(self) -> str:
        return "blender"

    @property
    def supports_session(self) -> bool:
        return True

    def detect(self, script: Path) -> bool:
        try:
            suffix = script.suffix.lower()
        except OSError:
            return False
        if suffix == _BLEND_SUFFIX:
            try:
                return script.is_file()
            except OSError:
                return False
        if suffix != _PY_SUFFIX:
            return False
        try:
            text = script.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return "import bpy" in text or "from bpy" in text

    def lint(self, script: Path) -> LintResult:
        suffix = script.suffix.lower()
        if suffix not in _ACCEPTED_SUFFIXES:
            return LintResult(
                ok=False,
                diagnostics=[Diagnostic(
                    level="error",
                    message=(
                        f"Unsupported file type: {suffix} "
                        f"(expected one of {', '.join(_ACCEPTED_SUFFIXES)})"
                    ),
                )],
            )
        if suffix == _BLEND_SUFFIX:
            if not script.is_file():
                return LintResult(
                    ok=False,
                    diagnostics=[Diagnostic(level="error", message=f"Cannot read: {script}")],
                )
            return LintResult(
                ok=True,
                diagnostics=[Diagnostic(
                    level="info",
                    message="Blender .blend static lint is not implemented; skipping binary scene checks",
                )],
            )
        try:
            text = script.read_text(encoding="utf-8")
        except OSError as exc:
            return LintResult(
                ok=False,
                diagnostics=[Diagnostic(level="error", message=f"Cannot read: {exc}")],
            )
        try:
            ast.parse(text, filename=str(script))
        except SyntaxError as exc:
            return LintResult(
                ok=False,
                diagnostics=[Diagnostic(level="error", message=exc.msg, line=exc.lineno)],
            )
        return LintResult(ok=True, diagnostics=[])

    def detect_installed(self) -> list[SolverInstall]:
        return _scan_blender_installs()

    def connect(self) -> ConnectionInfo:
        installs = self.detect_installed()
        if not installs:
            return ConnectionInfo(
                solver="blender",
                version=None,
                status="not_installed",
                message=(
                    "Blender executable not found. Install Blender, put `blender` on PATH, "
                    "or set SIM_BLENDER_EXE."
                ),
            )
        exe = installs[0].extra["exe"]
        version = _probe_version(exe) or installs[0].version
        return ConnectionInfo(
            solver="blender",
            version=version,
            status="ok",
            message=f"Blender {version} at {exe}",
            solver_version=version,
        )

    def parse_output(self, stdout: str) -> dict:
        return _json_line_tail(stdout)

    def run_file(self, script: Path) -> RunResult:
        suffix = script.suffix.lower()
        if suffix == _BLEND_SUFFIX:
            raise RuntimeError(
                "Blender .blend files require a live session or an explicit Python wrapper; "
                "run a .py script for one-shot execution."
            )
        if suffix != _PY_SUFFIX:
            raise RuntimeError(f"Blender driver only accepts {_ACCEPTED_SUFFIXES}")
        exe = self._selected_executable()
        command = [
            exe,
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            str(script),
        ]
        return run_subprocess(command, script=script, solver=self.name)

    def launch(
        self,
        mode: str = "solver",
        ui_mode: str = "gui",
        processors: int | None = None,
        **kwargs,
    ) -> dict:
        if self._proc is not None and self._proc.poll() is None:
            raise RuntimeError(f"Blender session already live: {self._session_id}")

        exe = kwargs.pop("blender_exe", None) or self._selected_executable()
        workspace = kwargs.pop("workspace", None)
        cwd = kwargs.pop("cwd", None)
        blend_file = kwargs.pop("blend_file", kwargs.pop("file", kwargs.pop("scene", None)))
        host = kwargs.pop("host", kwargs.pop("bridge_host", "127.0.0.1"))
        port = int(kwargs.pop("port", kwargs.pop("bridge_port", 0)) or 0)
        startup_timeout_s = float(kwargs.pop("startup_timeout_s", 60.0))
        close_on_disconnect = _as_bool(kwargs.pop("close_on_disconnect", True))
        factory_startup = _as_bool(kwargs.pop("factory_startup", blend_file is None))
        headless = _as_bool(kwargs.pop("headless", ui_mode in {"", "no_gui", "no-gui", "headless", "background"}))

        if kwargs.pop("attach_only", False):
            raise RuntimeError("attach_only is not implemented for Blender yet")

        self._session_id = str(uuid.uuid4())
        self._host = str(host)
        self._port = port or _find_free_port(self._host)
        self._close_on_disconnect = close_on_disconnect
        self._configure_workdir(workspace=workspace, cwd=cwd)
        self._open_log()

        bridge_path = files("sim_plugin_blender") / "bridge" / "sim_blender_bridge.py"
        cmd = [str(exe)]
        if headless:
            cmd.append("--background")
        if blend_file:
            cmd.append(str(Path(blend_file).resolve()))
        elif factory_startup:
            cmd.append("--factory-startup")
        cmd.extend([
            "--python-exit-code",
            "1",
            "--python",
            str(bridge_path),
            "--",
            "--sim-host",
            self._host,
            "--sim-port",
            str(self._port),
            "--session-id",
            self._session_id,
            "--workspace",
            str(self._sim_dir),
        ])

        self._launch_options = {
            "mode": mode,
            "requested_ui_mode": ui_mode,
            "ui_mode": "headless" if headless else "gui",
            "headless": headless,
            "factory_startup": factory_startup,
            "blend_file": str(Path(blend_file).resolve()) if blend_file else None,
            "workspace": workspace,
            "cwd": cwd,
            "processors": processors,
            "host": self._host,
            "port": self._port,
            "close_on_disconnect": close_on_disconnect,
            "command": cmd,
            **kwargs,
        }

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                cwd=str(Path(cwd).resolve()) if cwd else None,
                text=True,
            )
            self._wait_for_bridge(startup_timeout_s)
        except Exception:
            self._terminate()
            self._close_log()
            self._session_id = None
            raise

        self._connected_at = time.time()
        health = self.health()
        return {
            "ok": True,
            "session_id": self._session_id,
            "mode": "live-bridge",
            "source": "launch",
            "ui_mode": self._launch_options["ui_mode"],
            "requested_ui_mode": ui_mode,
            "headless": headless,
            "bridge_host": self._host,
            "bridge_port": self._port,
            "pid": self._proc.pid if self._proc else None,
            "log_path": str(self._log_path) if self._log_path else None,
            "launch_options": self._launch_options,
            "health": health,
        }

    def run(self, code: str, label: str = "blender-snippet") -> dict:
        started = time.time()
        run_id = str(uuid.uuid4())
        try:
            response = self._bridge_request(
                {"type": "exec", "code": code, "label": label},
                timeout_s=_DEFAULT_BRIDGE_TIMEOUT_S,
            )
        except Exception as exc:
            record = {
                "run_id": run_id,
                "ok": False,
                "label": label,
                "stdout": "",
                "stderr": "",
                "error": str(exc),
                "result": None,
                "elapsed_s": round(time.time() - started, 4),
                "health": self.health(),
            }
            self._last_run = record
            return record

        elapsed = round(time.time() - started, 4)
        record = {
            "run_id": run_id,
            "ok": bool(response.get("ok")),
            "label": label,
            "stdout": response.get("stdout", ""),
            "stderr": response.get("stderr", ""),
            "error": response.get("error"),
            "result": response.get("result"),
            "elapsed_s": elapsed,
            "scene": response.get("scene"),
        }
        self._run_count += 1
        self._last_run = record
        return record

    def query(self, name: str) -> dict:
        if name in {"health", "session.health"}:
            return self.health()
        if name == "last.result":
            return {"ok": True, "has_last_run": self._last_run is not None, **(self._last_run or {})}
        target = name
        if name in {"scene.summary", "blender.scene.summary"}:
            target = "scene.summary"
        elif name in {"selection.summary", "blender.selection.summary"}:
            target = "selection.summary"
        elif name in {"materials.summary", "blender.materials.summary"}:
            target = "materials.summary"
        elif name in {"file.summary", "blender.file.summary"}:
            target = "file.summary"
        elif name.startswith("blender.object:"):
            target = "object:" + name.split(":", 1)[1]
        elif name.startswith("object:"):
            target = name
        else:
            return {"ok": False, "error": f"unknown inspect target: {name}"}
        try:
            return self._bridge_request({"type": "inspect", "name": target}, timeout_s=30.0)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "target": target}

    def disconnect(self) -> dict:
        session_id = self._session_id
        if self._proc is not None and self._proc.poll() is None and self._port is not None:
            try:
                self._bridge_request(
                    {"type": "shutdown", "quit_blender": self._close_on_disconnect},
                    timeout_s=10.0,
                )
            except Exception:
                pass
        self._terminate(wait_first=True)
        self._close_log()
        self._session_id = None
        self._port = None
        self._connected_at = None
        self._last_run = None
        self._run_count = 0
        return {"ok": True, "session_id": session_id, "disconnected": True}

    def health(self) -> dict:
        proc_running = self._proc is not None and self._proc.poll() is None
        data = {
            "ok": proc_running,
            "connected": proc_running,
            "session_id": self._session_id,
            "pid": self._proc.pid if self._proc else None,
            "returncode": None if self._proc is None else self._proc.poll(),
            "bridge_host": self._host,
            "bridge_port": self._port,
            "connected_at": self._connected_at,
            "run_count": self._run_count,
            "log_path": str(self._log_path) if self._log_path else None,
        }
        if not proc_running:
            data["message"] = "Blender process is not running"
            data["log_tail"] = _tail(self._log_path)
            return data
        try:
            ping = self._bridge_request({"type": "ping"}, timeout_s=2.0)
            data.update(ping)
            data["ok"] = bool(ping.get("ok", False))
            data["connected"] = bool(ping.get("ok", False))
        except Exception as exc:
            data.update({
                "ok": False,
                "connected": False,
                "message": f"Blender bridge did not respond: {exc}",
                "log_tail": _tail(self._log_path),
            })
        return data

    def _selected_executable(self) -> str:
        installs = self.detect_installed()
        if not installs:
            raise RuntimeError(
                "Blender executable not found; set SIM_BLENDER_EXE or put `blender` on PATH."
            )
        return str(installs[0].extra["exe"])

    def _configure_workdir(self, *, workspace: str | None, cwd: str | None) -> None:
        base = Path(workspace or cwd or Path.cwd()).resolve()
        self._sim_dir = base / ".sim" / "blender"
        self._sim_dir.mkdir(parents=True, exist_ok=True)

    def _open_log(self) -> None:
        self._close_log()
        self._sim_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._log_path = self._sim_dir / f"blender-{stamp}-{uuid.uuid4().hex[:8]}.log"
        self._log_handle = self._log_path.open("w", encoding="utf-8")

    def _close_log(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except Exception:
                pass
        self._log_handle = None

    def _wait_for_bridge(self, timeout_s: float) -> None:
        deadline = time.time() + timeout_s
        last_error: Exception | None = None
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(
                    "Blender exited before bridge became ready. "
                    f"returncode={self._proc.returncode}; log_tail={_tail(self._log_path)!r}"
                )
            try:
                response = self._bridge_request({"type": "ping"}, timeout_s=1.0)
                if response.get("ok"):
                    return
            except Exception as exc:
                last_error = exc
            time.sleep(0.1)
        raise RuntimeError(
            f"Blender bridge did not become ready within {timeout_s}s: {last_error}; "
            f"log_tail={_tail(self._log_path)!r}"
        )

    def _bridge_request(self, payload: dict, timeout_s: float) -> dict:
        if self._port is None:
            raise RuntimeError("Blender bridge is not connected")
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        with socket.create_connection((self._host, self._port), timeout=timeout_s) as sock:
            sock.settimeout(timeout_s)
            sock.sendall(body)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk:
                    break
        raw = b"".join(chunks).split(b"\n", 1)[0].decode("utf-8", errors="replace")
        if not raw:
            raise RuntimeError("empty response from Blender bridge")
        response = json.loads(raw)
        if not isinstance(response, dict):
            raise RuntimeError(f"unexpected bridge response: {response!r}")
        return response

    def _terminate(self, *, wait_first: bool = False) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if wait_first:
            try:
                proc.wait(timeout=8)
                return
            except subprocess.TimeoutExpired:
                pass
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)

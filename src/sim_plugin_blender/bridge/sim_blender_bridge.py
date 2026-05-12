"""Blender-side sim bridge.

Run inside Blender:

    blender --python sim_blender_bridge.py -- --sim-port 9876

Protocol: one JSON object per TCP connection, newline terminated. This keeps the
bridge easy to probe from small shell/Python snippets and avoids an MCP runtime
dependency inside the Blender process.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import queue
import socket
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any

import bpy

try:  # Optional modules available in Blender; tests should not require them.
    import bmesh  # type: ignore
    import mathutils  # type: ignore
except Exception:  # pragma: no cover - depends on Blender build
    bmesh = None
    mathutils = None


_NAMESPACE: dict[str, Any] = {
    "bpy": bpy,
    "context": bpy.context,
    "data": bpy.data,
    "ops": bpy.ops,
    "_result": None,
}
if bmesh is not None:
    _NAMESPACE["bmesh"] = bmesh
if mathutils is not None:
    _NAMESPACE["mathutils"] = mathutils

_STOP = threading.Event()
_QUIT_BLENDER = False


@dataclass
class _QueuedRequest:
    payload: dict
    event: threading.Event
    response: dict | None = None


def _args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim-host", default="127.0.0.1")
    parser.add_argument("--sim-port", type=int, required=True)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--workspace", default="")
    return parser.parse_args(argv)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if hasattr(value, "to_tuple"):
        try:
            return list(value.to_tuple())
        except Exception:
            pass
    if hasattr(value, "to_list"):
        try:
            return value.to_list()
        except Exception:
            pass
    return repr(value)


def _vec3(value: Any) -> list[float]:
    return [round(float(v), 6) for v in value]


def _object_summary(obj: Any) -> dict:
    return {
        "name": obj.name,
        "type": obj.type,
        "location": _vec3(obj.location),
        "rotation_euler": _vec3(obj.rotation_euler),
        "scale": _vec3(obj.scale),
        "dimensions": _vec3(obj.dimensions),
        "visible": bool(obj.visible_get()),
        "selected": bool(obj.select_get()),
        "material_names": [slot.material.name for slot in obj.material_slots if slot.material],
    }


def _scene_summary() -> dict:
    scene = bpy.context.scene
    objects = list(scene.objects)
    by_type: dict[str, int] = {}
    for obj in objects:
        by_type[obj.type] = by_type.get(obj.type, 0) + 1
    scene_material_names = sorted({
        slot.material.name
        for obj in objects
        for slot in obj.material_slots
        if slot.material
    })
    active = bpy.context.view_layer.objects.active
    selected = list(bpy.context.selected_objects)
    return {
        "ok": True,
        "target": "blender.scene.summary",
        "session": _session_block(),
        "file_path": bpy.data.filepath or None,
        "scene_name": scene.name,
        "unit_system": scene.unit_settings.system,
        "frame_current": scene.frame_current,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "object_count": len(objects),
        "object_count_by_type": by_type,
        "mesh_count": by_type.get("MESH", 0),
        "camera_count": by_type.get("CAMERA", 0),
        "light_count": by_type.get("LIGHT", 0),
        "material_count": len(scene_material_names),
        "scene_material_count": len(scene_material_names),
        "scene_material_names": scene_material_names,
        "data_material_count": len(bpy.data.materials),
        "active_object": active.name if active else None,
        "selected_objects": [obj.name for obj in selected],
        "objects": [_object_summary(obj) for obj in objects[:200]],
        "truncated": len(objects) > 200,
    }


def _selection_summary() -> dict:
    selected = list(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    return {
        "ok": True,
        "target": "blender.selection.summary",
        "active_object": active.name if active else None,
        "selected_count": len(selected),
        "selected_objects": [_object_summary(obj) for obj in selected],
    }


def _materials_summary() -> dict:
    return {
        "ok": True,
        "target": "blender.materials.summary",
        "material_count": len(bpy.data.materials),
        "materials": [
            {
                "name": mat.name,
                "use_nodes": bool(mat.use_nodes),
                "diffuse_color": _vec3(mat.diffuse_color),
            }
            for mat in bpy.data.materials
        ],
    }


def _file_summary() -> dict:
    return {
        "ok": True,
        "target": "blender.file.summary",
        "file_path": bpy.data.filepath or None,
        "is_saved": bool(bpy.data.filepath),
        "is_dirty": bool(bpy.data.is_dirty),
    }


def _session_block() -> dict:
    return {
        "session_id": _CONFIG.session_id,
        "version": bpy.app.version_string,
        "background": bool(bpy.app.background),
        "binary_path": bpy.app.binary_path,
        "time": time.time(),
    }


def _inspect(name: str) -> dict:
    if name in {"scene.summary", "blender.scene.summary"}:
        return _scene_summary()
    if name in {"selection.summary", "blender.selection.summary"}:
        return _selection_summary()
    if name in {"materials.summary", "blender.materials.summary"}:
        return _materials_summary()
    if name in {"file.summary", "blender.file.summary"}:
        return _file_summary()
    if name.startswith("object:"):
        obj_name = name.split(":", 1)[1]
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            return {"ok": False, "error": f"object not found: {obj_name}", "target": name}
        return {"ok": True, "target": "blender.object", "object": _object_summary(obj)}
    return {"ok": False, "error": f"unknown inspect target: {name}", "target": name}


def _exec(code: str, label: str) -> dict:
    stdout = io.StringIO()
    stderr = io.StringIO()
    _NAMESPACE["_result"] = None
    started = time.time()
    ok = True
    error = None
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            compiled = compile(code, f"<sim-blender:{label}>", "exec")
            exec(compiled, _NAMESPACE)  # noqa: S102 - explicit local bridge contract
        except Exception as exc:  # noqa: BLE001 - report Blender/API exceptions verbatim
            ok = False
            error = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return {
        "ok": ok,
        "label": label,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "error": error,
        "result": _json_safe(_NAMESPACE.get("_result")),
        "elapsed_s": round(time.time() - started, 4),
        "scene": _scene_summary(),
    }


def _handle(payload: dict) -> dict:
    global _QUIT_BLENDER
    kind = payload.get("type")
    if kind == "ping":
        return {"ok": True, "type": "pong", **_session_block()}
    if kind == "inspect":
        return _inspect(str(payload.get("name", "scene.summary")))
    if kind == "exec":
        return _exec(str(payload.get("code", "")), str(payload.get("label", "snippet")))
    if kind == "shutdown":
        _QUIT_BLENDER = bool(payload.get("quit_blender", True))
        _STOP.set()
        return {"ok": True, "shutdown": True, "quit_blender": _QUIT_BLENDER}
    return {"ok": False, "error": f"unknown request type: {kind}"}


def _read_request(conn: socket.socket) -> dict:
    chunks: list[bytes] = []
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    raw = b"".join(chunks).split(b"\n", 1)[0]
    return json.loads(raw.decode("utf-8"))


def _write_response(conn: socket.socket, response: dict) -> None:
    conn.sendall(json.dumps(response, separators=(",", ":"), default=_json_safe).encode("utf-8") + b"\n")


def _listen_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((_CONFIG.sim_host, _CONFIG.sim_port))
    sock.listen(16)
    return sock


def _serve_background(sock: socket.socket) -> None:
    print(json.dumps({"ok": True, "bridge": "ready", **_session_block()}), flush=True)
    while not _STOP.is_set():
        conn, _addr = sock.accept()
        with conn:
            try:
                payload = _read_request(conn)
                response = _handle(payload)
            except Exception as exc:  # noqa: BLE001
                response = {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
            _write_response(conn, response)


def _serve_visible(sock: socket.socket) -> None:
    requests: "queue.Queue[_QueuedRequest]" = queue.Queue()

    def socket_thread() -> None:
        while not _STOP.is_set():
            try:
                conn, _addr = sock.accept()
            except OSError:
                return
            with conn:
                try:
                    payload = _read_request(conn)
                    item = _QueuedRequest(payload=payload, event=threading.Event())
                    requests.put(item)
                    item.event.wait()
                    response = item.response or {"ok": False, "error": "request did not produce a response"}
                except Exception as exc:  # noqa: BLE001
                    response = {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
                _write_response(conn, response)

    def process_queue():
        while True:
            try:
                item = requests.get_nowait()
            except queue.Empty:
                break
            try:
                item.response = _handle(item.payload)
            except Exception as exc:  # noqa: BLE001
                item.response = {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
            finally:
                item.event.set()
        if _STOP.is_set():
            if _QUIT_BLENDER:
                bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender(), first_interval=0.2)
            return None
        return 0.05

    threading.Thread(target=socket_thread, name="sim-blender-bridge", daemon=True).start()
    bpy.app.timers.register(process_queue, first_interval=0.05)
    print(json.dumps({"ok": True, "bridge": "ready", **_session_block()}), flush=True)


_CONFIG = _args()


def main() -> None:
    sock = _listen_socket()
    if bpy.app.background:
        try:
            _serve_background(sock)
        finally:
            sock.close()
    else:
        _serve_visible(sock)


main()

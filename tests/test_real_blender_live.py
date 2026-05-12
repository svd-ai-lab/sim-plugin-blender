from __future__ import annotations

import os
from pathlib import Path

import pytest

from sim_plugin_blender import BlenderDriver


if os.environ.get("SIM_BLENDER_RUN_INTEGRATION") != "1":
    pytest.skip(
        "set SIM_BLENDER_RUN_INTEGRATION=1 to run the real Blender live smoke",
        allow_module_level=True,
    )


def test_real_blender_headless_live_session(tmp_path: Path) -> None:
    driver = BlenderDriver()
    info = driver.launch(ui_mode="no_gui", workspace=str(tmp_path), startup_timeout_s=30)
    try:
        assert info["ok"] is True
        result = driver.run(
            """
import bpy
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
bpy.context.scene.unit_settings.system = "METRIC"
bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 1))
cube = bpy.context.object
cube.name = "sim_live_cube"
_result = {
    "cube_name": cube.name,
    "cube_dimensions": [round(float(v), 6) for v in cube.dimensions],
    "cube_volume": round(float(cube.dimensions[0] * cube.dimensions[1] * cube.dimensions[2]), 6),
}
""",
            label="live-cube",
        )
        assert result["ok"] is True, result
        assert result["result"]["cube_name"] == "sim_live_cube"
        assert result["result"]["cube_dimensions"] == [2.0, 2.0, 2.0]
        assert result["result"]["cube_volume"] == 8.0

        scene = driver.query("blender.scene.summary")
        assert scene["ok"] is True
        assert scene["object_count_by_type"]["MESH"] == 1
        assert scene["active_object"] == "sim_live_cube"
    finally:
        driver.disconnect()

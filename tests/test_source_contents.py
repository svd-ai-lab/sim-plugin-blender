from __future__ import annotations

from importlib.resources import files


def test_packaged_bridge_and_skill_exist() -> None:
    package = files("sim_plugin_blender")
    assert (package / "bridge" / "sim_blender_bridge.py").is_file()
    assert (package / "_skills" / "blender" / "SKILL.md").is_file()

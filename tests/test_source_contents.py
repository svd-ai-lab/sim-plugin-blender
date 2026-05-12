from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def test_packaged_bridge_and_skill_exist() -> None:
    package = files("sim_plugin_blender")
    assert (package / "bridge" / "sim_blender_bridge.py").is_file()
    assert (package / "_skills" / "blender" / "SKILL.md").is_file()


def test_starship_cookbook_exists() -> None:
    root = Path(__file__).parents[1]
    assert (root / "cookbook" / "starship_stack.py").is_file()

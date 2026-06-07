from __future__ import annotations

from importlib.resources import files
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_packaged_bridge_and_skill_exist() -> None:
    package = files("sim_plugin_blender")
    assert (package / "bridge" / "sim_blender_bridge.py").is_file()
    assert (package / "_skills" / "blender" / "SKILL.md").is_file()


def test_mcp_docs_keep_companion_opt_in() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    skill = (ROOT / "src" / "sim_plugin_blender" / "_skills" / "blender" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    combined = readme + "\n" + skill

    assert "does not use, bundle, install, or start Blender's MCP server" in readme
    assert "optional companion" in skill
    assert "default sim transport" in skill
    assert "Do not silently install" in combined
    assert "without guards" in combined
    assert "isolated VM" in combined
    assert "projects.blender.org/lab/blender_mcp.git#subdirectory=mcp" in combined

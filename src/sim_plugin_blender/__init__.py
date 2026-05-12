"""Blender driver plugin for sim-cli."""
from importlib.resources import files

from .driver import BlenderDriver

skills_dir = files(__name__) / "_skills"

plugin_info = {
    "name": "blender",
    "summary": "Blender live-editing driver for sim-cli.",
    "homepage": "https://github.com/svd-ai-lab/sim-plugin-blender",
    "license_class": "oss",
    "solver_name": "Blender",
}

__all__ = ["BlenderDriver", "skills_dir", "plugin_info"]

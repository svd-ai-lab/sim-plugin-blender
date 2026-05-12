"""Approximate SpaceX Starship/Super Heavy model for Blender live sessions.

Run with:
    uv run sim exec --file cookbook/starship_stack.py --label starship-stack

The proportions follow SpaceX's public Starship page at a tabletop scale where
one Blender unit represents one meter.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import bpy
from mathutils import Vector


STACK_HEIGHT_M = 123.0
DIAMETER_M = 9.0
BOOSTER_HEIGHT_M = 71.0
SHIP_HEIGHT_M = 52.0
SHIP_CYLINDER_HEIGHT_M = 44.0
NOSE_HEIGHT_M = SHIP_HEIGHT_M - SHIP_CYLINDER_HEIGHT_M
RADIUS_M = DIAMETER_M / 2.0


def material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat


def set_mat(obj: bpy.types.Object, mat: bpy.types.Material) -> bpy.types.Object:
    obj.data.materials.append(mat)
    return obj


def cylinder(name: str, radius: float, depth: float, z_center: float, mat: bpy.types.Material) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=radius, depth=depth, location=(0, 0, z_center))
    obj = bpy.context.object
    obj.name = name
    return set_mat(obj, mat)


def cone(
    name: str,
    radius1: float,
    radius2: float,
    depth: float,
    z_center: float,
    mat: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cone_add(
        vertices=128,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
        location=(0, 0, z_center),
    )
    obj = bpy.context.object
    obj.name = name
    return set_mat(obj, mat)


def torus_band(name: str, z: float, mat: bpy.types.Material, minor_radius: float = 0.06) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=RADIUS_M,
        minor_radius=minor_radius,
        major_segments=160,
        minor_segments=8,
        location=(0, 0, z),
    )
    obj = bpy.context.object
    obj.name = name
    return set_mat(obj, mat)


def engine_nozzle(name: str, x: float, y: float, mat: bpy.types.Material) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cone_add(
        vertices=32,
        radius1=0.36,
        radius2=0.18,
        depth=1.4,
        location=(x, y, -0.7),
    )
    obj = bpy.context.object
    obj.name = name
    return set_mat(obj, mat)


def panel(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    angle_rad: float,
    mat: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=(0, 0, angle_rad))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return set_mat(obj, mat)


def triangular_fin(name: str, angle_rad: float, z0: float, mat: bpy.types.Material) -> bpy.types.Object:
    radial = Vector((math.cos(angle_rad), math.sin(angle_rad), 0))
    tangent = Vector((-math.sin(angle_rad), math.cos(angle_rad), 0))
    base = radial * RADIUS_M
    verts = [
        base + tangent * -0.18 + Vector((0, 0, z0)),
        base + tangent * 0.18 + Vector((0, 0, z0)),
        base + radial * 2.6 + tangent * 0.18 + Vector((0, 0, z0 + 7.0)),
        base + radial * 2.6 + tangent * -0.18 + Vector((0, 0, z0 + 7.0)),
    ]
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata([tuple(v) for v in verts], [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return set_mat(obj, mat)


def label(name: str, text: str, location: tuple[float, float, float], size: float, mat: bpy.types.Material) -> bpy.types.Object:
    bpy.ops.object.text_add(location=location, rotation=(math.radians(72), 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.data.body = text
    obj.data.align_x = "CENTER"
    obj.data.size = size
    return set_mat(obj, mat)


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
bpy.context.scene.unit_settings.system = "METRIC"
bpy.context.scene.unit_settings.scale_length = 1.0

stainless = material("starship_brushed_stainless", (0.72, 0.74, 0.74, 1.0))
dark = material("starship_heatshield_black", (0.03, 0.035, 0.04, 1.0))
orange = material("starship_engine_copper", (0.85, 0.42, 0.12, 1.0))
blue = material("sim_reference_blue", (0.05, 0.24, 0.70, 1.0))
white = material("sim_label_white", (0.90, 0.90, 0.86, 1.0))

created: list[bpy.types.Object] = []
created.append(cylinder("super_heavy_booster_71m", RADIUS_M, BOOSTER_HEIGHT_M, BOOSTER_HEIGHT_M / 2, stainless))
created.append(cylinder("starship_upper_stage_44m_body", RADIUS_M, SHIP_CYLINDER_HEIGHT_M, BOOSTER_HEIGHT_M + SHIP_CYLINDER_HEIGHT_M / 2, stainless))
created.append(cone("starship_nose_cone_8m", RADIUS_M, 0.18, NOSE_HEIGHT_M, BOOSTER_HEIGHT_M + SHIP_CYLINDER_HEIGHT_M + NOSE_HEIGHT_M / 2, stainless))
created.append(cylinder("hot_stage_interstage", RADIUS_M + 0.08, 2.0, BOOSTER_HEIGHT_M + 1.0, dark))

for i, z in enumerate((4.5, 18.0, 36.0, 54.0, BOOSTER_HEIGHT_M, 95.0, 115.0), start=1):
    created.append(torus_band(f"starship_reference_band_{i}", z, dark if z == BOOSTER_HEIGHT_M else blue))

engine_positions = [(0.0, 0.0)]
for ring_radius, count in ((1.35, 6), (2.65, 12), (3.65, 14)):
    for i in range(count):
        a = 2 * math.pi * i / count
        engine_positions.append((ring_radius * math.cos(a), ring_radius * math.sin(a)))
for i, (x, y) in enumerate(engine_positions[:33], start=1):
    created.append(engine_nozzle(f"raptor_engine_{i:02d}", x, y, orange))

for i, angle in enumerate((0, math.pi / 2, math.pi, 3 * math.pi / 2), start=1):
    location = ((RADIUS_M + 1.2) * math.cos(angle), (RADIUS_M + 1.2) * math.sin(angle), 63.0)
    created.append(panel(f"super_heavy_grid_fin_{i}", location, (2.7, 0.28, 2.0), angle, dark))

for i, angle in enumerate((math.radians(45), math.radians(225)), start=1):
    created.append(triangular_fin(f"starship_aft_flap_{i}", angle, BOOSTER_HEIGHT_M + 4.0, dark))
    created.append(triangular_fin(f"starship_forward_flap_{i}", angle, BOOSTER_HEIGHT_M + 34.0, dark))

created.append(label("starship_stack_label", "SpaceX Starship / Super Heavy, approx 123 m x 9 m", (0, -12, 8), 2.3, white))

bpy.ops.object.light_add(type="AREA", location=(-12, -18, 145))
light = bpy.context.object
light.name = "starship_area_light"
light.data.energy = 800
light.data.size = 35
created.append(light)

bpy.ops.object.camera_add(location=(36, -82, 56), rotation=(math.radians(63), 0, math.radians(23)))
camera = bpy.context.object
camera.name = "starship_camera"
bpy.context.scene.camera = camera
created.append(camera)

for obj in bpy.context.scene.objects:
    obj.select_set(False)
for obj in created:
    obj.select_set(True)
bpy.context.view_layer.objects.active = created[0]

blend_path = Path(os.environ.get("SIM_BLENDER_STARSHIP_BLEND", Path.cwd() / "starship_stack.blend")).resolve()
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

_result = {
    "ok": True,
    "model": "spacex-starship-super-heavy-approx",
    "stack_height_m": STACK_HEIGHT_M,
    "diameter_m": DIAMETER_M,
    "booster_height_m": BOOSTER_HEIGHT_M,
    "ship_height_m": SHIP_HEIGHT_M,
    "object_count": len(bpy.context.scene.objects),
    "mesh_count": sum(1 for obj in bpy.context.scene.objects if obj.type == "MESH"),
    "blend_path": str(blend_path),
    "created": [obj.name for obj in created],
}
print(json.dumps(_result, sort_keys=True))

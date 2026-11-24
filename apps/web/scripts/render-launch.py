"""Render the release-page covers from the same GLB used by the interactive viewer.

From the project root, run Blender --background --factory-startup --python
apps/web/scripts/render-launch.py. Append -- --preview to render small proofs in var/qa.
"""

import math
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

PRODUCTS = Path(__file__).resolve().parents[1] / "public" / "products"
preview = "--preview" in sys.argv
out = PRODUCTS.parents[3] / "var" / "qa" / "launch" if preview else PRODUCTS
out.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(PRODUCTS / "frame.glb"))
# The viewer uses glTF alpha blending. In the ray-traced studio, apply a thin
# lens surface so that the studio lights reflect over a view through the rim.
lens_nodes = bpy.data.materials["Clear sage-tinted optical lens"].node_tree
surface = lens_nodes.nodes.get("Principled BSDF")
surface.inputs["Base Color"].default_value = (0.80, 0.94, 0.90, 1)
surface.inputs["Roughness"].default_value = 0.07
surface.inputs["Metallic"].default_value = 0.0
surface.inputs["Transmission Weight"].default_value = 1
surface.inputs["Alpha"].default_value = 0.48
vertices = [
    obj.matrix_world @ vertex.co
    for obj in bpy.context.scene.objects
    if obj.type == "MESH"
    for vertex in obj.data.vertices
]
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 8 if preview else 40
scene.cycles.use_denoising = True
scene.render.image_settings.file_format = "WEBP"
scene.render.image_settings.quality = 91
scene.render.resolution_percentage = 36 if preview else 100
scene.world = bpy.data.worlds.new("Graphite studio")
scene.world.use_nodes = True
background = scene.world.node_tree.nodes["Background"]
background.inputs["Color"].default_value = (0.28, 0.32, 0.35, 1)
background.inputs["Strength"].default_value = 0.24

# The matte floor catches the soft reflection below the rim.
bpy.ops.mesh.primitive_plane_add(size=300, location=(0, 0, -0.78))
mat = bpy.data.materials.new("Charcoal sweep")
mat.use_nodes = True
shader = mat.node_tree.nodes["Principled BSDF"]
shader.inputs["Base Color"].default_value = (0.009, 0.012, 0.014, 1)
shader.inputs["Roughness"].default_value = 0.45
bpy.context.object.data.materials.append(mat)


def softbox(position, power, size, height, color):
    bpy.ops.object.light_add(type="AREA", location=position)
    lamp = bpy.context.object
    lamp.rotation_euler = (
        (Vector((0, 0.35, 0)) - lamp.location).to_track_quat("-Z", "Y").to_euler()
    )
    lamp.data.shape = "RECTANGLE"
    lamp.data.size, lamp.data.size_y = size, height
    lamp.data.color, lamp.data.energy = color, power


softbox((-2.8, -3.2, 4.8), 680, 4, 1.8, (1, 0.93, 0.82))
softbox((3.2, 2.6, 3.9), 950, 4, 0.85, (0.80, 0.90, 1))
softbox((4.1, -1.8, 1.2), 150, 2.3, 0.6, (1, 0.86, 0.67))

target = Vector((0, 0.62, 0.05))
bpy.ops.object.camera_add(location=(4.85, -5.8, 3.15))
camera = bpy.context.object
rotation = (target - camera.location).to_track_quat("-Z", "Y") @ Quaternion(
    (0, 0, 1), math.radians(4)
)
camera.rotation_euler = rotation.to_euler()
camera.data.type = "ORTHO"
scene.camera = camera
right, up = rotation @ Vector((1, 0, 0)), rotation @ Vector((0, 1, 0))
xs, ys = [v.dot(right) for v in vertices], [v.dot(up) for v in vertices]
center_x, center_y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def render(name, width, height, product_width, cx, cy):
    scene.render.resolution_x, scene.render.resolution_y = width, height
    span_x = (max(xs) - min(xs)) / product_width
    span_y = span_x * height / width
    camera.data.ortho_scale = max(span_x, span_y)
    camera.location += right * (
        center_x - camera.location.dot(right) - (cx - 0.5) * span_x
    )
    camera.location += up * (center_y - camera.location.dot(up) - (0.5 - cy) * span_y)
    scene.render.filepath = str(out / name)
    bpy.ops.render.render(write_still=True)


render("launch-frame.webp", 1920, 1000, 0.535, 0.704, 0.50)
render("launch-frame-mobile.webp", 860, 1040, 0.91, 0.5, 0.53)

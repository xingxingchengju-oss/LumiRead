"""Build the LumiRead design-C optics, labelled GLBs and transparent WebP posters.

Run with Blender --background --factory-startup --python render-products.py.
Use -- --models-only to omit rendering, or -- --guide-covers-only to render
just the closed shells for the scroll guide. Design dimensions are in millimetres.
Blender's Y points towards the ears; in glTF the glasses face +Z, Y points up
and one scene unit represents 100 mm.
"""

import json
import math
import sys
from contextlib import contextmanager
from pathlib import Path

import bmesh
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.geometry import interpolate_bezier

OUT = Path(__file__).resolve().parents[1] / "public" / "products"
UNIT = 0.01
N = 64
TAU = math.tau
PARENT = None


def units(p):
    return Vector(p) * UNIT


def register(obj, name, part=None, mat=None):
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    if part:
        obj["part"] = part
    if PARENT:
        bpy.context.view_layer.update()
        obj.parent = PARENT
        obj.location -= PARENT.matrix_world.translation
    return obj


@contextmanager
def inside(node):
    global PARENT
    old = PARENT
    PARENT = node
    try:
        yield
    finally:
        PARENT = old


def empty(name, pos, key, value):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.empty_display_size = 0.015
    obj.location = units(pos)
    obj[key] = value
    return register(obj, name)


def anchor(part, pos):
    return empty("Focus · " + part, pos, "anchor", part)


def srgb(hexcode):
    vals = [int(hexcode[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(
        v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in vals
    )


def material(name, color, rough, metal=0, coat=0, alpha=1, transmission=0, emission=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    rgba = (*srgb(color), 1)
    for prop, val in {
        "Base Color": rgba,
        "Metallic": metal,
        "Roughness": rough,
        "Alpha": alpha,
        "Transmission Weight": transmission,
        "Coat Weight": coat,
        "Coat Roughness": 0.15,
        "IOR": 1.46,
        "Emission Color": rgba,
        "Emission Strength": emission,
    }.items():
        shader.inputs[prop].default_value = val
    mat.diffuse_color = (*rgba[:3], alpha)
    return mat


def surface_finish(mat, brushed):
    """A tile in millimetres. Both the renderer and glTF read the same ORM map."""
    shader = mat.node_tree.nodes.get("Principled BSDF")
    roughness = shader.inputs["Roughness"].default_value
    metallic = shader.inputs["Metallic"].default_value
    rng = np.random.default_rng(41)
    grain = rng.normal(0, 0.022, (256, 256))
    if brushed:
        grain += rng.normal(0, 0.038, (256, 1))
    pixels = np.ones((256, 256, 4), dtype=np.float32)
    pixels[:, :, 1] = np.clip(roughness + grain, 0.04, 0.95)
    pixels[:, :, 2] = metallic
    image = bpy.data.images.new(
        mat.name + " finish", width=256, height=256, alpha=False
    )
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(pixels.ravel())
    image.pack()
    tree = mat.node_tree
    tex = tree.nodes.new("ShaderNodeTexImage")
    tex.image = image
    channels = tree.nodes.new("ShaderNodeSeparateColor")
    tree.links.new(tex.outputs["Color"], channels.inputs["Color"])
    tree.links.new(channels.outputs["Green"], shader.inputs["Roughness"])
    tree.links.new(channels.outputs["Blue"], shader.inputs["Metallic"])
    mat["finish_uv"] = True


def materials():
    m = {
        "acetate": material("Smoke · polished acetate", "363437", 0.17, 0.025, 0.88),
        "acetate_edge": material(
            "Smoke · polished cut edge", "666062", 0.11, 0.025, 0.92
        ),
        "host": material("Graphite · optical acetate", "393537", 0.24, 0.05, 0.44),
        "tip": material("Carbon · soft-touch elastomer", "333439", 0.60, 0, 0.04),
        "nose": material("Clear smoke · cast silicone", "bcb8b3", 0.32, 0, 0.24, 0.40),
        "lens": material(
            "Platinum violet · optical coating", "d1d4e8", 0.038, 0, 0.78, 0.115
        ),
        "clear": material("Clear · prescription glass", "dfe3e4", 0.04, 0, 0.65, 0.09),
        "gold": material("Pale champagne · satin titanium", "c7ae8c", 0.24, 0.91, 0.17),
        "edge": material("Polished titanium", "d4c6b8", 0.17, 0.88),
        "dark": material("Ink · anodised hardware", "1b1b20", 0.29, 0.37),
        "gasket": material("Carbon silicone", "242329", 0.53, 0.02),
        "crystal": material("Obsidian · optical window", "23232c", 0.135, 0.36, 0.43),
        "sensor": material("Sapphire · objective", "294269", 0.115, 0.54, 0.58),
        "iris": material("Indigo · objective coating", "584b72", 0.19, 0.59),
        "led": material(
            "Sea-glass · illuminated indicator",
            "bfd3c9",
            0.19,
            0.05,
            0.25,
            emission=0,
        ),
        "silver": material("Satin silver · magnesium", "c3c3c5", 0.26, 0.91, 0.13),
        "frost": material("Machined silver", "d3d2d8", 0.22, 0.82),
        "board": material("Solder mask · forest", "225849", 0.36, 0.21),
        "traces": material("Copper under solder mask", "68967b", 0.32, 0.42),
        "pins": material("Electroless gold", "d3a85b", 0.27, 0.73),
        "chip": material("Silicon package", "252a2b", 0.47, 0.17),
        "cell": material("Amber · cell edge tape", "c58a37", 0.30, 0.37, 0.19),
        "cellmetal": material("Brushed battery pouch", "a5a7a0", 0.35, 0.64),
    }
    for key in ("gold", "edge", "silver", "frost", "tip"):
        surface_finish(m[key], brushed=key in ("gold", "edge"))
    for key in ("lens", "clear"):
        shader = m[key].node_tree.nodes.get("Principled BSDF")
        shader.inputs["IOR"].default_value = 1.54
        if key == "lens":
            shader.inputs["Thin Film Thickness"].default_value = 300
            shader.inputs["Thin Film IOR"].default_value = 1.34
    return m


def mesh(name, verts, faces, part, mat, pos=(0, 0, 0), smooth=True):
    data = bpy.data.meshes.new(name)
    data.from_pydata([units(v) for v in verts], [], faces)
    data.update()
    if mat.get("finish_uv"):
        uv = data.uv_layers.new(name="Finish")
        for poly in data.polygons:
            axis = max(range(3), key=lambda k: abs(poly.normal[k]))
            u, v = [(1, 2), (0, 2), (1, 0)][axis]
            for idx in poly.loop_indices:
                co = data.vertices[data.loops[idx].vertex_index].co
                uv.data[idx].uv = (co[u] / 0.06, co[v] / 0.06)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = units(pos)
    if smooth:
        for poly in data.polygons:
            poly.use_smooth = True
    return register(obj, name, part, mat)


def soften(obj, width, segments=4):
    if width:
        mod = obj.modifiers.new("Machined radius", "BEVEL")
        mod.width = width * UNIT
        mod.segments = segments
        mod.harden_normals = True
    normal = obj.modifiers.new("Polished surface normals", "WEIGHTED_NORMAL")
    normal.keep_sharp = True
    return obj


def box(name, pos, dims, radius, part, mat):
    x, y, z = (v / 2 for v in dims)
    verts = [
        (-x, -y, -z),
        (x, -y, -z),
        (x, y, -z),
        (-x, y, -z),
        (-x, -y, z),
        (x, -y, z),
        (x, y, z),
        (-x, y, z),
    ]
    faces = [
        (3, 2, 1, 0),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    return soften(mesh(name, verts, faces, part, mat, pos), radius)


def ellipsoid(name, pos, radii, part, mat, tilt=0, segments=28):
    verts = [(0, 0, radii[2])]
    steps = 12
    for i in range(1, steps):
        a = math.pi * i / steps
        for j in range(segments):
            b = TAU * j / segments
            verts.append(
                (
                    radii[0] * math.sin(a) * math.cos(b),
                    radii[1] * math.sin(a) * math.sin(b),
                    radii[2] * math.cos(a),
                )
            )
    verts.append((0, 0, -radii[2]))
    faces = []
    for j in range(segments):
        k = (j + 1) % segments
        faces.append((0, j + 1, k + 1))
        for i in range(steps - 2):
            m = 1 + i * segments
            faces.append((m + j, m + j + segments, m + k + segments, m + k))
        m = 1 + (steps - 2) * segments
        faces.append((m + k, m + j, len(verts) - 1))
    obj = mesh(name, verts, faces, part, mat, pos)
    obj.rotation_euler.y = math.radians(tilt)
    return obj


def rings_faces(rings, count, caps=False):
    faces = []
    for i in range(rings - 1):
        for j in range(count):
            k = (j + 1) % count
            a, b = i * count, (i + 1) * count
            faces.append((a + j, a + k, b + k, b + j))
    if caps:
        faces.extend(
            [
                tuple(reversed(range(count))),
                tuple((rings - 1) * count + j for j in range(count)),
            ]
        )
    return faces


def lathe(name, pos, profile, part, mat):
    """A round machined profile looking directly towards the front (-Blender Y)."""
    verts = [
        (r * math.cos(a), -depth, r * math.sin(a))
        for r, depth in profile
        for a in (TAU * j / N for j in range(N))
    ]
    return mesh(name, verts, rings_faces(len(profile), N), part, mat, pos)


def rounded_2d(width, height, radius, steps=8):
    pts = []
    for i, (sx, sy) in enumerate([(1, 1), (-1, 1), (-1, -1), (1, -1)]):
        for j in range(steps + 1):
            angle = i * math.pi / 2 + (math.pi / 2) * j / steps
            pts.append(
                (
                    sx * (width / 2 - radius) + radius * math.cos(angle),
                    sy * (height / 2 - radius) + radius * math.sin(angle),
                )
            )
    return pts


def plate(name, pos, width, height, depth, radius, edge, part, mat):
    path = rounded_2d(width, height, radius)
    # The profile is drawn counterclockwise from the front.
    verts = [(x, y, z) for y in (depth / 2, -depth / 2) for x, z in path]
    return soften(
        mesh(name, verts, rings_faces(2, len(path), caps=True), part, mat, pos), edge, 3
    )


def bezier_path(start, pieces):
    points = [start]
    for ca, cb, end in pieces:
        v = [Vector(p) for p in (points[-1], ca, cb, end)]
        length = sum((v[i] - v[i + 1]).length for i in range(3))
        points.extend(
            tuple(p)
            for p in interpolate_bezier(*v, max(6, math.ceil(length / 1.05)))[1:]
        )
    return points


# Half of the continuous acetate outline: bridge top, brow, outside corner,
# lower rim, and the underside of the saddle. Mirroring closes the other half.
HALF = bezier_path(
    (0, 14.0),
    [
        ((4.0, 14.05), (5.4, 14.15), (8.6, 16.35)),
        ((13.1, 19.4), (18.4, 20.25), (28.2, 20.35)),
        ((41.0, 20.65), (51.2, 20.1), (57.7, 18.5)),
        ((59.2, 18.1), (62.7, 17.2), (63.65, 16.6)),
        ((64.0, 16.3), (64.05, 16.0), (64.05, 15.28)),
        ((64.02, 13.4), (64.0, 10.0), (63.9, 9.05)),
        ((63.8, 8.1), (63.15, 7.65), (62.0, 7.2)),
        ((59.2, 5.95), (58.45, 3.75), (57.65, -0.7)),
        ((56.45, -7.7), (55.2, -13.2), (52.0, -16.5)),
        ((49.0, -19.4), (45.0, -20.0), (36.3, -20.0)),
        ((26.0, -20.0), (18.7, -19.55), (15.15, -16.7)),
        ((11.65, -13.75), (10.30, -7.1), (8.50, -1.7)),
        ((7.28, 2.25), (6.25, 5.60), (4.15, 6.0)),
        ((2.60, 6.3), (1.15, 6.25), (0, 6.25)),
    ],
)
APERTURE = bezier_path(
    (12.15, 12.15),
    [
        ((15.1, 16.0), (20.1, 17.4), (29.2, 17.5)),
        ((40.9, 17.7), (48.6, 17.5), (52.45, 15.9)),
        ((55.65, 14.5), (56.7, 11.4), (56.05, 6.65)),
        ((55.15, 1.0), (53.95, -8.9), (50.75, -13.6)),
        ((48.5, -16.7), (44.6, -17.35), (36.8, -17.45)),
        ((27.5, -17.65), (20.5, -17.3), (17.35, -14.8)),
        ((14.65, -12.6), (12.9, -5.65), (11.1, 1.4)),
        ((9.7, 6.7), (10.0, 9.8), (12.15, 12.15)),
    ],
)[:-1]
HALF_HOST = bezier_path(
    (0, 13.15),
    [
        ((4, 13.3), (6.7, 15.3), (10.9, 17.8)),
        ((15.5, 20.4), (22, 21.1), (31, 21.05)),
        ((43.5, 21.0), (51.5, 19.1), (57.6, 17.3)),
        ((59.4, 16.8), (61.9, 16.6), (62.05, 15.4)),
        ((62.2, 14.8), (62.1, 10.25), (61.7, 9.15)),
        ((60.9, 7.8), (58.9, 7.4), (58.2, 5.1)),
        ((56.65, -0.5), (55.25, -10.8), (49.5, -15.85)),
        ((44, -20.5), (37.2, -21.1), (31.55, -20.7)),
        ((23.15, -20.1), (16.50, -16.8), (13.35, -12.2)),
        ((10.45, -7.7), (8, 1.4), (6.35, 5.7)),
        ((5.2, 8.3), (2.1, 9.0), (0, 9.0)),
    ],
)
APERTURE_HOST = bezier_path(
    (11.15, 11.7),
    [
        ((13.8, 16.4), (20.9, 18.65), (31.0, 18.65)),
        ((41.85, 18.9), (48.15, 17.35), (52.55, 15.6)),
        ((56.6, 14.0), (57.4, 10), (55.75, 3.8)),
        ((54.5, -2.0), (53.3, -9.2), (48.0, -13.9)),
        ((43.45, -17.7), (36.1, -19.2), (31.5, -18.3)),
        ((23.8, -17.7), (18.55, -14.9), (15.6, -10.9)),
        ((12.8, -6.9), (11.1, 0.75), (9.98, 5.3)),
        ((9.55, 7.8), (9.95, 10.1), (11.15, 11.7)),
    ],
)[:-1]


def wrap(x):
    return 0.00076 * x * x


def bend_front(data):
    # The planar tessellator draws long triangles along the brows. Add stations
    # before bowing the sheet so their faces follow the wrap of a real frame.
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.00005)
    for x in range(-60, 61, 6):
        bmesh.ops.bisect_plane(
            bm,
            geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
            plane_co=(x, 0, 0),
            plane_no=(1, 0, 0),
            dist=0.00005,
        )
    bm.to_mesh(data)
    bm.free()
    data.update()
    for face in data.polygons:
        face.use_smooth = True

    # Transform the manufactured flat-face and milling-radius normals with the
    # same bend. This keeps moving studio reflections continuous across the brow.
    normals = [corner.vector.copy() for corner in data.corner_normals]
    cut_edges = []
    for face in data.polygons:
        nz = face.normal.z
        if abs(nz) < 0.93:
            cut_edges.append(face.index)
        if abs(nz) > 0.9999:
            for index in face.loop_indices:
                normals[index] = Vector((0, 0, math.copysign(1, nz)))
    for i, loop in enumerate(data.loops):
        x = data.vertices[loop.vertex_index].co.x
        nx, nh, nd = normals[i]
        normals[i] = Vector((nx + 0.00152 * x * nd, -nd, nh)).normalized()
    for vertex in data.vertices:
        x, z, depth = vertex.co
        vertex.co = units((x, wrap(x) - depth, z))
    data.update()
    data.normals_split_custom_set(normals)
    return cut_edges


def front_block(m, host):
    half = HALF_HOST if host else HALF
    aperture = APERTURE_HOST if host else APERTURE
    outline = half + [(-x, z) for x, z in reversed(half[1:-1])]
    paths = [outline, list(reversed(aperture)), [(-x, z) for x, z in aperture]]
    data = bpy.data.curves.new("CNC front master", "CURVE")
    data.dimensions = "2D"
    data.fill_mode = "BOTH"
    data.resolution_u = 1
    data.extrude = 1.02 if host else 1.13
    data.bevel_depth = 0.46 if host else 0.67
    data.bevel_resolution = 4
    for path in paths:
        spline = data.splines.new("POLY")
        spline.points.add(len(path) - 1)
        for point, (x, z) in zip(spline.points, path):
            point.co = (x, z, 0, 1)
        spline.use_cyclic_u = True
        spline.use_smooth = True
    outline_obj = bpy.data.objects.new("Front outline", data)
    bpy.context.collection.objects.link(outline_obj)
    dg = bpy.context.evaluated_depsgraph_get()
    final = bpy.data.meshes.new_from_object(outline_obj.evaluated_get(dg))
    bpy.data.objects.remove(outline_obj, do_unlink=True)
    # The exposed milling radius has a polished, clearer edge that catches
    # light separately from the broad flat face of the acetate sheet.
    cut_edges = bend_front(final)
    obj = bpy.data.objects.new("Continuous front", final)
    bpy.context.collection.objects.link(obj)
    register(
        obj,
        "One-piece optical front" if host else "Sculpted smoke full-rim",
        "rim",
        m["host" if host else "acetate"],
    )
    if not host:
        final.materials.append(m["acetate_edge"])
        for index in cut_edges:
            final.polygons[index].material_index = 1
    anchor("rim", (36, wrap(36) - 1.7, -19.2))
    for side in (-1, 1):
        verts = [(side * 33, wrap(33) - 1.46, 0)]
        for j in range(1, 7):
            t = j / 6
            for a, b in aperture:
                x, z = side * (33 + t * (a - 33)), b * t
                verts.append((x, wrap(x) - 0.05 - 1.42 * (1 - t * t), z))
        count = len(aperture)
        faces = [(0, j + 1, (j + 1) % count + 1) for j in range(count)]
        faces += [tuple(i + 1 for i in reversed(f)) for f in rings_faces(6, count)]
        if side == 1:
            faces = [tuple(reversed(f)) for f in faces]
        mesh(
            "Prescription lens" if host else "Plano optical lens",
            verts,
            faces,
            "lens",
            m["clear" if host else "lens"],
        )
    anchor("lens", (-33, wrap(33) - 1.5, 0))
    # Secondary spot is used for the other lens opening in the static poster.
    empty(
        "Opposite optical centre", (33, wrap(33) - 1.5, 0), "posterAnchor", "lens-other"
    )


def curve_samples(knots, steps=5):
    """Centripetal-ish cubic transitions through the arm cross sections."""
    for i in range(len(knots) - 1):
        p0, p1 = knots[max(i - 1, 0)], knots[i]
        p2, p3 = knots[i + 1], knots[min(i + 2, len(knots) - 1)]
        for j in range(steps):
            t = j / steps
            yield [
                0.5
                * (
                    2 * a1
                    + (-a0 + a2) * t
                    + (2 * a0 - 5 * a1 + 4 * a2 - a3) * t * t
                    + (-a0 + 3 * a1 - 3 * a2 + a3) * t * t * t
                )
                for a0, a1, a2, a3 in zip(p0, p1, p2, p3)
            ]
    yield knots[-1]


def sweep_temple(name, side, knots, part, mat):
    verts = []
    rings = list(curve_samples(knots))
    count = 20
    for y, x, z, w, h in rings:
        for k in range(count):
            a = TAU * k / count
            c, s = math.cos(a), math.sin(a)
            u, v = math.copysign(abs(c) ** 0.51, c), math.copysign(abs(s) ** 0.51, s)
            verts.append((side * (x + w / 2 * u), y, z + h / 2 * v))
    faces = rings_faces(len(rings), count, caps=True)
    if side == 1:
        faces = [tuple(reversed(f)) for f in faces]
    return mesh(name, verts, faces, part, mat)


def optics(m, part, pos, r, gold=False):
    x, y, z = pos
    lathe(
        "Precision bezel",
        pos,
        [
            (r * 0.83, -0.09),
            (r, 0),
            (r, 0.05 * r),
            (r * 0.94, 0.145 * r),
            (r * 0.84, 0.15 * r),
            (r * 0.80, 0.085 * r),
        ],
        part,
        m["gold" if gold else "dark"],
    )
    lathe(
        "Lens barrel",
        pos,
        [
            (r * 0.83, 0.03 * r),
            (r * 0.84, 0.12 * r),
            (r * 0.78, 0.17 * r),
            (r * 0.64, 0.17 * r),
            (r * 0.57, 0.085 * r),
        ],
        part,
        m["crystal"],
    )
    lathe(
        "Optical coating",
        pos,
        [
            (r * 0.66, 0.087 * r),
            (r * 0.58, 0.145 * r),
            (r * 0.38, 0.17 * r),
            (0.0001, 0.16 * r),
        ],
        part,
        m["sensor"],
    )
    lathe(
        "Aperture ring",
        pos,
        [
            (r * 0.36, 0.175 * r),
            (r * 0.31, 0.20 * r),
            (r * 0.25, 0.207 * r),
            (r * 0.22, 0.19 * r),
        ],
        part,
        m["iris"],
    )
    ellipsoid(
        "Camera aperture",
        (x, y - 0.19 * r, z),
        (r * 0.24, r * 0.022, r * 0.24),
        part,
        m["dark"],
        segments=20,
    )


def indicator(m, pos, r):
    lathe(
        "Indicator socket",
        pos,
        [(r * 1.22, -0.04), (r * 1.23, 0.04), (r * 0.95, 0.11)],
        "led",
        m["dark"],
    )
    x, y, z = pos
    ellipsoid(
        "Status light", (x, y - 0.06, z), (r, 0.13, r), "led", m["led"], segments=20
    )
    anchor("led", (x, y - 0.20, z))


def distance_window(m, pos, scale=1):
    x, y, z = pos
    plate(
        "Time-of-flight receiver surround",
        pos,
        7.0 * scale,
        3.15 * scale,
        0.43 * scale,
        1.16 * scale,
        0.18 * scale,
        "tof",
        m["dark"],
    )
    plate(
        "Infrared optical window",
        (x, y - 0.255 * scale, z),
        5.98 * scale,
        2.42 * scale,
        0.16 * scale,
        0.81 * scale,
        0.061 * scale,
        "tof",
        m["crystal"],
    )
    for dx, r in [(-1.30, 0.52), (1.10, 0.41)]:
        ellipsoid(
            "Infrared emitter / receiver",
            (x + dx * scale, y - 0.345 * scale, z),
            (r * scale, 0.055 * scale, r * scale),
            "tof",
            m["sensor" if dx < 0 else "iris"],
            segments=18,
        )
    anchor("tof", (x, y - 0.47 * scale, z))


def ambient(m, pos, r):
    x, y, z = pos
    lathe(
        "Illuminance bezel",
        pos,
        [(r * 0.86, -0.06), (r, 0.02), (r * 0.98, 0.13), (r * 0.86, 0.21)],
        "light",
        m["dark"],
    )
    ellipsoid(
        "Light meter window",
        (x, y - 0.14, z),
        (r * 0.86, 0.18, r * 0.86),
        "light",
        m["crystal"],
        segments=24,
    )
    anchor("light", (x, y - 0.35, z))


def screws(m, side, x, y, z, part):
    # A recessed slot in the circular screw cap faces the outside of the temple.
    ellipsoid(
        "Polished hinge pin",
        (side * x, y, z),
        (0.09, 0.84, 0.84),
        part,
        m["edge"],
        segments=20,
    )
    slot = box(
        "Hinge screw slot",
        (side * (x + 0.08), y, z),
        (0.04, 1.02, 0.16),
        0.044,
        part,
        m["dark"],
    )
    slot.rotation_euler.x = -0.42


def legend(text, pos, size, part, mat, side=None):
    data = bpy.data.curves.new("Laser engraving", "FONT")
    data.body = text
    data.size = size * UNIT
    data.align_x = "CENTER"
    data.align_y = "CENTER"
    obj = bpy.data.objects.new("Engraved marking", data)
    bpy.context.collection.objects.link(obj)
    obj.location = units(pos)
    obj.rotation_euler = (math.pi / 2, 0, side * math.pi / 2 if side else 0)
    register(obj, "Engraved " + text, part, mat)
    dg = bpy.context.evaluated_depsgraph_get()
    final = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    local = obj.matrix_local.copy()
    parent = obj.parent
    bpy.data.objects.remove(obj, do_unlink=True)
    baked = bpy.data.objects.new("Engraved " + text, final)
    bpy.context.collection.objects.link(baked)
    baked.parent = parent
    baked.matrix_local = local
    baked["part"] = part


def circuit_details(m, x):
    face_x = x - 0.438
    routes = [
        [(19.6, 9.8), (20.1, 9.8), (20.85, 9.05), (26.4, 9.05), (26.8, 9.46)],
        [(19.6, 10.7), (20.1, 10.7), (20.72, 10.05)],
        [(19.6, 12.5), (20.15, 12.5), (20.8, 13.12)],
        [(19.6, 13.4), (20.1, 13.4), (20.60, 13.91), (28.6, 13.91), (29.03, 13.49)],
        [(31.4, 12.9), (31.97, 12.9), (32.6, 13.54), (34.12, 13.54), (34.8, 12.85)],
        [(31.4, 10.9), (33.2, 10.9), (33.82, 10.28), (34.91, 10.28)],
        [(38.45, 13.52), (38.45, 13.68), (38.85, 14.06), (43.1, 14.06), (44.0, 13.14)],
        [(40.55, 12.83), (41.27, 12.83), (41.86, 12.24), (42.92, 12.24)],
        [(46.1, 12.70), (46.55, 12.70), (47.18, 12.06), (47.66, 12.06)],
        [(46.1, 10.40), (46.53, 10.40), (47.05, 10.93), (47.66, 10.93)],
        [(48.7, 12.71), (48.7, 13.15), (49.2, 13.65), (50.75, 13.65), (51.23, 13.18)],
    ]
    for i in range(3):
        routes.append(
            [
                (35.94 + i * 1.25, 9.51),
                (35.94 + i * 1.25, 9.41),
                (36.37 + i * 1.25, 8.98 + i * 0.12),
                (42.75 + i * 0.55, 8.98 + i * 0.12),
                (43.7 + i * 0.55, 9.94 + i * 0.12),
            ]
        )
    vertices, faces = [], []
    for route in routes:
        base = len(vertices)
        points = [Vector(p) for p in route]
        for i, p in enumerate(points):
            before = (p - points[max(i - 1, 0)]).normalized()
            after = (points[min(i + 1, len(points) - 1)] - p).normalized()
            tangent = (before + after).normalized()
            offset = Vector((-tangent.y, tangent.x)) * 0.067
            vertices.extend((face_x, *(p + signed * offset)) for signed in (1, -1))
            if i:
                a = base + (i - 1) * 2
                faces.append((a, a + 2, a + 3, a + 1))
    mesh("Etched interconnects", vertices, faces, "board", m["traces"], smooth=False)

    vertices, faces = [], []
    for y, z in [
        (20.15, 11.55),
        (21.12, 13.86),
        (29.10, 9.03),
        (31.96, 13.98),
        (32.25, 9.87),
        (33.84, 13.83),
        (41.89, 13.68),
        (42.20, 10.33),
        (46.98, 13.32),
        (47.43, 9.46),
        (50.87, 12.68),
        (51.10, 10.56),
    ]:
        start = len(vertices)
        for radius in (0.185, 0.081):
            for i in range(12):
                a = TAU * i / 12
                vertices.append(
                    (face_x - 0.014, y + radius * math.cos(a), z + radius * math.sin(a))
                )
        for i in range(12):
            j = (i + 1) % 12
            faces.append((start + j, start + i, start + 12 + i, start + 12 + j))
    mesh("Plated microvias", vertices, faces, "board", m["pins"], smooth=False)
    for i in range(5):
        box(
            "Flex connector pad",
            (face_x - 0.045, 19.28, 9.8 + i * 0.90),
            (0.11, 1.35, 0.42),
            0.045,
            "board",
            m["pins"],
        )
    for y, z in [(32.15, 12.00), (33.40, 12.00), (42.01, 11.22), (50.91, 11.73)]:
        box(
            "Ceramic capacitor lands",
            (face_x - 0.06, y, z),
            (0.14, 0.94, 0.46),
            0.06,
            "board",
            m["edge"],
        )
        box(
            "Surface-mount capacitor",
            (face_x - 0.17, y, z),
            (0.28, 0.55, 0.40),
            0.06,
            "board",
            m["gold"],
        )


def internals(m, side):
    if side < 0:
        x = -61.8
        box(
            "Logic board",
            (x, 35.2, 11.45),
            (0.83, 34.3, 5.62),
            0.35,
            "board",
            m["board"],
        )
        box(
            "RF shield",
            (x - 0.63, 26.1, 11.45),
            (0.5, 10.7, 4.25),
            0.20,
            "board",
            m["cellmetal"],
        )
        legend("LumiRead", (x - 0.889, 26.1, 11.45), 1.58, "board", m["dark"], side=-1)
        circuit_details(m, x)
        for y, w, h in [(37.9, 6.3, 4.1), (44.5, 3.4, 3.2), (49.0, 2.85, 2.25)]:
            box(
                "Processor package",
                (x - 0.69, y, 11.5),
                (0.55, w, h),
                0.14,
                "board",
                m["chip"],
            )
            for d in (-1, 1):
                for i in range(4):
                    yy = y - w * 0.31 + i * w * 0.205
                    box(
                        "Chip contacts",
                        (x - 0.65, yy, 11.5 + d * h * 0.51),
                        (0.34, 0.33, 0.43),
                        0.053,
                        "board",
                        m["pins"],
                    )
        for y in (21, 33, 42.1, 51.0):
            box(
                "Solder test point",
                (x - 0.45, y, 9.32),
                (0.12, 1, 0.48),
                0.064,
                "board",
                m["pins"],
            )
        anchor("board", (x - 0.98, 36.0, 11.55))
    else:
        x = 61.8
        box(
            "Rechargeable cell",
            (x, 35.35, 11.45),
            (2.25, 35.0, 5.8),
            0.54,
            "battery",
            m["cell"],
        )
        box(
            "Battery foil jacket",
            (x + 1.03, 35.3, 11.45),
            (0.32, 31.5, 4.8),
            0.14,
            "battery",
            m["cellmetal"],
        )
        for y in (21.0, 49.6):
            box(
                "Cell seal",
                (x + 1.08, y, 11.45),
                (0.33, 1.0, 4.92),
                0.13,
                "battery",
                m["cell"],
            )
        legend("Li-ion", (x + 1.245, 37, 11.45), 1.55, "battery", m["dark"], side=1)
        anchor("battery", (x + 1.3, 35.0, 11.4))


def temples(m, host):
    for side in (-1, 1):
        part = "temple-right" if side < 0 else "temple-left"
        shift_x = -2.0 if host else 0
        w = 0.67 if host else 1
        x = 61.8 + shift_x
        hinge_y = 10.0
        front_joint = [
            (2.4, x - 0.6, 12.90, 4.0 * w, 6.7 * w),
            (5.7, x, 12.88, 4.9 * w, 6.88 * w),
            (8.9, x + 0.08, 12.83, 4.95 * w, 6.84 * w),
        ]
        sweep_temple(
            "Endpiece", side, front_joint, "rim", m["host" if host else "acetate"]
        )
        hinge = [
            (8.9, x + 0.09, 12.83, 4.98 * w, 6.86 * w),
            (9.1, x + 0.09, 12.83, 5.03 * w, 6.88 * w),
            (13.25, x + 0.15, 12.73, 5.04 * w, 6.77 * w),
            (13.47, x + 0.15, 12.73, 4.98 * w, 6.72 * w),
        ]
        sweep_temple("Satin barrel hinge", side, hinge, "hinge", m["gold"])
        screws(m, side, x + 0.11 + 2.52 * w, hinge_y + 1.9, 12.7, "hinge")
        # Individual temple sleeves allow a local cutaway over the board/cell.
        arm = [
            (13.45, x + 0.15, 12.72, 4.9 * w, 6.72 * w),
            (14.5, x + 0.18, 12.69, 5.06 * w, 7.36 * w),
            (19, x + 0.14, 12.3, 5.28 * w, 8.0 * w),
            (29, x + 0.05, 11.72, 5.34 * w, 8.14 * w),
            (42, x + 0.13, 11.49, 5.24 * w, 8.07 * w),
            (55, x + 0.55, 11.18, 4.65 * w, 7.33 * w),
            (69, x + 1.07, 11.08, 3.92 * w, 6.3 * w),
            (84, x + 1.37, 10.95, 3.53 * w, 5.96 * w),
            (97, x + 0.8, 10.2, 3.58 * w, 5.88 * w),
            (104, x + 0.10, 9.12, 3.65 * w, 5.80 * w),
        ]
        sweep_temple(
            "Optical side arm" if host else "Electronics temple cover",
            side,
            arm,
            part,
            m["host" if host else "acetate"],
        )
        tip = [
            arm[-1],
            (109, x - 0.58, 7.98, 3.60 * w, 5.75 * w),
            (115.1, x - 1.63, 5.2, 3.59 * w, 5.75 * w),
            (122.35, x - 2.6, 0.30, 3.64 * w, 5.89 * w),
            (129.0, x - 3.85, -5.20, 3.75 * w, 6.34 * w),
            (132.65, x - 4.30, -7.3, 3.9 * w, 6.29 * w),
            (135.2, x - 4.60, -7.99, 3.24 * w, 4.9 * w),
            (136.75, x - 4.74, -7.8, 0.70 * w, 1.18 * w),
        ]
        sweep_temple("Silicone earpiece", side, tip, "ear", m["tip"])
        if not host:
            internals(m, side)
            if side == 1:
                legend(
                    "LumiRead",
                    (side * (x + 2.76), 24.4, 12.35),
                    1.62,
                    part,
                    m["edge"],
                    side=side,
                )
        if side == 1:
            anchor("hinge", (side * (x + 2.5 * w), 11.4, 12.75))
            anchor("ear", (side * (x - 2.0), 125, -2.0))
        anchor(part, (side * (x + 2.73 * w), 34, 11.7))
        pad_x = 8.7 if host else 8.0
        ellipsoid(
            "Pad mount",
            (side * (pad_x + 0.45), 2.85, 0.7),
            (1.25, 2.38, 3.8),
            "nose",
            m["host" if host else "acetate"],
            side * 15,
        )
        ellipsoid(
            "Silicone nose pad",
            (side * pad_x, 4.52, -1.35),
            (2.42, 2.18, 7.05),
            "nose",
            m["nose"],
            side * 17,
        )
        if side == -1:
            anchor("nose", (-pad_x, 4.85, -3.48))


def eye_modules(m):
    for side in (-1, 1):
        x, z = side * 12.7, 13.0
        y = wrap(x) + 2.25
        pod = plate(
            "Inward camera carrier",
            (x, y, z),
            6.2,
            4.25,
            1.7,
            1.8,
            0.21,
            "eye",
            m["dark"],
        )
        pod.rotation_euler.z = side * -0.21
        optic = lathe(
            "Inward eye objective",
            (x, y + 0.87, z),
            [(1.55, 0), (1.52, 0.32), (1.21, 0.50), (0.96, 0.48), (0.84, 0.33)],
            "eye",
            m["edge"],
        )
        optic.rotation_euler.z = math.pi - side * 0.25
        ellipsoid(
            "Eye camera glass", (x, y + 1.31, z), (1.15, 0.19, 1.15), "eye", m["sensor"]
        )
        ellipsoid(
            "Eye camera pupil",
            (x, y + 1.47, z),
            (0.46, 0.10, 0.46),
            "eye",
            m["crystal"],
        )
        for dz in (-0.55, 0.62):
            ellipsoid(
                "Near infrared illuminator",
                (x + side * 2.1, y + 0.94, z + dz),
                (0.36, 0.22, 0.36),
                "eye",
                m["iris"],
            )
        if side == 1:
            anchor("eye", (x, y + 1.67, z))


def frame_controls(m):
    for side in (-1, 1):
        box(
            "Capacitive temple strip",
            (side * 64.83, 68.8, 11.13),
            (0.23, 10.8, 1.85),
            0.11,
            "touch",
            m["dark"],
        )
        for dy in (-2.1, 0, 2.1):
            box(
                "Touch strip index",
                (side * 64.96, 68.8 + dy, 11.13),
                (0.06, 0.20, 0.90),
                0.025,
                "touch",
                m["frost"],
            )
    anchor("touch", (-65.01, 68.8, 11.13))
    box(
        "Six-axis inertial sensor",
        (-62.59, 32.9, 11.27),
        (0.62, 2.6, 2.6),
        0.18,
        "imu",
        m["chip"],
    )
    ellipsoid(
        "IMU pin one", (-62.92, 32.22, 11.94), (0.045, 0.19, 0.19), "imu", m["pins"]
    )
    anchor("imu", (-62.95, 32.9, 11.27))
    for y in (47.3, 50.2):
        ellipsoid(
            "Dock charging contact",
            (62.2, y, 7.42),
            (0.80, 1.0, 0.27),
            "charge",
            m["pins"],
        )
    anchor("charge", (62.2, 49, 7.15))
    box(
        "Antenna carrier",
        (-62.3, 55.3, 11.2),
        (0.48, 6.0, 4.2),
        0.14,
        "radio",
        m["board"],
    )
    for i in range(4):
        box(
            "Meander antenna trace",
            (-62.57, 53.2 + 1.38 * i, 11.2),
            (0.06, 0.28, 3.15),
            0.02,
            "radio",
            m["pins"],
        )
        if i < 3:
            box(
                "Antenna trace return",
                (-62.57, 53.89 + 1.38 * i, 11.2 + (-1) ** i * 1.45),
                (0.06, 1.5, 0.26),
                0.02,
                "radio",
                m["pins"],
            )
    anchor("radio", (-62.7, 55.3, 11.2))


def clip_electronics(m, x, y, z):
    board = "clip-core"
    plate(
        "Clip radio and sensor PCB",
        (x - 7.6, y + 0.6, z),
        18.8,
        7.6,
        0.70,
        1.5,
        0.18,
        board,
        m["board"],
    )
    plate(
        "Clip processor", (x - 8.8, y, z), 4.6, 3.9, 0.72, 0.34, 0.12, board, m["chip"]
    )
    for dx in (-14.5, -12.6, -4, -2.3):
        for dz in (-1.9, 1.9):
            box(
                "Clip component land",
                (x + dx, y + 0.16, z + dz),
                (1.1, 0.30, 0.62),
                0.09,
                board,
                m["pins"],
            )
    plate(
        "Clip lithium cell",
        (x + 9.3, y + 0.50, z),
        14.9,
        8.2,
        3.65,
        1.3,
        0.28,
        board,
        m["cell"],
    )
    plate(
        "Clip cell foil",
        (x + 9.3, y - 1.33, z),
        13.5,
        7.4,
        0.14,
        1.0,
        0.05,
        board,
        m["cellmetal"],
    )
    for dx in (1.6, 2.8):
        box(
            "Cell flex tab",
            (x + dx, y - 0.14, z + 1.2),
            (0.56, 0.35, 2.35),
            0.08,
            board,
            m["pins"],
        )
    anchor(board, (x - 1.1, y - 0.75, z))
    plate(
        "RF polymer antenna window",
        (x + 17.9, y - 3.67, z + 0.12),
        2.5,
        5.7,
        1.0,
        1.12,
        0.24,
        "radio",
        m["dark"],
    )
    anchor("radio", (x + 17.9, y - 4.23, z + 0.12))
    for dx in (6.8, 10.2):
        ellipsoid(
            "Clip charging contact",
            (x + dx, y, z - 6.04),
            (0.93, 1.05, 0.25),
            "charge",
            m["pins"],
        )
    anchor("charge", (x + 8.5, y, z - 6.29))


def integrated(m):
    front_block(m, False)
    temples(m, False)
    x, z = -60.30, 13.24
    front = wrap(x) - 1.83
    optics(m, "camera", (x, front, z), 2.5, gold=True)
    anchor("camera", (x, front - 0.57, z))
    indicator(m, (-56.37, wrap(-56.37) - 1.90, 14.33), 0.56)
    ambient(m, (60.2, wrap(60.2) - 1.86, 13.1), 1.38)
    distance_window(m, (0, -1.83, 10.08))
    eye_modules(m)
    frame_controls(m)


def clipped(m):
    front_block(m, True)
    temples(m, True)
    x, y, z = -37.4, -3.64, 19.6
    module = empty("Removable magnesium accessory", (x, y, z), "role", "clip-module")
    with inside(module):
        body_y = y - 3.26
        clip_electronics(m, x, body_y, z)
        plate(
            "Machined magnesium housing",
            (x, body_y, z),
            41.1,
            12.15,
            7.55,
            4.6,
            0.72,
            "shell",
            m["silver"],
        )
        plate(
            "Rear housing seam",
            (x, body_y + 3.51, z),
            40.12,
            11.54,
            0.30,
            4.27,
            0.10,
            "shell",
            m["gasket"],
        )
        plate(
            "Rear shell",
            (x, body_y + 3.56, z),
            40.36,
            11.75,
            0.91,
            4.26,
            0.23,
            "shell",
            m["silver"],
        )
        fy = body_y - 3.90
        plate(
            "Continuous optical fascia",
            (x - 6.67, fy, z + 0.12),
            24.86,
            9.68,
            0.77,
            4.08,
            0.24,
            "shell",
            m["dark"],
        )
        plate(
            "Black glass sensor band",
            (x - 6.67, fy - 0.39, z + 0.12),
            24.17,
            9.19,
            0.28,
            3.96,
            0.13,
            "shell",
            m["crystal"],
        )
        optics(m, "camera", (x - 13.34, fy - 0.58, z + 0.31), 2.12)
        anchor("camera", (x - 13.34, fy - 1.06, z + 0.31))
        distance_window(m, (x - 6.1, fy - 0.56, z + 0.18), 0.81)
        ambient(m, (x + 1.32, fy - 0.61, z + 0.15), 1.41)
        indicator(m, (x - 10.15, fy - 0.6, z + 2.51), 0.36)
        legend("LumiRead", (x + 12.8, fy + 0.02, z - 0.57), 2.04, "shell", m["dark"])
        anchor("shell", (x + 12.2, fy, z - 0.22))
        box(
            "Button undercut",
            (x + 4.4, body_y, z + 6.05),
            (7.73, 3.20, 0.72),
            0.31,
            "button",
            m["dark"],
        )
        box(
            "Tactile top button",
            (x + 4.4, body_y, z + 6.51),
            (7.36, 2.93, 0.76),
            0.35,
            "button",
            m["frost"],
        )
        box(
            "Tactile index",
            (x + 4.4, body_y, z + 6.92),
            (3.0, 0.25, 0.066),
            0.03,
            "button",
            m["silver"],
        )
        anchor("button", (x + 4.4, body_y, z + 7.03))
        # A saddle clamps the upper rim from both sides. The rear jaw rotates
        # about the X-axis shaft. Positive glTF X rotation opens the jaw.
        axis_y, axis_z = 1.87, 23.63
        box(
            "Spring clip saddle",
            (x, 0.05, 23.42),
            (18.4, 7.6, 2.34),
            0.79,
            "clamp",
            m["silver"],
        )
        for dx in (-7.70, 7.70):
            box(
                "Fixed spring lug",
                (x + dx, axis_y, axis_z - 0.32),
                (2.47, 3.8, 4.13),
                0.96,
                "clamp",
                m["silver"],
            )
            ellipsoid(
                "Spring pin",
                (x + dx, axis_y, axis_z),
                (1.38, 1.32, 1.32),
                "clamp",
                m["gold"],
            )
        shaft = [
            (dx, 0.73 * math.cos(TAU * j / 24), 0.73 * math.sin(TAU * j / 24))
            for dx in (-8.1, 8.1)
            for j in range(24)
        ]
        mesh(
            "Spring pivot axle",
            shaft,
            rings_faces(2, 24, caps=True),
            "clamp",
            m["edge"],
            (x, axis_y, axis_z),
        )
        box(
            "Fixed grip pad",
            (x, -0.48, 20.05),
            (15.7, 1.39, 4.42),
            0.61,
            "pad",
            m["gasket"],
        )
        jaw = empty("Spring jaw pivot", (x, axis_y, axis_z), "role", "clip-jaw")
        with inside(jaw):
            box(
                "Jaw pivot knuckle",
                (x, axis_y + 0.89, axis_z - 0.06),
                (12.52, 3.42, 2.41),
                1.08,
                "clamp",
                m["silver"],
            )
            box(
                "Spring grip lever",
                (x, 4.11, 21.04),
                (17.45, 1.97, 8.22),
                0.84,
                "clamp",
                m["silver"],
            )
            box(
                "Rear silicone cushion",
                (x, 3.15, 19.81),
                (15.48, 1.0, 4.83),
                0.45,
                "pad",
                m["gasket"],
            )
            for j in range(9):
                box(
                    "Moulded grip rib",
                    (x - 6.1 + j * 1.52, 2.62, 19.75),
                    (0.43, 0.19, 3.16),
                    0.085,
                    "pad",
                    m["tip"],
                )
            anchor("pad", (x + 0.44, 3.00, 18.67))
            anchor("clamp", (x + 2.55, 5.31, 22.16))


def point_at(obj, point):
    obj.rotation_euler = (
        (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()
    )


def studio():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 5
    scene.render.film_transparent = True
    scene.render.resolution_x = 1440
    scene.render.resolution_y = 850
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "WEBP"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.quality = 93
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("Silver photographic studio")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.72, 0.76, 0.85, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.26
    scene.world = world
    # Tall, narrow softboxes give acetate a polished edge while broad frontal
    # fill separates the smoke-coloured surfaces from a charcoal page.
    for pos, energy, width, height, tint in [
        ((-1.0, -2.2, 2.2), 92, 2.96, 0.34, (0.88, 0.93, 1.0)),
        ((1.75, -0.16, 1.37), 73, 0.36, 2.50, (1.0, 0.84, 0.73)),
        ((0.30, 1.82, 1.95), 102, 2.46, 0.49, (0.72, 0.84, 1.0)),
        ((-1.9, 0.72, 0.32), 40, 0.43, 1.80, (0.78, 0.86, 1.0)),
        ((0.55, -2.51, -0.06), 23, 1.60, 1.16, (0.92, 0.94, 1.0)),
        ((-1.77, -1.82, 0.38), 22, 0.58, 1.66, (0.85, 0.91, 1.0)),
    ]:
        bpy.ops.object.light_add(type="AREA", location=pos)
        lamp = bpy.context.object
        lamp.data.energy = energy
        lamp.data.color = tint
        lamp.data.shape = "RECTANGLE"
        lamp.data.size, lamp.data.size_y = width, height
        point_at(lamp, (0, 0.35, 0.0))
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.data.type = "PERSP"
    cam.data.sensor_fit = "VERTICAL"
    cam.data.lens = cam.data.sensor_height / (2 * math.tan(math.radians(12)))
    cam.data.clip_start = 0.03
    scene.camera = cam
    return scene


def poster(scene, name, azimuth, elevation, focus=None, span=None, retina=False):
    az, el = math.radians(azimuth), math.radians(elevation)
    direction = Vector(
        (math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))
    )
    cam = scene.camera
    cam.location = direction * 4
    point_at(cam, (0, 0, 0))
    bpy.context.view_layer.update()
    rot = cam.rotation_euler.to_matrix()
    right, up = rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0))
    anchors = {
        o.get("anchor") or o.get("posterAnchor"): o
        for o in scene.objects
        if o.get("anchor") or o.get("posterAnchor")
    }
    if focus == "board":
        anchors["processor"] = scene.objects["Processor package"]
    elif focus == "clip-core":
        anchors["pcb"] = scene.objects["Clip radio and sensor PCB"]
        anchors["cell"] = scene.objects["Clip cell foil"]
    slope = math.tan(math.radians(12))
    aspect = 1440 / 850
    if focus:
        target = anchors[focus].matrix_world.translation.copy()
        distance = span / (2 * slope * aspect)
    else:
        dg = bpy.context.evaluated_depsgraph_get()
        corners = []
        for obj in scene.objects:
            if obj.type == "MESH" and not obj.hide_render:
                ob = obj.evaluated_get(dg)
                corners.extend(ob.matrix_world @ v.co for v in ob.data.vertices)
        axes = (right, up, direction)
        coords = np.array([[p.dot(axis) for axis in axes] for p in corners])
        mid = (coords.min(axis=0) + coords.max(axis=0)) / 2
        target = sum((axis * float(c) for axis, c in zip(axes, mid)), Vector((0, 0, 0)))
        dx, dy, depth = (coords - mid).T
        distance = float(
            np.max(
                depth
                + np.maximum(
                    abs(dx) / (slope * aspect * 0.89), abs(dy) / (slope * 0.83)
                )
            )
        )
    cam.location = target + direction * distance
    point_at(cam, target)
    bpy.context.view_layer.update()
    scene.render.resolution_x, scene.render.resolution_y = (
        (2880, 1700) if retina else (1728, 1020)
    )
    points = {}
    for key, obj in anchors.items():
        v = world_to_camera_view(scene, cam, obj.matrix_world.translation)
        if v.z > 0 and 0 < v.x < 1 and 0 < v.y < 1:
            points[key] = [round(v.x, 5), round(1 - v.y, 5)]
    path = OUT / (name + ("@2x.webp" if retina else ".webp"))
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if retina:
        small = bpy.data.images.load(str(path))
        small.scale(1440, 850)
        small.filepath_raw = str(OUT / (name + ".webp"))
        small.file_format = "WEBP"
        small.save()
        bpy.data.images.remove(small)
    return points


def ground_shadow(name):
    """Bake a top-down contact mask from the underside height of the actual geometry."""
    scene = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    count, length = 144, 2.10
    height = np.full((count, count), np.inf)
    for row in range(count):
        for col in range(count):
            x = ((col + 0.5) / count - 0.5) * length
            y = ((row + 0.5) / count - 0.5) * length + 0.55
            hit, point, *_ = scene.ray_cast(
                dg, Vector((x, y, -0.225)), Vector((0, 0, 1)), distance=0.65
            )
            if hit:
                height[row, col] = max(0, point.z + 0.225)
    freqs = np.fft.fftfreq(count)
    radius = freqs[:, None] ** 2 + freqs[None, :] ** 2
    alpha = np.zeros_like(height)
    for sigma, decay, strength in [(2.2, 0.055, 0.56), (7.0, 0.24, 0.62)]:
        kernel = np.exp(-2 * math.pi**2 * sigma**2 * radius)
        alpha += (
            strength * np.fft.ifft2(np.fft.fft2(np.exp(-height / decay)) * kernel).real
        )
    pixels = np.ones((count, count, 4), dtype=np.float32)
    pixels[:, :, 3] = np.clip(alpha, 0, 1)
    im = bpy.data.images.new(
        name + " contact shadow", width=count, height=count, alpha=True
    )
    im.pixels.foreach_set(pixels.ravel())
    im.file_format = "PNG"
    im.filepath_raw = str(OUT / (name + "-shadow.png"))
    im.save()


def export_glb(name):
    bpy.ops.export_scene.gltf(
        filepath=str(OUT / (name + ".glb")),
        export_format="GLB",
        export_apply=True,
        export_extras=True,
        export_animations=False,
        export_texcoords=True,
        export_tangents=False,
        export_yup=True,
    )


def render_views(name, scene, covers_only=False):
    # Preserve original materials across passes; all optical modes share one master mesh.
    meshes = [o for o in scene.objects if o.type == "MESH"]
    original = {o: list(o.data.materials) for o in meshes}
    cutaway = material("Section skin", "8c9297", 0.27, 0.1, 0.24, 0.075)
    inside = {
        "board": "temple-right",
        "imu": "temple-right",
        "battery": "temple-left",
        "clip-core": "shell",
    }
    if name == "frame":
        inside["radio"] = "temple-right"

    def mode(shell=None, open_lens=False):
        for obj in meshes:
            part = obj.get("part")
            obj.hide_render = (part in inside and inside[part] != shell) or (
                open_lens and part == "lens"
            )
            if part in ("temple-right", "temple-left", "shell"):
                obj.data.materials.clear()
                for mat in original[obj]:
                    obj.data.materials.append(
                        cutaway if shell and part == shell else mat
                    )

    section_view = (
        ("board", -87, 13, 0.48, "temple-right")
        if name == "frame"
        else ("clip-core", -8, 22, 0.55, "shell")
    )
    part, az, el, span, _ = section_view
    mode()
    cover_points = poster(scene, name + "-closed", az, el, focus=part, span=span)
    if covers_only:
        return {("frame-board" if name == "frame" else "clip-inside"): cover_points}
    points = {name: poster(scene, name, 27, 12, retina=True)}
    if name == "frame":
        mode(open_lens=True)
        points["frame-open"] = poster(scene, "frame-open", 27, 12, retina=True)
        mode("temple-right")
        points["frame-inside"] = poster(scene, "frame-inside", -111, 24, retina=True)
        views = [
            ("camera", -13, 9, 0.24, None),
            ("tof", 9, 12, 0.26, None),
            ("light", 13, 10, 0.20, None),
            ("eye", 154, 12, 0.19, None),
            section_view,
            ("imu", -88, 9, 0.18, "temple-right"),
            ("radio", -88, 9, 0.18, "temple-right"),
            ("battery", 88, 12, 0.51, "temple-left"),
            ("charge", 55, -48, 0.23, None),
            ("touch", -86, 14, 0.29, None),
        ]
    else:
        views = [
            ("camera", -8, 15, 0.21, None),
            ("tof", 8, 13, 0.21, None),
            ("light", 9, 12, 0.20, None),
            section_view,
            ("clamp", 155, 35, 0.43, None),
            ("button", 12, 53, 0.32, None),
            ("charge", 14, -60, 0.34, None),
            ("radio", 17, 9, 0.28, None),
        ]
    for part, az, el, span, shell in views:
        mode(shell)
        key = "clip-inside" if part == "clip-core" else name + "-" + part
        points[key] = poster(scene, key, az, el, focus=part, span=span)
    return points


def main():
    global OUT
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--output" in args:
        OUT = Path(args[args.index("--output") + 1]).resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    points = {}
    covers_only = "--guide-covers-only" in args
    manifest = OUT / "poster-points.json"
    if covers_only and manifest.is_file():
        points = json.loads(manifest.read_text(encoding="utf-8"))
    for name, build in [("frame", integrated), ("clip", clipped)]:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        build(materials())
        bpy.context.view_layer.update()
        if covers_only:
            points.update(render_views(name, studio(), covers_only=True))
            continue
        export_glb(name)
        ground_shadow(name)
        if "--models-only" not in args:
            points.update(render_views(name, studio()))
    if points:
        manifest.write_text(json.dumps(points, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

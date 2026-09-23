"""Runs inside Blender: renders item previews (a weapon in a skin, a charm) from glTF folders.

blender --background --factory-startup --python blender_thumbs.py -- <jobs.json | ->
a job: {"folder": dir with .gltf files (any depth), "out": png path, "kind": "weapon" | "charm"}; jobs.json holds a list,
"-" reads one job per line from stdin until it closes (the engine keeps a few Blenders open this way). After
each job a line "THUMB <n>" says it's done.

EEVEE, transparent background, orthographic camera fitted to the item: a weapon from its side, a charm
from both faces (<out>.back.png for the second), turned a little so it reads as an object. About 0.15 s an item after Blender starts.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SIZES = {"weapon": (560, 320), "charm": (360, 360)}


def setup() -> tuple:
    scene = bpy.context.scene
    for thing in list(bpy.data.objects):
        bpy.data.objects.remove(thing)
    engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 16
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"  # the textures' own colors, not a filmic curve
    world = bpy.data.worlds.new("preview")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.57, 0.62, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    scene.world = world
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    camera.data.type = "ORTHO"
    scene.collection.objects.link(camera)
    scene.camera = camera
    for name, energy, rotation in (("key", 3.2, (50, 0, 35)), ("rim", 1.6, (-60, 0, 200))):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
        light.data.energy = energy
        light.rotation_euler = [math.radians(a) for a in rotation]
        scene.collection.objects.link(light)
    return scene, camera


def frame(camera, objects: list, kind: str, aspect: float, back: bool = False) -> None:
    """Point the camera at the item and fit the orthographic view to it, with a margin. The vertices as
    posed, not bound boxes: a magazine hangs from a bone, and its box would be the armature's."""
    graph = bpy.context.evaluated_depsgraph_get()
    corners = []
    for thing in objects:
        posed = thing.evaluated_get(graph)
        mesh = posed.to_mesh()
        corners += [posed.matrix_world @ v.co for v in mesh.vertices]
        posed.to_mesh_clear()
    low = Vector([min(p[i] for p in corners) for i in range(3)])
    high = Vector([max(p[i] for p in corners) for i in range(3)])
    size = high - low
    if kind == "weapon":  # look across the long axis, a little from above and ahead
        across = Vector((0, -1, 0)) if size.x >= size.y else Vector((1, 0, 0))
        along = Vector((1, 0, 0)) if size.x >= size.y else Vector((0, 1, 0))
        direction = (across + along * 0.18 + Vector((0, 0, 0.22))).normalized()
    else:  # a charm faces across its thinnest side (flat ones would show their edge otherwise)
        facing = Vector((0, -1, 0)) if size.y <= size.x else Vector((1, 0, 0))
        side = Vector((1, 0, 0)) if size.y <= size.x else Vector((0, 1, 0))
        direction = ((-facing if back else facing) + side * 0.35 + Vector((0, 0, 0.15))).normalized()
    center = (low + high) / 2
    reach = max(size.length, 1e-4)
    camera.location = center + direction * reach * 2
    camera.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    camera.data.clip_start = reach * 0.01
    camera.data.clip_end = reach * 5
    bpy.context.view_layer.update()
    view = camera.matrix_world.inverted()
    flat = [view @ p for p in corners]
    xs, ys = [p.x for p in flat], [p.y for p in flat]
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    shift = Vector(((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, 0))
    camera.location = camera.matrix_world @ shift
    camera.data.sensor_fit = "HORIZONTAL"
    camera.data.ortho_scale = max(width, height * aspect, 1e-4) * 1.12


def main() -> None:
    source = sys.argv[sys.argv.index("--") + 1]
    jobs = (json.loads(line) for line in iter(sys.stdin.readline, "") if line.strip()) if source == "-" else json.loads(Path(source).read_text(encoding="utf-8"))
    scene, camera = setup()
    for number, job in enumerate(jobs, 1):
        before = set(bpy.data.objects)
        try:
            for gltf in sorted(Path(job["folder"]).rglob("*.gltf")):
                bpy.ops.import_scene.gltf(filepath=str(gltf))
            # not the importer's bone-shape icosphere (1 m, in a hidden collection): it would shrink the item to a dot
            meshes = [o for o in bpy.data.objects if o not in before and o.type == "MESH" and o.visible_get()]
            if meshes:
                width, height = SIZES.get(job["kind"], SIZES["charm"])
                scene.render.resolution_x, scene.render.resolution_y = width, height
                frame(camera, meshes, job["kind"], width / height)
                scene.render.filepath = job["out"]
                bpy.ops.render.render(write_still=True)
                if job["kind"] == "charm":  # which side is the front isn't in the files: the engine keeps the richer one
                    frame(camera, meshes, job["kind"], width / height, back=True)
                    scene.render.filepath = job["out"] + ".back.png"
                    bpy.ops.render.render(write_still=True)
        except Exception as error:  # one broken item shouldn't cost the others their picture
            print(f"Preview failed {job['folder']}: {error}", flush=True)
        for thing in [o for o in bpy.data.objects if o not in before]:
            bpy.data.objects.remove(thing)
        for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
            for item in [b for b in block if b.users == 0]:
                block.remove(item)
        print(f"THUMB {number}", flush=True)


main()

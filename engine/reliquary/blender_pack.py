"""Runs inside Blender: assemble an operator pack into one .blend.

blender --background --python blender_pack.py -- <add-on folder> <pack.json>
pack.json: {"name", "blend", "items": [{"kind": uniform | headgear | weapon | charm, "name", "folder",
"group" (weapons: one sub-collection per weapon), "offset" [x, y, z]}]}. Every item becomes a collection; in each
group the first stays visible and the others are hidden (eye icon in the Outliner), except charms, which all show.
The R6-parser add-on imports each glTF with the Siege materials. Paths are saved relative, so the folder can move.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

addon, spec_path = sys.argv[sys.argv.index("--") + 1:][:2]
sys.path.insert(0, addon)
# the import function only: the add-on's register() refuses anything but Blender 4.5 for its menu entry
from io_scene_r6.blender_preview import import_siege_model  # noqa: E402

spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
scene, layer = bpy.context.scene, bpy.context.view_layer
for obj in list(bpy.data.objects):  # the startup cube, camera and light
    bpy.data.objects.remove(obj, do_unlink=True)
for collection in list(bpy.data.collections):  # and its empty "Collection"
    bpy.data.collections.remove(collection)

root = bpy.data.collections.new(spec["name"])
scene.collection.children.link(root)
TITLES = {"uniform": "Uniforms", "headgear": "Headgear", "weapon": "Weapons", "charm": "Charms"}
groups = {}


def group(kind, sub=None):
    """The collection an item goes in: Operator · Uniforms, … and for weapons one more level per weapon."""
    key = (kind, sub)
    if key not in groups:
        if sub is None:
            groups[key] = bpy.data.collections.new(f"{spec['name']} · {TITLES[kind]}")
            root.children.link(groups[key])
        else:
            groups[key] = bpy.data.collections.new(sub)
            group(kind).children.link(groups[key])
    return groups[key]


def layer_of(collection, parent=None):
    parent = parent or layer.layer_collection
    for child in parent.children:
        if child.collection == collection:
            return child
        found = layer_of(collection, child)
        if found:
            return found
    return None


shown = set()
for number, item in enumerate(spec["items"], 1):
    collection = bpy.data.collections.new(item["name"])
    group(item["kind"], item.get("group")).children.link(collection)
    layer.active_layer_collection = layer_of(collection)
    before = set(bpy.data.objects)
    for gltf in sorted(Path(item["folder"]).rglob("*.gltf")):
        import_siege_model(gltf)
    # next to the operator; weapons turned side-on (they come pointing along Y, like in the hands)
    place = Matrix.Translation(Vector(item.get("offset", (0, 0, 0))))
    if item["kind"] == "weapon":
        place = place @ Matrix.Rotation(math.pi / 2, 4, "Z")
    for obj in set(bpy.data.objects) - before:
        if obj.parent is None:
            obj.matrix_world = place @ obj.matrix_world
    slot = (item["kind"], item.get("group"))
    if item["kind"] != "charm" and slot in shown:
        layer_of(collection).hide_viewport = True
        collection.hide_render = True
    shown.add(slot)
    print(f"PACK {number}/{len(spec['items'])}", flush=True)

layer.active_layer_collection = layer.layer_collection
# the glTF importer packs every texture into the .blend: keep them as the PNG files next to it instead
for image in bpy.data.images:
    if image.packed_file and image.filepath:
        image.unpack(method="REMOVE")
bpy.context.preferences.filepaths.save_version = 0  # no .blend1 backup next to a fresh pack
bpy.ops.wm.save_as_mainfile(filepath=spec["blend"], relative_remap=True)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print("Reliquary pack saved:", spec["blend"], flush=True)

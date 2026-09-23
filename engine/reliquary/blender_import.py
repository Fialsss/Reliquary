"""Runs inside Blender: import an exported operator with the R6-parser add-on's Siege materials.

blender --python blender_import.py -- <add-on folder> <operator folder>
"""
import sys
from pathlib import Path

import bpy

addon, folder = sys.argv[sys.argv.index("--") + 1:][:2]
sys.path.insert(0, addon)
# the import function only: the add-on's register() refuses anything but Blender 4.5 for its menu entry
from io_scene_r6.blender_preview import import_siege_model  # noqa: E402

for obj in list(bpy.data.objects):  # the startup cube, camera and light
    bpy.data.objects.remove(obj, do_unlink=True)
models = sorted(Path(folder).glob("*/*/*.gltf"))  # <operator>/<body|head>/<model uid>/<model uid>.gltf
for gltf in models:
    import_siege_model(gltf)
print(f"Reliquary: imported {len(models)} models from {folder}", flush=True)

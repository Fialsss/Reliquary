# PyInstaller spec for the frozen engine shipped inside the installer.
# Build with `npm run build:engine` (needs `pip install pyinstaller pillow`).
import os
from PyInstaller.utils.hooks import collect_submodules

here = SPECPATH

analysis = Analysis(
    [os.path.join(here, "reliquary_engine.py")],
    pathex=[here, os.path.join(here, "r6parser")],
    datas=[(os.path.join(here, "reliquary", "data"), "reliquary/data")],
    # ooz.dll, built from engine/native/ooz by `npm run build:ooz` (build:engine runs it first)
    binaries=[(os.path.join(here, "native", "ooz", "ooz.dll"), ".")],
    hiddenimports=collect_submodules("src"),
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="reliquary-engine", console=True)
coll = COLLECT(exe, analysis.binaries, analysis.datas, name="reliquary-engine")

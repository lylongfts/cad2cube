"""
CAD2Cube — DXF / DWG Importer for Blender
=========================================
Free & open source. Made with love by Long Live The Cube.

    YouTube : https://www.youtube.com/@longlivethecube
    Support : https://ko-fi.com/longlivethecube

Import DXF and DWG files into Blender with proper unit handling,
layer-to-collection mapping, and block instancing.

Supported formats:
    - DXF (native via ezdxf)
    - DWG (via Open Design Alliance File Converter bridge)

License: GPL-3.0-or-later
"""

# bl_info is kept for legacy-addon installs (Blender 4.2-5.x "Install from Disk").
# The blender_manifest.toml takes over when installed as an Extension.
bl_info = {
    "name": "CAD2Cube — DXF / DWG Importer",
    "author": "Long Live The Cube",
    "version": (1, 2, 0),
    "blender": (4, 2, 0),
    "location": "File > Import > CAD2Cube (.dxf, .dwg)",
    "description": "Import DXF and DWG with layers, units, and block support. Free forever.",
    "category": "Import-Export",
    "doc_url": "https://github.com/lylongfts/CAD2CUBE",
    "tracker_url": "https://github.com/lylongfts/CAD2CUBE/issues",
}

# --- Vendor path setup (legacy "Install from Disk" fallback only) -----------
# When installed as a proper Extension (blender_manifest.toml + wheels/),
# Blender automatically puts wheels on sys.path — no manual setup needed.
# This block only activates for legacy installs that have a vendor/ folder.
import os
import sys

_vendor_dir = os.path.join(os.path.dirname(__file__), "vendor")
if os.path.isdir(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)

# --- Module imports ---------------------------------------------------------
import bpy
from bpy.types import TOPBAR_MT_file_import

from . import preferences
from . import operators


# --- Menu integration -------------------------------------------------------
def _menu_func_import_dxf(self, context):
    self.layout.operator(
        operators.IMPORT_OT_dxf.bl_idname,
        text="CAD2Cube — DXF (.dxf)",
        icon="MESH_GRID",
    )


def _menu_func_import_dwg(self, context):
    self.layout.operator(
        operators.IMPORT_OT_dwg.bl_idname,
        text="CAD2Cube — DWG (.dwg)",
        icon="MESH_GRID",
    )


# --- Registration -----------------------------------------------------------
_classes = (
    preferences.CAD2CubePreferences,
    operators.CAD2CUBE_OT_open_url,
    operators.IMPORT_OT_dxf,
    operators.IMPORT_OT_dwg,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    TOPBAR_MT_file_import.append(_menu_func_import_dxf)
    TOPBAR_MT_file_import.append(_menu_func_import_dwg)


def unregister():
    TOPBAR_MT_file_import.remove(_menu_func_import_dwg)
    TOPBAR_MT_file_import.remove(_menu_func_import_dxf)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

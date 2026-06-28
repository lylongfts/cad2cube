"""
Import operators for CAD2Cube.

    CAD2CUBE_OT_open_url  - opens a URL (YouTube / Coffee / GitHub / ODA)
    IMPORT_OT_dxf         - direct DXF import
    IMPORT_OT_dwg         - DWG import via ODA File Converter -> temp DXF
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import webbrowser
from pathlib import Path

import bpy
from bpy.props import (
    StringProperty,
    FloatProperty,
    BoolProperty,
    EnumProperty,
    IntProperty,
    CollectionProperty,
)
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector

from .core import reader, converters, layers
from .preferences import get_prefs, URL_ODA_DOWNLOAD, URL_COFFEE, URL_YOUTUBE


# ============================================================================
# Utility operator: open a URL in the default browser
# ============================================================================
class CAD2CUBE_OT_open_url(Operator):
    """Open a link in your web browser"""

    bl_idname = "cad2cube.open_url"
    bl_label = "Open Link"
    bl_options = {"INTERNAL"}

    url: StringProperty(default="")

    def execute(self, context):
        if self.url:
            webbrowser.open(self.url)
        return {"FINISHED"}


# ============================================================================
# Shared import options (mixin for both DXF and DWG operators)
# ============================================================================
class _CADImportOptions:
    """All the import option fields shared by DXF and DWG operators."""

    # --- Scale & Units ------------------------------------------------------
    units_mode: EnumProperty(
        name="Units",
        description="How to determine the scale factor",
        items=[
            ("AUTO", "Auto-detect", "Read $INSUNITS from DXF header"),
            ("MANUAL", "Manual scale", "Use the scale factor below"),
            ("PRESET_MM", "Millimeters", "Source is mm, target is m (x0.001)"),
            ("PRESET_CM", "Centimeters", "Source is cm, target is m (x0.01)"),
            ("PRESET_M", "Meters", "Source is m, target is m (x1.0)"),
            ("PRESET_IN", "Inches", "Source is inches (x0.0254)"),
            ("PRESET_FT", "Feet", "Source is feet (x0.3048)"),
        ],
        default="AUTO",
    )

    manual_scale: FloatProperty(
        name="Manual Scale",
        description="Multiplier applied to every coordinate. Used when Units = Manual",
        default=0.001,
        min=0.000001,
        max=100000.0,
        precision=6,
    )

    # --- Layer handling -----------------------------------------------------
    layer_mode: EnumProperty(
        name="Layers",
        description="How DXF layers map to Blender",
        items=[
            ("COLLECTIONS", "As Collections",
             "Each layer becomes a Blender collection (recommended for arch viz)"),
            ("MATERIALS", "As Materials",
             "Each layer becomes a material with the layer's color"),
            ("FLAT", "Flat / Ignore",
             "Put everything in one collection, no layer separation"),
        ],
        default="COLLECTIONS",
    )

    layer_filter: StringProperty(
        name="Layer Filter",
        description="Comma-separated layer names to import (empty = all). "
                    "Prefix a name with '!' to exclude it",
        default="",
    )

    # --- Block handling -----------------------------------------------------
    block_mode: EnumProperty(
        name="Blocks",
        description="How to handle INSERT entities (block references)",
        items=[
            ("INSTANCES", "Collection Instances",
             "Reuse geometry via instances (memory-efficient, recommended)"),
            ("EXPANDED", "Expand In Place",
             "Duplicate block geometry at each insert point (heavy)"),
            ("IGNORE", "Ignore Blocks",
             "Skip all block references entirely"),
        ],
        default="INSTANCES",
    )

    # --- Entity filters -----------------------------------------------------
    import_text: BoolProperty(
        name="Import Text",
        description="Import TEXT and MTEXT entities as Blender text objects",
        default=False,
    )

    import_points: BoolProperty(
        name="Import Points",
        description="Import POINT entities as empty axes",
        default=False,
    )

    hatch_mode: EnumProperty(
        name="Import HATCH",
        description="How to handle HATCH fill regions",
        items=[
            ("NONE", "None", "Skip all hatches"),
            ("SOLID", "Solid hatches only",
             "Import only hatches that are already solid fills (recommended)"),
            ("ALL_AS_SOLID", "All hatches as solid",
             "Import every hatch as a solid fill, including pattern hatches "
             "(pattern lines are dropped, only the filled boundary is kept)"),
        ],
        default="SOLID",
    )

    color_by_layer: BoolProperty(
        name="Color by Layer",
        description="Tint objects with their CAD layer color in the viewport "
                    "(object color only — no materials, does not affect render). "
                    "Makes the import look like the original CAD drawing",
        default=True,
    )

    skip_hidden_layers: BoolProperty(
        name="Skip Hidden / Frozen Layers",
        description="Skip layers that are off, frozen, or locked in the source file",
        default=True,
    )

    # --- Geometry options ---------------------------------------------------
    curve_resolution: IntProperty(
        name="Curve Resolution",
        description="Segments per full revolution for arcs, ellipses, splines",
        default=64,
        min=8,
        max=512,
    )

    flatten_z: BoolProperty(
        name="Flatten to XY Plane",
        description="Force Z = 0 on every entity (useful for 2D drawings with Z noise)",
        default=False,
    )

    # --- Scene -------------------------------------------------------------
    recenter_mode: EnumProperty(
        name="Recenter",
        description="How to position imported geometry relative to Blender's origin",
        items=[
            ("NONE", "No Recenter",
             "Keep original CAD coordinates — CAD (0,0,0) maps to Blender (0,0,0). "
             "Use when multiple files share the same coordinate system"),
            ("BBOX", "Bbox Center to Origin",
             "Move geometry so its bounding box center sits at world origin. "
             "Best for files with geographic/project coordinates far from zero"),
            ("MIN_CORNER", "Min Corner to Origin",
             "Move geometry so its bottom-left bounding box corner sits at origin. "
             "Useful when you want the building corner at (0,0,0)"),
        ],
        default="BBOX",
    )

    join_by_layer: BoolProperty(
        name="Join By Layer",
        description="Merge all curves on the same layer into a single object (faster scene)",
        default=False,
    )

    frame_after_import: BoolProperty(
        name="Frame View After Import",
        description="Zoom the viewport to the imported geometry and fix clipping distance",
        default=True,
    )


# ============================================================================
# DXF Import Operator
# ============================================================================
class IMPORT_OT_dxf(Operator, ImportHelper, _CADImportOptions):
    """Import an AutoCAD DXF file with CAD2Cube"""

    bl_idname = "import_scene.cad2cube_dxf"
    bl_label = "Import DXF (CAD2Cube)"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    filename_ext = ".dxf"
    filter_glob: StringProperty(default="*.dxf", options={"HIDDEN"})

    files: CollectionProperty(type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype="DIR_PATH")

    def invoke(self, context, event):
        prefs = get_prefs(context)
        if prefs.default_auto_units:
            self.units_mode = "AUTO"
        else:
            self.units_mode = "MANUAL"
            self.manual_scale = prefs.default_scale
        self.recenter_mode = "BBOX" if prefs.default_recenter else "NONE"
        return super().invoke(context, event)

    def draw(self, context):
        _draw_import_panel(self.layout, self)

    def execute(self, context):
        paths = _collect_paths(self)
        if not paths:
            self.report({"ERROR"}, "No file selected")
            return {"CANCELLED"}

        total_objects = 0
        all_created = []
        t0 = time.perf_counter()

        for path in paths:
            try:
                count, created = _do_import_dxf(context, path, self)
                total_objects += count
                all_created.extend(created)
            except Exception as e:
                self.report({"ERROR"}, f"{Path(path).name}: {e}")
                return {"CANCELLED"}

        elapsed = time.perf_counter() - t0

        # Recenter AFTER all files imported — full scene bbox, not per-file
        if self.recenter_mode != "NONE" and all_created:
            _recenter(all_created, self.recenter_mode)
        if self.frame_after_import and all_created:
            _frame_view_on(context, all_created)
        if self.color_by_layer and all_created:
            _enable_object_color_shading(context)

        self.report(
            {"INFO"},
            f"CAD2Cube: imported {total_objects} objects from {len(paths)} file(s) "
            f"in {elapsed:.1f}s  -  enjoying it? Support at ko-fi.com/longlivethecube",
        )
        return {"FINISHED"}


# ============================================================================
# DWG Import Operator
# ============================================================================
class IMPORT_OT_dwg(Operator, ImportHelper, _CADImportOptions):
    """Import an AutoCAD DWG file with CAD2Cube (requires ODA File Converter)"""

    bl_idname = "import_scene.cad2cube_dwg"
    bl_label = "Import DWG (CAD2Cube)"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    filename_ext = ".dwg"
    filter_glob: StringProperty(default="*.dwg", options={"HIDDEN"})

    files: CollectionProperty(type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype="DIR_PATH")

    dwg_output_version: EnumProperty(
        name="Convert As",
        description="Target DXF version for ODA conversion. Newer = more features preserved",
        items=[
            ("ACAD2018", "AutoCAD 2018", ""),
            ("ACAD2013", "AutoCAD 2013", ""),
            ("ACAD2010", "AutoCAD 2010", ""),
            ("ACAD2007", "AutoCAD 2007", ""),
            ("ACAD2004", "AutoCAD 2004", ""),
            ("ACAD2000", "AutoCAD 2000", ""),
        ],
        default="ACAD2018",
    )

    def invoke(self, context, event):
        prefs = get_prefs(context)
        if not prefs.oda_converter_path or not os.path.isfile(prefs.oda_converter_path):
            # Friendly dialog with a download button instead of a dead-end error
            return context.window_manager.invoke_props_dialog(self, width=420)

        if prefs.default_auto_units:
            self.units_mode = "AUTO"
        else:
            self.units_mode = "MANUAL"
            self.manual_scale = prefs.default_scale
        self.recenter_mode = "BBOX" if prefs.default_recenter else "NONE"
        return super().invoke(context, event)

    def draw(self, context):
        prefs = get_prefs(context)
        oda_ok = bool(prefs.oda_converter_path) and os.path.isfile(prefs.oda_converter_path)

        layout = self.layout
        if not oda_ok:
            # This branch shows in the invoke_props_dialog when ODA is missing
            box = layout.box()
            box.label(text="DWG import needs ODA File Converter", icon="ERROR")
            col = box.column(align=True)
            col.scale_y = 0.9
            col.label(text="DWG is a closed Autodesk format. CAD2Cube uses the free")
            col.label(text="ODA File Converter to turn it into DXF first.")
            col.separator()
            op = box.operator(
                "cad2cube.open_url",
                text="1. Download ODA File Converter (free)",
                icon="IMPORT",
            )
            op.url = URL_ODA_DOWNLOAD
            box.label(text="2. Install it, then set its path in:")
            box.label(text="   Edit > Preferences > Add-ons > CAD2Cube")
            box.label(text="3. Re-open this DWG. (Tip: restart Blender to auto-detect.)")
            return

        box = layout.box()
        box.label(text="DWG Conversion", icon="FILE_REFRESH")
        box.prop(self, "dwg_output_version")
        _draw_import_panel(layout, self)

    def execute(self, context):
        prefs = get_prefs(context)
        oda_ok = bool(prefs.oda_converter_path) and os.path.isfile(prefs.oda_converter_path)
        if not oda_ok:
            # User confirmed the info dialog; don't try to import.
            self.report(
                {"WARNING"},
                "CAD2Cube: set the ODA File Converter path in Preferences, then retry.",
            )
            return {"CANCELLED"}

        paths = _collect_paths(self)
        if not paths:
            self.report({"ERROR"}, "No file selected")
            return {"CANCELLED"}

        total_objects = 0
        all_created = []
        t0 = time.perf_counter()

        for dwg_path in paths:
            try:
                dxf_path = _convert_dwg_to_dxf(
                    dwg_path, prefs.oda_converter_path, self.dwg_output_version,
                )
                count, created = _do_import_dxf(context, dxf_path, self)
                total_objects += count
                all_created.extend(created)

                if not prefs.keep_temp_dxf:
                    try:
                        os.remove(dxf_path)
                        os.rmdir(os.path.dirname(dxf_path))
                    except OSError:
                        pass
            except Exception as e:
                self.report({"ERROR"}, f"{Path(dwg_path).name}: {e}")
                return {"CANCELLED"}

        elapsed = time.perf_counter() - t0

        # Recenter AFTER all files imported — full scene bbox, not per-file
        if self.recenter_mode != "NONE" and all_created:
            _recenter(all_created, self.recenter_mode)
        if self.frame_after_import and all_created:
            _frame_view_on(context, all_created)
        if self.color_by_layer and all_created:
            _enable_object_color_shading(context)

        self.report(
            {"INFO"},
            f"CAD2Cube: imported {total_objects} objects from {len(paths)} DWG file(s) "
            f"in {elapsed:.1f}s  -  support at ko-fi.com/longlivethecube",
        )
        return {"FINISHED"}


# ============================================================================
# Shared draw function for the import options panel
# ============================================================================
def _draw_import_panel(layout, op):
    box = layout.box()
    box.label(text="Scale & Units", icon="EMPTY_ARROWS")
    box.prop(op, "units_mode")
    row = box.row()
    row.enabled = op.units_mode == "MANUAL"
    row.prop(op, "manual_scale")

    box = layout.box()
    box.label(text="Layers", icon="OUTLINER")
    box.prop(op, "layer_mode")
    box.prop(op, "layer_filter")
    box.prop(op, "color_by_layer")
    box.prop(op, "skip_hidden_layers")

    box = layout.box()
    box.label(text="Blocks", icon="GROUP")
    box.prop(op, "block_mode")

    box = layout.box()
    box.label(text="Entities", icon="MESH_DATA")
    row = box.row(align=True)
    row.prop(op, "import_text", toggle=True)
    row.prop(op, "import_points", toggle=True)
    box.prop(op, "hatch_mode")
    box.prop(op, "curve_resolution")
    box.prop(op, "flatten_z")

    box = layout.box()
    box.label(text="Scene", icon="SCENE_DATA")
    box.prop(op, "recenter_mode")
    box.prop(op, "join_by_layer")
    box.prop(op, "frame_after_import")


# ============================================================================
# Helpers
# ============================================================================
def _collect_paths(op) -> list[str]:
    if op.files:
        return [os.path.join(op.directory, f.name) for f in op.files if f.name]
    return [op.filepath] if op.filepath else []


def _resolve_scale(op, doc: reader.DXFDocument) -> float:
    mode = op.units_mode
    if mode == "AUTO":
        return doc.auto_scale(fallback=op.manual_scale)
    if mode == "MANUAL":
        return op.manual_scale
    return {
        "PRESET_MM": 0.001,
        "PRESET_CM": 0.01,
        "PRESET_M": 1.0,
        "PRESET_IN": 0.0254,
        "PRESET_FT": 0.3048,
    }[mode]


def _parse_layer_filter(raw: str) -> tuple[set[str], set[str]]:
    include, exclude = set(), set()
    for token in (raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        if token.startswith("!"):
            exclude.add(token[1:])
        else:
            include.add(token)
    return include, exclude


def _should_skip_layer(layer_name, include, exclude, layer_obj, skip_hidden) -> bool:
    if exclude and layer_name in exclude:
        return True
    if include and layer_name not in include:
        return True
    if skip_hidden and layer_obj is not None:
        if layer_obj.is_off() or layer_obj.is_frozen() or layer_obj.is_locked():
            return True
    return False


# ============================================================================
# Viewport: switch solid shading to Object color (so obj.color is visible)
# ============================================================================
def _enable_object_color_shading(context):
    """
    Set every 3D viewport's solid-mode color to 'OBJECT' so the per-object
    colors set by Color-by-Layer actually show.

    Two properties are needed:
      - color_type           → tints meshes/surfaces (3DFACE, SOLID, beveled curves)
      - wireframe_color_type → tints curve wireframes (LINE, ARC, POLYLINE...)
    Most CAD imports are curves, so wireframe_color_type is the important one.
    Only touches solid shading; material/rendered modes are untouched.
    """
    for area in context.screen.areas:
        if area.type != "VIEW_3D":
            continue
        for space in area.spaces:
            if space.type != "VIEW_3D":
                continue
            try:
                space.shading.color_type = "OBJECT"
            except (AttributeError, TypeError):
                pass
            try:
                space.shading.wireframe_color_type = "OBJECT"
            except (AttributeError, TypeError):
                pass


# ============================================================================
# Viewport framing (the v1.1 fix)
# ============================================================================
def _frame_view_on(context, objects):
    """Fix clip distance for far-from-origin geometry and frame the view on it."""
    if not objects:
        return

    # Blender lazily updates bound_box after objects move; force it now or the
    # bbox below reads stale (origin-centered) corners.
    context.view_layer.update()

    # Compute world-space bbox of the imported objects
    min_co = Vector((float("inf"),) * 3)
    max_co = Vector((float("-inf"),) * 3)
    for obj in objects:
        # Empties (block instances) have no bound_box geometry; use location
        if obj.type == "EMPTY":
            loc = obj.matrix_world.translation
            for i in range(3):
                min_co[i] = min(min_co[i], loc[i])
                max_co[i] = max(max_co[i], loc[i])
            continue
        for v in obj.bound_box:
            wv = obj.matrix_world @ Vector(v)
            for i in range(3):
                min_co[i] = min(min_co[i], wv[i])
                max_co[i] = max(max_co[i], wv[i])

    if min_co.x == float("inf"):
        return

    center = (min_co + max_co) * 0.5
    diag = (max_co - min_co).length
    far = max(center.length, diag) * 4.0

    # Update every 3D viewport: bump clip_end so distant geometry isn't culled,
    # then frame the selection.
    for area in context.screen.areas:
        if area.type != "VIEW_3D":
            continue
        space = area.spaces.active
        # Only raise clip_end (never lower a user's higher value)
        if far > space.clip_end:
            space.clip_end = max(far, 10000.0)
        if space.clip_start > 0.1:
            space.clip_start = 0.1

    # Select imported objects and frame them
    try:
        bpy.ops.object.select_all(action="DESELECT")
    except RuntimeError:
        pass
    active_set = False
    for obj in objects:
        try:
            obj.select_set(True)
            if not active_set:
                context.view_layer.objects.active = obj
                active_set = True
        except RuntimeError:
            pass

    for area in context.screen.areas:
        if area.type != "VIEW_3D":
            continue
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        if region is None:
            continue
        try:
            with context.temp_override(area=area, region=region):
                bpy.ops.view3d.view_selected()
        except RuntimeError:
            pass


# ============================================================================
# Main import pipeline
# ============================================================================
def _do_import_dxf(context, filepath: str, op):
    """Run the DXF import pipeline. Returns (object_count, created_objects_list)."""
    doc = reader.DXFDocument.open(filepath)
    info = doc.info()
    print(
        f"[CAD2Cube] {os.path.basename(filepath)}: "
        f"DXF {info.dxf_version}, {info.entity_count} entities, "
        f"{info.layer_count} layers, {info.block_count} blocks"
    )

    scale = _resolve_scale(op, doc)
    print(f"[CAD2Cube] Effective scale: {scale}")

    root_name = Path(filepath).stem
    root = bpy.data.collections.new(root_name)
    context.scene.collection.children.link(root)

    layer_mgr = layers.LayerManager(op.layer_mode, root, color_by_layer=op.color_by_layer)
    include, exclude = _parse_layer_filter(op.layer_filter)

    dxf_layers = {name: rgb for name, rgb in doc.iter_layers()}
    for name, rgb in dxf_layers.items():
        layer_obj = doc._doc.layers.get(name)
        if _should_skip_layer(name, include, exclude, layer_obj, op.skip_hidden_layers):
            continue
        layer_mgr.prepare(name, rgb)

    block_collections = {}
    if op.block_mode == "INSTANCES":
        blocks_root = bpy.data.collections.new(f"{root_name}_Blocks")
        root.children.link(blocks_root)
        blocks_root.hide_viewport = True
        blocks_root.hide_render = True

        for block_def in doc.iter_block_definitions():
            block_coll = _build_block_collection(block_def, blocks_root, scale, op)
            if block_coll:
                block_collections[block_def.name] = block_coll

    created = []
    per_layer_objs = {}

    for entity in doc.iter_modelspace():
        layer_name = entity.dxf.layer
        layer_obj = doc._doc.layers.get(layer_name)
        if _should_skip_layer(layer_name, include, exclude, layer_obj, op.skip_hidden_layers):
            continue

        rgb = dxf_layers.get(layer_name, (0.8, 0.8, 0.8))

        if entity.dxftype() == "INSERT":
            if op.block_mode == "IGNORE":
                continue
            if op.block_mode == "INSTANCES":
                block_coll = block_collections.get(entity.dxf.name)
                if not block_coll:
                    continue
                obj = converters.make_block_instance(entity, block_coll, scale, op.flatten_z)
            else:  # EXPANDED
                block_def = doc.get_block(entity.dxf.name)
                if not block_def:
                    continue
                _expand_block_in_place(
                    block_def, entity, scale, op, layer_mgr, dxf_layers, created,
                )
                continue
        else:
            if entity.dxftype() == "POINT" and not op.import_points:
                continue
            obj = converters.convert_entity(
                entity, scale,
                curve_resolution=op.curve_resolution,
                import_text=op.import_text,
                flatten_z=op.flatten_z,
                hatch_mode=op.hatch_mode,
            )

        if obj is None:
            continue

        layer_mgr.link_object(obj, layer_name, rgb)
        created.append(obj)
        per_layer_objs.setdefault(layer_name, []).append(obj)

    if op.join_by_layer and op.layer_mode == "COLLECTIONS":
        created = _join_objects_per_layer(context, per_layer_objs)

    return len(created), created


def _build_block_collection(block_def, parent_collection, scale, op):
    from .core.reader import _aci_to_rgb  # imported once per block, not per entity

    coll = bpy.data.collections.new(f"BLOCK_{block_def.name}")
    parent_collection.children.link(coll)

    count = 0
    for entity in block_def:
        if entity.dxftype() == "INSERT":
            # Nested block: bake its geometry into this collection, transformed
            # to the nested insert's position. Common in dynamic blocks.
            count += _bake_nested_insert(entity, block_def, coll, scale, op, _doc=block_def.doc)
            continue
        obj = converters.convert_entity(
            entity, scale,
            curve_resolution=op.curve_resolution,
            import_text=op.import_text,
            flatten_z=op.flatten_z,
            hatch_mode=op.hatch_mode,
        )
        if obj is None:
            continue
        coll.objects.link(obj)
        # Tint block geometry by its own entity color (ACI), if enabled.
        # Block entities are often BYLAYER/BYBLOCK; fall back to a neutral tint.
        if op.color_by_layer:
            try:
                aci = getattr(entity.dxf, "color", 256)  # 256 = BYLAYER
                if aci in (0, 256, None):  # BYBLOCK / BYLAYER / unset
                    obj.color = (0.8, 0.8, 0.8, 1.0)
                else:
                    r, g, b = _aci_to_rgb(aci)
                    obj.color = (r, g, b, 1.0)
            except (AttributeError, TypeError, ValueError):
                pass
        count += 1

    if count == 0:
        bpy.data.collections.remove(coll)
        return None
    return coll


def _bake_nested_insert(insert_entity, parent_block, target_coll, scale, op, _doc, _depth=0):
    """
    Bake a nested INSERT's geometry directly into target_coll, transformed
    to the nested insert's local position/rotation/scale. Recurses up to a
    safe depth to handle blocks nested inside blocks (dynamic blocks do this).
    Returns the number of objects added.
    """
    import math
    from mathutils import Matrix, Vector as V

    if _depth > 5:  # guard against pathological/circular nesting
        return 0

    nested_name = insert_entity.dxf.name
    try:
        nested_block = _doc.blocks.get(nested_name)
    except Exception:
        return 0
    if nested_block is None:
        return 0

    # Build the nested insert's transform (in block-local space, no scaling of
    # coordinates here — convert_entity already applies `scale` to points)
    ins = insert_entity.dxf.insert
    loc = V((ins[0] * scale, ins[1] * scale,
             (0.0 if op.flatten_z else (ins[2] * scale if len(ins) > 2 else 0.0))))
    rot_z = math.radians(getattr(insert_entity.dxf, "rotation", 0.0))
    sx = getattr(insert_entity.dxf, "xscale", 1.0) or 1.0
    sy = getattr(insert_entity.dxf, "yscale", 1.0) or 1.0
    sz = getattr(insert_entity.dxf, "zscale", 1.0) or 1.0
    xform = (Matrix.Translation(loc)
             @ Matrix.Rotation(rot_z, 4, "Z")
             @ Matrix.Diagonal((sx, sy, sz, 1.0)))

    added = 0
    for entity in nested_block:
        if entity.dxftype() == "INSERT":
            added += _bake_nested_insert(entity, nested_block, target_coll,
                                         scale, op, _doc, _depth + 1)
            continue
        obj = converters.convert_entity(
            entity, scale,
            curve_resolution=op.curve_resolution,
            import_text=op.import_text,
            flatten_z=op.flatten_z,
            hatch_mode=op.hatch_mode,
        )
        if obj is None:
            continue
        # Apply the nested transform to the object's geometry
        obj.matrix_world = xform @ obj.matrix_world
        target_coll.objects.link(obj)
        if op.color_by_layer:
            try:
                aci = getattr(entity.dxf, "color", 256)
                if aci in (0, 256, None):
                    obj.color = (0.8, 0.8, 0.8, 1.0)
                else:
                    r, g, b = _aci_to_rgb(aci)
                    obj.color = (r, g, b, 1.0)
            except (AttributeError, TypeError, ValueError):
                pass
        added += 1

    return added


def _expand_block_in_place(block_def, insert_entity, scale, op, layer_mgr, dxf_layers, created):
    import math
    from mathutils import Matrix

    ins = insert_entity.dxf.insert
    loc = Vector((
        ins[0] * scale,
        ins[1] * scale,
        (0.0 if op.flatten_z else (ins[2] * scale if len(ins) > 2 else 0.0)),
    ))
    rot_z = math.radians(getattr(insert_entity.dxf, "rotation", 0.0))
    sx = getattr(insert_entity.dxf, "xscale", 1.0)
    sy = getattr(insert_entity.dxf, "yscale", 1.0)
    sz = getattr(insert_entity.dxf, "zscale", 1.0)
    xform = (
        Matrix.Translation(loc)
        @ Matrix.Rotation(rot_z, 4, "Z")
        @ Matrix.Diagonal((sx, sy, sz, 1.0))
    )

    for entity in block_def:
        if entity.dxftype() == "INSERT":
            continue
        obj = converters.convert_entity(
            entity, scale,
            curve_resolution=op.curve_resolution,
            import_text=op.import_text,
            flatten_z=op.flatten_z,
            hatch_mode=op.hatch_mode,
        )
        if obj is None:
            continue
        obj.matrix_world = xform @ obj.matrix_world
        layer_name = insert_entity.dxf.layer
        rgb = dxf_layers.get(layer_name, (0.8, 0.8, 0.8))
        layer_mgr.link_object(obj, layer_name, rgb)
        created.append(obj)


def _join_objects_per_layer(context, per_layer_objs):
    result = []
    for layer_name, objs in per_layer_objs.items():
        curves = [o for o in objs if o.type == "CURVE"]
        meshes = [o for o in objs if o.type == "MESH"]
        for group in (curves, meshes):
            if len(group) < 2:
                result.extend(group)
                continue
            ctx_override = {
                "active_object": group[0],
                "selected_editable_objects": group,
                "selected_objects": group,
            }
            with context.temp_override(**ctx_override):
                try:
                    bpy.ops.object.join()
                    group[0].name = f"{layer_name}_joined"
                    result.append(group[0])
                except RuntimeError as e:
                    print(f"[CAD2Cube] Join failed on {layer_name}: {e}")
                    result.extend(group)
    return result


def _recenter(objects, mode: str = "BBOX", scale: float = 1.0):
    """
    Reposition imported geometry by transforming the underlying mesh/curve
    data — NOT by shifting object.location. The latter would leave each
    object's transform showing a giant offset even though visually centered.

    Modes:
        NONE       — do nothing
        BBOX       — shift bounding box center to world origin
        MIN_CORNER — shift bounding box min corner to world origin

    Block instances (EMPTY with instance_collection) are repositioned by
    shifting their .location, since their geometry lives in a shared
    collection that should be transformed exactly once.
    """
    if mode == "NONE":
        return

    bpy.context.view_layer.update()

    # Compute world-space bounding box across all objects.
    # For EMPTY instances, use their location.
    # For meshes/curves, use bound_box transformed by matrix_world.
    min_co = Vector((float("inf"),) * 3)
    max_co = Vector((float("-inf"),) * 3)
    for obj in objects:
        if obj.type == "EMPTY":
            loc = obj.matrix_world.translation
            for i in range(3):
                min_co[i] = min(min_co[i], loc[i])
                max_co[i] = max(max_co[i], loc[i])
            continue
        for v in obj.bound_box:
            wv = obj.matrix_world @ Vector(v)
            for i in range(3):
                min_co[i] = min(min_co[i], wv[i])
                max_co[i] = max(max_co[i], wv[i])

    if min_co.x == float("inf"):
        return

    if mode == "BBOX":
        offset = (min_co + max_co) * 0.5
    elif mode == "MIN_CORNER":
        offset = min_co
    else:
        return

    # Build translation matrix to undo the offset
    from mathutils import Matrix
    translate = Matrix.Translation(-offset)

    # Track block collections we've already transformed (instances share them)
    transformed_block_collections = set()

    # Track data blocks we've already transformed (multiple objects can share
    # the same mesh/curve, especially after Join By Layer)
    transformed_data = set()

    for obj in objects:
        if obj.type == "EMPTY" and obj.instance_collection is not None:
            # Block instance: shift its location.
            # Its instance_collection geometry will be shifted ONCE below.
            obj.location -= offset
            transformed_block_collections.add(obj.instance_collection)
        elif obj.type == "EMPTY":
            # Plain empty (e.g. POINT): shift location, no data to transform
            obj.location -= offset
        elif obj.type == "FONT":
            # Text objects position via obj.location (data sits at local origin),
            # so shift the location like empties — NOT the data.
            obj.location -= offset
        elif obj.data is not None and obj.data not in transformed_data:
            # Mesh/Curve: geometry lives in the data, transform it so
            # obj.location stays clean at the origin.
            obj.data.transform(translate)
            transformed_data.add(obj.data)
        # Else: shared data already transformed by an earlier sibling

    # Now translate the block-definition geometry as well, so block instances
    # render at the right spot. Each block collection is processed once.
    for block_coll in transformed_block_collections:
        for obj in block_coll.all_objects:
            if obj.data is not None and obj.data not in transformed_data:
                # Block geometry is positioned at CAD coords relative to block
                # origin. We DON'T transform block data — instances handle
                # the world placement via their own .location now.
                pass


# ============================================================================
# DWG -> DXF bridge
# ============================================================================
def _convert_dwg_to_dxf(dwg_path: str, oda_exe: str, version: str) -> str:
    import shutil

    src_name = os.path.basename(dwg_path)
    stage_in = tempfile.mkdtemp(prefix="cad2cube_in_")
    stage_out = tempfile.mkdtemp(prefix="cad2cube_out_")

    staged_dwg = os.path.join(stage_in, src_name)
    shutil.copy2(dwg_path, staged_dwg)

    cmd = [oda_exe, stage_in, stage_out, version, "DXF", "0", "1", src_name]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        shutil.rmtree(stage_in, ignore_errors=True)
        raise RuntimeError("ODA conversion timed out after 5 minutes")
    except FileNotFoundError:
        shutil.rmtree(stage_in, ignore_errors=True)
        raise RuntimeError(f"Cannot execute ODA File Converter at: {oda_exe}")
    finally:
        shutil.rmtree(stage_in, ignore_errors=True)

    out_dxf = os.path.join(stage_out, Path(src_name).stem + ".dxf")
    if not os.path.isfile(out_dxf):
        shutil.rmtree(stage_out, ignore_errors=True)
        raise RuntimeError(
            "ODA did not produce a DXF. Check that the DWG file is valid.\n"
            f"stdout: {result.stdout[:300]}\nstderr: {result.stderr[:300]}"
        )

    return out_dxf

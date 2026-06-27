"""
Layer manager: maps DXF layers to Blender collections (or materials, or flat).
Optionally tints objects by layer color (viewport only, no material).
"""

from __future__ import annotations

from typing import Dict

import bpy


# Mode constants (kept as strings to match operator EnumProperty values)
MODE_COLLECTIONS = "COLLECTIONS"
MODE_MATERIALS = "MATERIALS"
MODE_FLAT = "FLAT"

# Blender collection color tags cycle through 8 presets (COLOR_01..COLOR_08).
# We map an ACI rgb to the nearest of these for the Outliner color dot.
_COLLECTION_TAG_COLORS = [
    ("COLOR_01", (0.74, 0.30, 0.28)),  # red
    ("COLOR_02", (0.78, 0.50, 0.25)),  # orange
    ("COLOR_03", (0.79, 0.70, 0.30)),  # yellow
    ("COLOR_04", (0.40, 0.64, 0.34)),  # green
    ("COLOR_05", (0.34, 0.56, 0.66)),  # blue
    ("COLOR_06", (0.47, 0.38, 0.64)),  # purple
    ("COLOR_07", (0.74, 0.46, 0.60)),  # pink
    ("COLOR_08", (0.52, 0.52, 0.52)),  # gray
]


def _nearest_collection_tag(rgb: tuple[float, float, float]) -> str:
    """Pick the Blender collection color tag closest to an ACI rgb."""
    r, g, b = rgb
    best_tag = "NONE"
    best_dist = float("inf")
    for tag, (tr, tg, tb) in _COLLECTION_TAG_COLORS:
        dist = (r - tr) ** 2 + (g - tg) ** 2 + (b - tb) ** 2
        if dist < best_dist:
            best_dist = dist
            best_tag = tag
    return best_tag


class LayerManager:
    """Routes imported objects into the right collection / assigns materials."""

    def __init__(
        self,
        mode: str,
        root_collection: bpy.types.Collection,
        color_by_layer: bool = False,
    ):
        self.mode = mode
        self.root = root_collection
        self.color_by_layer = color_by_layer
        self._collections: Dict[str, bpy.types.Collection] = {}
        self._materials: Dict[str, bpy.types.Material] = {}

    # --- Public API ---------------------------------------------------------
    def prepare(self, layer_name: str, rgb: tuple[float, float, float]):
        """Pre-create the collection or material for a layer."""
        if self.mode == MODE_COLLECTIONS:
            coll = self._get_or_create_collection(layer_name)
            # Tint the Outliner color dot to match the layer color
            if self.color_by_layer:
                try:
                    coll.color_tag = _nearest_collection_tag(rgb)
                except (AttributeError, TypeError):
                    pass
        elif self.mode == MODE_MATERIALS:
            self._get_or_create_material(layer_name, rgb)
        # FLAT mode: no per-layer setup needed

    def link_object(self, obj: bpy.types.Object, layer_name: str, rgb):
        """Place `obj` in the correct collection and/or assign material/color."""
        if self.mode == MODE_COLLECTIONS:
            coll = self._get_or_create_collection(layer_name)
            coll.objects.link(obj)
            if self.color_by_layer:
                self._tint_object(obj, rgb)
        elif self.mode == MODE_MATERIALS:
            self.root.objects.link(obj)
            mat = self._get_or_create_material(layer_name, rgb)
            if obj.data and hasattr(obj.data, "materials"):
                obj.data.materials.append(mat)
        else:  # FLAT
            self.root.objects.link(obj)
            if self.color_by_layer:
                self._tint_object(obj, rgb)

    # --- Internals ----------------------------------------------------------
    @staticmethod
    def _tint_object(obj: bpy.types.Object, rgb: tuple[float, float, float]):
        """
        Set the object's viewport display color (obj.color).
        This affects the viewport only when shading is set to 'Object' color,
        never the render. No material is created.
        """
        try:
            obj.color = (rgb[0], rgb[1], rgb[2], 1.0)
        except (AttributeError, TypeError):
            pass

    def _get_or_create_collection(self, name: str) -> bpy.types.Collection:
        if name in self._collections:
            return self._collections[name]

        # Sanitize: Blender collection names max 63 chars, can't be empty
        clean = (name or "Layer_0")[:63]
        coll = bpy.data.collections.new(clean)
        self.root.children.link(coll)
        self._collections[name] = coll
        return coll

    def _get_or_create_material(self, name: str, rgb) -> bpy.types.Material:
        if name in self._materials:
            return self._materials[name]

        mat = bpy.data.materials.new(name=f"DXF_{name}"[:63])
        mat.use_nodes = True
        # Set viewport color + Principled BSDF base color
        mat.diffuse_color = (*rgb, 1.0)
        if mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    # Use string key — version-safe across Blender 3.x/4.x
                    if "Base Color" in node.inputs:
                        node.inputs["Base Color"].default_value = (*rgb, 1.0)
                    break
        self._materials[name] = mat
        return mat

"""
Entity converters: turn DXF entities into Blender data blocks.

Strategy:
    - Linear / curved entities  -> Blender Curve (preserves CAD accuracy,
      stays editable, faster to import than meshing every spline).
    - Filled / planar entities  -> Blender Mesh.
    - INSERT (block ref)        -> handled by operator (collection instances).

All coordinates are scaled by the operator before entities reach here, so
this module is unit-agnostic.
"""

from __future__ import annotations

import math
from typing import Optional

import bpy
from mathutils import Matrix, Vector


# --- Public converter dispatcher --------------------------------------------
def convert_entity(
    entity,
    scale: float,
    *,
    curve_resolution: int = 32,
    import_text: bool = True,
    flatten_z: bool = False,
    hatch_mode: str = "SOLID",
) -> Optional[bpy.types.Object]:
    """
    Convert a DXF entity to a Blender object. Returns None if unsupported
    or if the entity should be skipped (e.g. TEXT when import_text=False).
    The returned object is NOT yet linked to any collection.

    hatch_mode:
        "NONE"          skip all hatches
        "SOLID"         only import hatches that are already solid fills
        "ALL_AS_SOLID"  import every hatch as a solid fill (pattern lines dropped)
    """
    dxftype = entity.dxftype()

    try:
        if dxftype == "LINE":
            return _line(entity, scale, flatten_z)

        if dxftype in ("LWPOLYLINE", "POLYLINE"):
            return _polyline(entity, scale, flatten_z)

        if dxftype == "CIRCLE":
            return _circle(entity, scale, flatten_z)

        if dxftype == "ARC":
            return _arc(entity, scale, curve_resolution, flatten_z)

        if dxftype == "ELLIPSE":
            return _ellipse(entity, scale, curve_resolution, flatten_z)

        if dxftype == "SPLINE":
            return _spline(entity, scale, curve_resolution, flatten_z)

        if dxftype == "POINT":
            return _point(entity, scale, flatten_z)

        if dxftype in ("3DFACE", "SOLID"):
            return _face(entity, scale, flatten_z)

        if dxftype in ("TEXT", "MTEXT") and import_text:
            return _text(entity, scale, flatten_z)

        if dxftype == "HATCH":
            if hatch_mode == "NONE":
                return None
            return _hatch(entity, scale, curve_resolution, flatten_z,
                          force_all=(hatch_mode == "ALL_AS_SOLID"))

    except Exception as e:
        # One bad entity should not abort the entire import.
        print(f"[CAD2Cube] Skipped {dxftype}: {e}")
        return None

    return None  # Unsupported entity type


# --- Helpers ----------------------------------------------------------------
def _v(point, scale: float, flatten_z: bool) -> Vector:
    """Scale a point and optionally flatten Z to 0."""
    x = point[0] * scale
    y = point[1] * scale
    z = 0.0 if flatten_z else (point[2] * scale if len(point) > 2 else 0.0)
    return Vector((x, y, z))


def _new_curve(name: str) -> bpy.types.Curve:
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 12
    return curve


# --- Per-entity converters --------------------------------------------------
def _line(entity, scale, flatten_z) -> bpy.types.Object:
    curve = _new_curve("DXF_Line")
    spline = curve.splines.new("POLY")
    spline.points.add(1)  # POLY splines start with 1 point
    p1 = _v(entity.dxf.start, scale, flatten_z)
    p2 = _v(entity.dxf.end, scale, flatten_z)
    spline.points[0].co = (*p1, 1.0)
    spline.points[1].co = (*p2, 1.0)
    return bpy.data.objects.new("DXF_Line", curve)


def _polyline(entity, scale, flatten_z) -> bpy.types.Object:
    curve = _new_curve("DXF_Polyline")
    spline = curve.splines.new("POLY")

    # LWPOLYLINE: get_points returns (x, y, start_width, end_width, bulge)
    # POLYLINE (2D/3D): iterate vertices via .points()
    if entity.dxftype() == "LWPOLYLINE":
        pts = [(p[0], p[1], entity.dxf.elevation) for p in entity.get_points()]
    else:
        pts = [tuple(v) for v in entity.points()]

    if not pts:
        return None

    spline.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        v = _v(p, scale, flatten_z)
        spline.points[i].co = (*v, 1.0)

    if getattr(entity, "closed", False) or getattr(entity, "is_closed", False):
        spline.use_cyclic_u = True

    return bpy.data.objects.new("DXF_Polyline", curve)


def _circle(entity, scale, flatten_z) -> bpy.types.Object:
    curve = _new_curve("DXF_Circle")
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(3)  # 4 bezier points = closed circle
    spline.use_cyclic_u = True

    center = _v(entity.dxf.center, scale, flatten_z)
    r = entity.dxf.radius * scale
    # Magic constant for ~circular bezier (4/3 * tan(pi/8))
    handle = r * 0.5522847498

    offsets = [(r, 0), (0, r), (-r, 0), (0, -r)]
    h_offsets = [(0, handle), (-handle, 0), (0, -handle), (handle, 0)]

    for i, (off, ho) in enumerate(zip(offsets, h_offsets)):
        bp = spline.bezier_points[i]
        bp.co = center + Vector((off[0], off[1], 0))
        bp.handle_left = bp.co + Vector((-ho[0], -ho[1], 0))
        bp.handle_right = bp.co + Vector((ho[0], ho[1], 0))
        bp.handle_left_type = "ALIGNED"
        bp.handle_right_type = "ALIGNED"

    return bpy.data.objects.new("DXF_Circle", curve)


def _arc(entity, scale, resolution, flatten_z) -> bpy.types.Object:
    curve = _new_curve("DXF_Arc")
    spline = curve.splines.new("POLY")

    center = _v(entity.dxf.center, scale, flatten_z)
    r = entity.dxf.radius * scale
    start = math.radians(entity.dxf.start_angle)
    end = math.radians(entity.dxf.end_angle)
    if end < start:
        end += 2 * math.pi

    steps = max(2, int(resolution * (end - start) / (2 * math.pi)))
    spline.points.add(steps)  # add N -> N+1 total points
    for i in range(steps + 1):
        t = start + (end - start) * (i / steps)
        p = center + Vector((math.cos(t) * r, math.sin(t) * r, 0))
        spline.points[i].co = (*p, 1.0)

    return bpy.data.objects.new("DXF_Arc", curve)


def _ellipse(entity, scale, resolution, flatten_z) -> bpy.types.Object:
    curve = _new_curve("DXF_Ellipse")
    spline = curve.splines.new("POLY")

    center = _v(entity.dxf.center, scale, flatten_z)
    major = Vector(entity.dxf.major_axis) * scale
    ratio = entity.dxf.ratio
    minor = Vector((-major.y, major.x, 0)) * ratio

    start = entity.dxf.start_param
    end = entity.dxf.end_param
    if end < start:
        end += 2 * math.pi

    steps = max(8, int(resolution * (end - start) / (2 * math.pi)))
    spline.points.add(steps)
    for i in range(steps + 1):
        t = start + (end - start) * (i / steps)
        p = center + major * math.cos(t) + minor * math.sin(t)
        spline.points[i].co = (*p, 1.0)

    if abs(end - start - 2 * math.pi) < 1e-6:
        spline.use_cyclic_u = True

    return bpy.data.objects.new("DXF_Ellipse", curve)


def _spline(entity, scale, resolution, flatten_z) -> bpy.types.Object:
    curve = _new_curve("DXF_Spline")
    spline = curve.splines.new("NURBS")

    # Use control points; flattened or fit_points fall through if unavailable
    try:
        control_pts = list(entity.control_points)
    except AttributeError:
        control_pts = list(getattr(entity, "fit_points", []))

    if not control_pts:
        return None

    spline.points.add(len(control_pts) - 1)
    for i, p in enumerate(control_pts):
        v = _v(p, scale, flatten_z)
        spline.points[i].co = (*v, 1.0)

    spline.order_u = min(getattr(entity.dxf, "degree", 3) + 1, len(control_pts))
    spline.use_endpoint_u = True
    if getattr(entity, "closed", False):
        spline.use_cyclic_u = True

    return bpy.data.objects.new("DXF_Spline", curve)


def _point(entity, scale, flatten_z) -> bpy.types.Object:
    empty = bpy.data.objects.new("DXF_Point", None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.05
    empty.location = _v(entity.dxf.location, scale, flatten_z)
    return empty


def _face(entity, scale, flatten_z) -> bpy.types.Object:
    """3DFACE / SOLID - flat polygon, 3 or 4 verts."""
    mesh = bpy.data.meshes.new("DXF_Face")
    verts = []
    for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
        v = getattr(entity.dxf, attr, None)
        if v is not None:
            verts.append(tuple(_v(v, scale, flatten_z)))
    # SOLID stores verts in odd order: 0,1,3,2 -> rectangle
    if entity.dxftype() == "SOLID" and len(verts) == 4:
        verts = [verts[0], verts[1], verts[3], verts[2]]
    if len(verts) < 3:
        return None
    # De-dupe coincident verts (3DFACE often duplicates 3rd vert as 4th)
    if len(verts) == 4 and verts[2] == verts[3]:
        verts = verts[:3]
    faces = [list(range(len(verts)))]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return bpy.data.objects.new("DXF_Face", mesh)


def _text(entity, scale, flatten_z) -> bpy.types.Object:
    """TEXT / MTEXT as Blender text object."""
    txt_data = bpy.data.curves.new(name="DXF_Text", type="FONT")

    if entity.dxftype() == "MTEXT":
        txt_data.body = entity.plain_text() if hasattr(entity, "plain_text") else entity.text
        height = entity.dxf.char_height * scale
        loc = _v(entity.dxf.insert, scale, flatten_z)
    else:  # TEXT
        txt_data.body = entity.dxf.text
        height = entity.dxf.height * scale
        loc = _v(entity.dxf.insert, scale, flatten_z)

    txt_data.size = max(height, 0.001)

    obj = bpy.data.objects.new("DXF_Text", txt_data)
    obj.location = loc
    rotation = math.radians(getattr(entity.dxf, "rotation", 0.0))
    obj.rotation_euler.z = rotation
    return obj


# --- HATCH (solid fill) → mesh ----------------------------------------------
def _hatch(entity, scale, resolution, flatten_z, force_all=False) -> Optional[bpy.types.Object]:
    """
    Convert a HATCH to a Blender mesh.

    force_all=False : only solid-fill hatches are imported (pattern hatches skipped)
    force_all=True  : every hatch is imported as solid (pattern lines dropped,
                      only the filled boundary is kept)

    Boundary paths come in two flavors from ezdxf:
        - PolylinePath : a closed list of vertices (the common case)
        - EdgePath     : a sequence of LINE / ARC / ELLIPSE / SPLINE edges

    Each path becomes one polygon. Multiple paths in one HATCH become
    separate faces in the same mesh (islands/holes are approximated as
    additional faces — true boolean holes are out of scope for v1).
    """
    # Skip non-solid (pattern) hatches unless force_all is set.
    if not force_all:
        is_solid = getattr(entity.dxf, "solid_fill", 0) == 1
        pattern_name = getattr(entity.dxf, "pattern_name", "")
        if not is_solid and pattern_name.upper() != "SOLID":
            return None

    # HATCH elevation in ezdxf is a Vec3 point, not a scalar.
    # The z-height is its .z component.
    z = 0.0
    if not flatten_z:
        elev = getattr(entity.dxf, "elevation", None)
        if elev is not None:
            elev_z = getattr(elev, "z", None)
            if elev_z is None:
                # Fallback: maybe it's a tuple/sequence
                try:
                    elev_z = elev[2]
                except (TypeError, IndexError, KeyError):
                    elev_z = 0.0
            z = float(elev_z) * scale

    all_verts = []
    all_faces = []

    for path in entity.paths:
        loop = _hatch_path_to_points(path, scale, resolution)
        if loop is None or len(loop) < 3:
            continue

        # De-duplicate a trailing point that equals the first (closed loop)
        if len(loop) > 1 and (loop[0] - loop[-1]).length < 1e-9:
            loop = loop[:-1]
        if len(loop) < 3:
            continue

        base = len(all_verts)
        for p in loop:
            all_verts.append((p.x, p.y, z))
        all_faces.append(list(range(base, base + len(loop))))

    if not all_verts or not all_faces:
        return None

    mesh = bpy.data.meshes.new("DXF_Hatch")
    mesh.from_pydata(all_verts, [], all_faces)
    mesh.update()

    # n-gon faces from CAD boundaries are often non-planar or concave;
    # validate cleans up anything Blender can't represent.
    mesh.validate(verbose=False)

    return bpy.data.objects.new("DXF_Hatch", mesh)


def _hatch_path_to_points(path, scale, resolution):
    """
    Turn one HATCH boundary path into a list of mathutils.Vector points (2D->3D
    with z handled by caller). Returns None if the path type is unsupported.
    """
    path_type = type(path).__name__

    # PolylinePath: has .vertices = [(x, y, bulge), ...]
    if path_type == "PolylinePath":
        pts = []
        for v in path.vertices:
            x, y = _xy(v)
            pts.append(Vector((x * scale, y * scale, 0.0)))
        return pts

    # EdgePath: a list of edges (LineEdge, ArcEdge, EllipseEdge, SplineEdge)
    if path_type == "EdgePath":
        pts = []
        for edge in path.edges:
            edge_type = type(edge).__name__

            if edge_type == "LineEdge":
                x, y = _xy(edge.start)
                pts.append(Vector((x * scale, y * scale, 0.0)))
                # end point is added by the next edge's start, or final closure

            elif edge_type == "ArcEdge":
                pts.extend(_sample_arc_edge(edge, scale, resolution))

            elif edge_type == "EllipseEdge":
                pts.extend(_sample_ellipse_edge(edge, scale, resolution))

            elif edge_type == "SplineEdge":
                # Approximate spline by its control/fit points
                fit = getattr(edge, "fit_points", None) or getattr(edge, "control_points", [])
                for p in fit:
                    x, y = _xy(p)
                    pts.append(Vector((x * scale, y * scale, 0.0)))

        return pts

    return None


def _xy(point) -> tuple[float, float]:
    """
    Extract (x, y) as plain floats from any ezdxf point representation.
    ezdxf returns Vec2/Vec3 objects whose indexing can yield Vec objects,
    not floats — so prefer the .x/.y attributes when present.
    """
    if hasattr(point, "x") and hasattr(point, "y"):
        return float(point.x), float(point.y)
    return float(point[0]), float(point[1])


def _sample_arc_edge(edge, scale, resolution):
    """Sample an ArcEdge boundary into points."""
    cx, cy = _xy(edge.center)
    r = edge.radius
    start = math.radians(edge.start_angle)
    end = math.radians(edge.end_angle)
    ccw = getattr(edge, "ccw", True)

    if ccw:
        if end < start:
            end += 2 * math.pi
    else:
        if start < end:
            start += 2 * math.pi

    span = abs(end - start)
    steps = max(2, int(resolution * span / (2 * math.pi)))
    pts = []
    for i in range(steps + 1):
        a = start + (end - start) * (i / steps)
        pts.append(Vector(((cx + math.cos(a) * r) * scale,
                           (cy + math.sin(a) * r) * scale, 0.0)))
    return pts


def _sample_ellipse_edge(edge, scale, resolution):
    """Sample an EllipseEdge boundary into points."""
    cx, cy = _xy(edge.center)
    mx, my = _xy(edge.major_axis)
    major = Vector((mx, my, 0.0))
    ratio = edge.ratio
    minor = Vector((-major.y, major.x, 0.0)) * ratio

    start = edge.start_param
    end = edge.end_param
    if end < start:
        end += 2 * math.pi

    span = abs(end - start)
    steps = max(2, int(resolution * span / (2 * math.pi)))
    pts = []
    for i in range(steps + 1):
        t = start + (end - start) * (i / steps)
        p = Vector((cx, cy, 0.0)) + major * math.cos(t) + minor * math.sin(t)
        pts.append(Vector((p.x * scale, p.y * scale, 0.0)))
    return pts


# --- INSERT (block reference) → collection instance -------------------------
def make_block_instance(
    insert_entity,
    block_collection: bpy.types.Collection,
    scale: float,
    flatten_z: bool,
) -> bpy.types.Object:
    """Create an empty that instances the given block collection."""
    name = f"INS_{insert_entity.dxf.name}"
    obj = bpy.data.objects.new(name, None)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = block_collection

    loc = _v(insert_entity.dxf.insert, scale, flatten_z)
    rot_z = math.radians(getattr(insert_entity.dxf, "rotation", 0.0))
    sx = getattr(insert_entity.dxf, "xscale", 1.0)
    sy = getattr(insert_entity.dxf, "yscale", 1.0)
    sz = getattr(insert_entity.dxf, "zscale", 1.0)

    obj.location = loc
    obj.rotation_euler = (0, 0, rot_z)
    obj.scale = (sx, sy, sz)
    return obj

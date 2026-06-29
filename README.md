<div align="center">

# CAD2Cube

### Free DXF importer for Blender — hatches, layers, units, and block instances

[![Blender](https://img.shields.io/badge/Blender-4.2%20–%205.x-orange)](https://www.blender.org/)
[![License](https://img.shields.io/badge/license-GPL--3.0-blue)](LICENSE)
[![Free](https://img.shields.io/badge/price-free%20forever-brightgreen)]()

**Made by [Long Live The Cube](https://www.youtube.com/@longlivethecube) · [❤️ Support on Ko-fi](https://ko-fi.com/longlivethecube)**

</div>

---

Blender's built-in DXF importer is a legacy add-on that only understands DXF R12,
crashes on modern files, and has no hatch import, no layer mapping, and no unit detection.
**CAD2Cube fixes all of that — for free.**

## What's New in v1.5.0

- 🎨 **HATCH import overhauled** — filled regions (rooms, slabs, walls) now come in as real editable mesh faces, not just outlines. Default mode is "All as solid" so nothing gets skipped.
- 📦 **Nested block instancing** — complex drawings with hundreds of inserts no longer explode your scene into thousands of objects
- 🏔️ **Merge 3D Faces** — Civil 3D terrain TIN surfaces weld into a single clean mesh instead of 50k separate faces
> [!NOTE]
> **Important Update (v1.5.0):** To comply with the official Blender Extensions platform guidelines regarding third-party software and security, native DWG support via the ODA converter has been removed. This plugin is now a 100% standalone, ultra-safe, and lightweight DXF Importer. If you still need DWG import support, please download and use **v1.4.5** from the releases page.

## Why CAD2Cube

| | CAD2Cube | Blender built-in | Better FBX ($30) |
|---|:---:|:---:|:---:|
| DXF all versions (R12 – 2018+) | ✅ | ❌ R12 only | ⚠️ basic |
| **HATCH → editable mesh face** | ✅ | ❌ | ❌ |
| Layer → Collection | ✅ | ❌ | ❌ |
| Layer → Material (ACI colors) | ✅ | ❌ | ❌ |
| Memory-efficient block instances | ✅ | ❌ | ❌ |
| Auto unit detection (`$INSUNITS`) | ✅ | ❌ | ❌ |
| Auto-recenter geographic coords | ✅ | ❌ | ❌ |
| Recovers from corrupt files | ✅ | ❌ crash | ❌ |
| Maintained for Blender 5.x | ✅ | ❌ legacy | ✅ |

## Features

- **DXF import** — native, via the MIT-licensed `ezdxf` library (bundled, no setup)
- **HATCH → mesh face** — filled regions import as real Blender mesh faces, ready for Solidify, UV unwrap, and materials. Three modes: *None / Solid only / All as solid (default)*
- **Smart units** — reads `$INSUNITS` so a 5000 mm wall becomes a 5 m wall automatically
- **Layers as collections** — keeps the architect's organization intact
- **Block instancing** — INSERT entities become Blender collection instances. One mesh shared across N references, light on memory. Supports nested blocks and mirrored inserts
- **Color by Layer** — tint objects with their CAD layer color in the viewport (object color, not materials — looks like the original drawing)
- **Three recenter modes** — keep CAD coords, center bounding box, or snap min-corner to origin
- **Auto-recenter & auto-frame** — CAD files with geographic coordinates just work
- **Layer filtering** — `WALL, DOOR, !DIM_*` include/exclude syntax
- **Merge 3D Faces** — weld all 3DFACE entities into one mesh (useful for Civil 3D terrain files)
- **Curves stay curves** — splines, arcs, ellipses remain editable, not pre-meshed
- **Tolerant reader** — opens corrupt/non-conforming DXFs that crash other importers

## Install

1. Download `cad2cube-x.x.x.zip` from either:
   - 🟠 **Gumroad** (recommended): [lylongsoul.gumroad.com/l/esyoci](https://lylongsoul.gumroad.com/l/esyoci)
   - 🐙 **GitHub Releases**: [github.com/lylongfts/CAD2CUBE/releases](https://github.com/lylongfts/CAD2CUBE/releases)
2. Drag the zip into Blender, or: Edit → Preferences → Get Extensions → Install from Disk.
3. Done. `File → Import → CAD2Cube — DXF (.dxf)`

## Usage

`File → Import → CAD2Cube — DXF (.dxf)`

Recommended settings for architectural drawings:
- **Units:** Auto-detect
- **Layers:** As Collections
- **Blocks:** Collection Instances
- **Import HATCH:** All as solid *(default)*
- **Recenter to Origin:** ON
- **Frame View After Import:** ON

> **For Civil 3D terrain files:** turn on *Merge 3D Faces* to get one clean mesh instead of thousands of separate triangles.

## Supported entities

LINE, LWPOLYLINE, POLYLINE (2D/3D), CIRCLE, ARC, ELLIPSE, SPLINE, POINT,
3DFACE, SOLID, TEXT, MTEXT, INSERT (blocks), **HATCH (solid & patterns → mesh face)**.

Planned: DIMENSION, LEADER, 3DSOLID.

## Tutorials

Full CAD-to-Blender workflow series on YouTube:
**[youtube.com/@longlivethecube](https://www.youtube.com/@longlivethecube)**

## Support the project

CAD2Cube is free and always will be. If it saved you time:
**[❤️ ko-fi.com/longlivethecube](https://ko-fi.com/longlivethecube)**

## License

GPL-3.0-or-later (required for Blender add-ons). `ezdxf` is MIT (compatible).

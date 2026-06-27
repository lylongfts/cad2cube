<div align="center">

# CAD2Cube

### Free DXF & DWG importer for Blender — with layers, units, and block instances

[![Blender](https://img.shields.io/badge/Blender-4.2%20–%205.x-orange)](https://www.blender.org/)
[![License](https://img.shields.io/badge/license-GPL--3.0-blue)](LICENSE)
[![Free](https://img.shields.io/badge/price-free%20forever-brightgreen)]()

**Made by [Long Live The Cube](https://www.youtube.com/@longlivethecube) · [❤️ Support on Ko-fi](https://ko-fi.com/longlivethecube)**

</div>

---

Blender's built-in DXF importer is a legacy add-on that only understands DXF R12,
crashes on modern files, and has no DWG, no layer mapping, and no unit detection.
**CAD2Cube fixes all of that — for free.**

## Why CAD2Cube

| | CAD2Cube | Blender built-in | Better FBX ($30) |
|---|:---:|:---:|:---:|
| DXF all versions (R12 – 2018+) | ✅ | ❌ R12 only | ⚠️ basic |
| DWG support (via free ODA) | ✅ | ❌ | ❌ |
| Layer → Collection | ✅ | ❌ | ❌ |
| Layer → Material (ACI colors) | ✅ | ❌ | ❌ |
| Memory-efficient block instances | ✅ | ❌ | ❌ |
| Auto unit detection (`$INSUNITS`) | ✅ | ❌ | ❌ |
| Auto-recenter geographic coords | ✅ | ❌ | ❌ |
| Recovers from corrupt files | ✅ | ❌ crash | ❌ |
| Maintained for Blender 5.x | ✅ | ❌ legacy | ✅ |

## Features

- **DXF import** — native, via the MIT-licensed `ezdxf` library (bundled, no setup)
- **DWG import** — via the free Open Design Alliance File Converter
- **Smart units** — reads `$INSUNITS` so a 5000 mm wall becomes a 5 m wall automatically
- **Layers as collections** — keeps the architect's organization intact
- **Block instancing** — INSERT entities become Blender collection instances. One mesh shared across N references, light on memory
- **Auto-recenter & auto-frame** — CAD files with geographic coordinates just work
- **Layer filtering** — `WALL, DOOR, !DIM_*` include/exclude syntax
- **Curves stay curves** — splines, arcs, ellipses remain editable, not pre-meshed
- **Tolerant reader** — opens corrupt/non-conforming DXFs that crash other importers

## Install

### Blender 4.2+ (recommended)
1. Download `cad2cube-x.x.x.zip` from either:
   - 🟠 **Gumroad** (recommended): [lylongsoul.gumroad.com/l/esyoci](https://lylongsoul.gumroad.com/l/esyoci)
   - 🐙 **GitHub Releases**: [github.com/lylongfts/CAD2CUBE/releases](https://github.com/lylongfts/CAD2CUBE/releases)
2. Drag the zip into Blender, or: Edit → Preferences → Get Extensions → Install from Disk.
3. Done. DXF works immediately.

### DWG support (optional)
DWG is a closed Autodesk format, so it needs one free helper:
1. [Download ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter) (free, account required).
2. Install it.
3. In CAD2Cube preferences, the path auto-detects on next Blender start — or set it manually.

## Usage

`File → Import → CAD2Cube — DXF (.dxf)` or `— DWG (.dwg)`

Recommended settings for architectural drawings:
- **Units:** Auto-detect
- **Layers:** As Collections
- **Blocks:** Collection Instances
- **Recenter to Origin:** ON
- **Frame View After Import:** ON

## Supported entities

LINE, LWPOLYLINE, POLYLINE (2D/3D), CIRCLE, ARC, ELLIPSE, SPLINE, POINT,
3DFACE, SOLID, TEXT, MTEXT, INSERT (blocks).

Planned: HATCH, DIMENSION, LEADER, 3DSOLID, nested blocks.

## Tutorials

Full CAD-to-Blender workflow series on YouTube:
**[youtube.com/@longlivethecube](https://www.youtube.com/@longlivethecube)**

## Support the project

CAD2Cube is free and always will be. If it saved you time:
**[❤️ ko-fi.com/longlivethecube](https://ko-fi.com/longlivethecube)**

## License

GPL-3.0-or-later (required for Blender add-ons). `ezdxf` is MIT (compatible).

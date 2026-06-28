"""
Reader module: opens DXF documents, detects units, exposes a clean iterator
over modelspace entities. Hides ezdxf specifics from the rest of the addon.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional


# AutoCAD $INSUNITS code -> meters per unit
# Reference: DXF spec, group code 70 in $INSUNITS header var
_INSUNITS_TO_METERS = {
    0: None,        # Unitless - caller decides
    1: 0.0254,      # Inches
    2: 0.3048,      # Feet
    3: 1609.344,    # Miles
    4: 0.001,       # Millimeters
    5: 0.01,        # Centimeters
    6: 1.0,         # Meters
    7: 1000.0,      # Kilometers
    8: 2.54e-8,     # Microinches
    9: 2.54e-5,     # Mils
    10: 0.9144,     # Yards
    11: 1e-10,      # Angstroms
    12: 1e-9,       # Nanometers
    13: 1e-6,       # Microns
    14: 0.1,        # Decimeters
    15: 10.0,       # Dekameters
    16: 100.0,      # Hectometers
    17: 1e9,        # Gigameters
    18: 1.496e11,   # Astronomical units
    19: 9.461e15,   # Light years
    20: 3.086e16,   # Parsecs
    21: 0.9144,     # US Survey Feet (close enough)
    22: 0.0254,     # US Survey Inches
}


@dataclass
class DocumentInfo:
    """Summary of a loaded DXF document."""
    dxf_version: str
    insunits_code: int
    meters_per_unit: Optional[float]   # None if unitless
    entity_count: int
    layer_count: int
    block_count: int


class DXFDocument:
    """Thin wrapper around an ezdxf Drawing."""

    def __init__(self, ezdxf_doc):
        self._doc = ezdxf_doc
        self._msp = ezdxf_doc.modelspace()

    @classmethod
    def open(cls, filepath: str) -> "DXFDocument":
        # Local import so the addon can register even if ezdxf is missing,
        # and surface a clear error at import-time instead of register-time.
        try:
            import ezdxf
            from ezdxf import recover
        except ImportError as e:
            raise RuntimeError(
                "ezdxf is not available. Reinstall the addon — the bundled "
                "ezdxf in the vendor/ folder appears to be missing."
            ) from e

        # recover.readfile is more tolerant of corrupt/non-conforming DXF
        # files than ezdxf.readfile, which matters a lot in the wild.
        try:
            doc, auditor = recover.readfile(filepath)
        except IOError as e:
            raise RuntimeError(f"Cannot read DXF file: {e}") from e
        except ezdxf.DXFStructureError as e:
            raise RuntimeError(f"Invalid or corrupt DXF: {e}") from e

        return cls(doc)

    # --- Metadata -----------------------------------------------------------
    def info(self) -> DocumentInfo:
        insunits = int(self._doc.header.get("$INSUNITS", 0))
        return DocumentInfo(
            dxf_version=self._doc.dxfversion,
            insunits_code=insunits,
            meters_per_unit=_INSUNITS_TO_METERS.get(insunits),
            entity_count=sum(1 for _ in self._msp),
            layer_count=len(self._doc.layers),
            block_count=sum(
                1 for b in self._doc.blocks
                if not _is_layout_block(b.name)
            ),
        )

    def auto_scale(self, fallback: float = 0.001) -> float:
        """Return scene-unit multiplier (Blender uses meters)."""
        mpu = _INSUNITS_TO_METERS.get(int(self._doc.header.get("$INSUNITS", 0)))
        return mpu if mpu is not None else fallback

    # --- Layers -------------------------------------------------------------
    def iter_layers(self) -> Iterator[tuple[str, tuple[float, float, float]]]:
        """Yield (layer_name, rgb) for every layer in the document."""
        for layer in self._doc.layers:
            yield layer.dxf.name, _aci_to_rgb(layer.color)

    # --- Entities -----------------------------------------------------------
    def iter_modelspace(self) -> Iterator:
        """Iterate over modelspace entities (lines, polylines, circles, ...)."""
        yield from self._msp

    def get_block(self, name: str):
        """Return the block definition with the given name, or None."""
        try:
            return self._doc.blocks.get(name)
        except Exception:
            return None

    def iter_block_definitions(self) -> Iterator:
        """
        Yield user-defined and dynamic-block definitions.

        Skips only the model/paper space layout blocks. Anonymous blocks
        like *U10, *D24 (the baked geometry of AutoCAD dynamic blocks) are
        KEPT, because INSERT entities reference them directly.
        """
        for block in self._doc.blocks:
            if _is_layout_block(block.name):
                continue
            yield block


# --- Block name helpers -----------------------------------------------------
def _is_layout_block(name: str) -> bool:
    """
    True for the model/paper space layout blocks that must never be imported
    as geometry. Everything else — including anonymous dynamic-block defs
    like *U10, *D24, *E5 — is real geometry we want.
    """
    upper = name.upper()
    return upper.startswith("*MODEL_SPACE") or upper.startswith("*PAPER_SPACE")


# --- ACI color palette ------------------------------------------------------
# full palette is in ezdxf.colors if higher fidelity matters in v2.
_ACI_BASIC = {
    1: (1.0, 0.0, 0.0),     # red
    2: (1.0, 1.0, 0.0),     # yellow
    3: (0.0, 1.0, 0.0),     # green
    4: (0.0, 1.0, 1.0),     # cyan
    5: (0.0, 0.0, 1.0),     # blue
    6: (1.0, 0.0, 1.0),     # magenta
    7: (1.0, 1.0, 1.0),     # white/black (context-dependent)
    8: (0.5, 0.5, 0.5),     # dark gray
    9: (0.75, 0.75, 0.75),  # light gray
}


def _aci_to_rgb(aci: int) -> tuple[float, float, float]:
    """Map an AutoCAD Color Index (1-255) to a linear-ish RGB triple."""
    try:
        from ezdxf.colors import aci2rgb
        r, g, b = aci2rgb(aci)
        return (r / 255.0, g / 255.0, b / 255.0)
    except Exception:
        return _ACI_BASIC.get(aci, (0.8, 0.8, 0.8))

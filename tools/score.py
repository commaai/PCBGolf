from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sexpr as sx

VIA_WEIGHT = 50
LAYER_WEIGHT = 5000
ARC_SEGMENTS = 32


# --- geometry ---------------------------------------------------------------

class BBox:
    """Accumulating 2D bounding box. KiCad's Y points down; irrelevant here."""

    def __init__(self):
        self.xmin = self.ymin = math.inf
        self.xmax = self.ymax = -math.inf

    @property
    def empty(self) -> bool:
        return self.xmin is math.inf or self.xmin > self.xmax

    def add(self, x: float, y: float) -> "BBox":
        self.xmin, self.xmax = min(self.xmin, x), max(self.xmax, x)
        self.ymin, self.ymax = min(self.ymin, y), max(self.ymax, y)
        return self

    def add_all(self, points) -> "BBox":
        for x, y in points:
            self.add(x, y)
        return self

    def merge(self, other: "BBox") -> "BBox":
        if not other.empty:
            self.add(other.xmin, other.ymin).add(other.xmax, other.ymax)
        return self

    @property
    def w(self) -> float:
        return 0.0 if self.empty else self.xmax - self.xmin

    @property
    def h(self) -> float:
        return 0.0 if self.empty else self.ymax - self.ymin

    @property
    def area(self) -> float:
        return self.w * self.h


def transform(x: float, y: float, ox: float, oy: float, rot: float):
    """Footprint-local point -> board coordinates. Rotation is CW on screen."""
    a = math.radians(-rot)
    c, s = math.cos(a), math.sin(a)
    return ox + x * c - y * s, oy + x * s + y * c


def arc_points(start, mid, end, segments: int = ARC_SEGMENTS):
    """Tessellate a KiCad three-point arc; the three points if collinear."""
    (x1, y1), (x2, y2), (x3, y3) = start, mid, end
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return [start, mid, end]
    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1)
          + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3)
          + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1 = math.atan2(y1 - uy, x1 - ux)
    a2 = math.atan2(y2 - uy, x2 - ux)
    a3 = math.atan2(y3 - uy, x3 - ux)
    sweep = (a3 - a1) % (2 * math.pi)
    if (a2 - a1) % (2 * math.pi) > sweep:     # midpoint not on this sweep
        sweep -= 2 * math.pi
    n = max(2, int(abs(sweep) / (2 * math.pi) * segments) + 1)
    return [(ux + r * math.cos(a1 + sweep * i / n),
             uy + r * math.sin(a1 + sweep * i / n)) for i in range(n + 1)]


def layers_of(node: list) -> list[str]:
    """Layer names on a graphic or pad: (layer "X") or (layers "X" "Y")."""
    out: list[str] = []
    for key in ("layer", "layers"):
        c = sx.kid(node, key)
        if c:
            out += [str(v) for v in c[1:] if isinstance(v, str)]
    return out


def shape_points(node: list) -> list[tuple[float, float]]:
    """Outline points of one gr_*/fp_* graphic, in its own frame.

    Stroke width is ignored -- hundredths of a millimetre, and KiCad's own
    board extents ignore it too.
    """
    kind = (sx.name(node) or "").removeprefix("gr_").removeprefix("fp_")

    if kind in ("line", "rect"):
        a, b = sx.kid(node, "start"), sx.kid(node, "end")
        if not (a and b):
            return []
        x1, y1, x2, y2 = float(a[1]), float(a[2]), float(b[1]), float(b[2])
        if kind == "line":
            return [(x1, y1), (x2, y2)]
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

    if kind == "circle":
        c, e = sx.kid(node, "center"), sx.kid(node, "end")
        if not (c and e):
            return []
        cx, cy = float(c[1]), float(c[2])
        r = math.hypot(float(e[1]) - cx, float(e[2]) - cy)
        return [(cx - r, cy - r), (cx + r, cy + r)]

    if kind == "arc":
        a, m, b = sx.kid(node, "start"), sx.kid(node, "mid"), sx.kid(node, "end")
        if not (a and m and b):
            return []
        return arc_points((float(a[1]), float(a[2])), (float(m[1]), float(m[2])),
                          (float(b[1]), float(b[2])))

    if kind in ("poly", "curve"):
        return [(float(p[1]), float(p[2])) for p in sx.find(node, "xy")]

    return []


def pad_points(pad: list) -> list[tuple[float, float]]:
    """Corners of a pad's bounding rect. Round/oval/roundrect all fit in (size)."""
    at, size = sx.kid(pad, "at"), sx.kid(pad, "size")
    if not (at and size):
        return []
    px, py = float(at[1]), float(at[2])
    rot = float(at[3]) if len(at) > 3 else 0.0
    hw, hh = float(size[1]) / 2, float(size[2]) / 2
    pts = [transform(dx, dy, px, py, rot)
           for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
    prims = sx.kid(pad, "primitives")
    if prims is not None:
        for node in prims[1:]:
            if isinstance(node, list):
                pts += [transform(x, y, px, py, rot) for x, y in shape_points(node)]
    return pts


def local_layer_bbox(fp: list, suffix: str) -> BBox:
    box = BBox()
    for node in sx.walk(fp):
        if any(l.endswith(suffix) for l in layers_of(node)):
            box.add_all(shape_points(node))
    return box


def footprint_bbox(fp: list, local: bool = False) -> BBox:
    """Extent of one footprint: the largest of courtyard, pads and fab outline.

    The stock library is inconsistent -- several footprints have no courtyard
    at all, and the USB-C receptacles have one far smaller than their pads --
    so taking the largest of the three is the only safe reading.
    """
    candidates = [local_layer_bbox(fp, ".CrtYd"), local_layer_bbox(fp, ".Fab")]
    pads = BBox()
    for pad in sx.find(fp, "pad"):
        pads.add_all(pad_points(pad))
    candidates.append(pads)
    best = max(candidates, key=lambda b: b.area)
    if local:
        return best
    at = sx.kid(fp, "at")
    ox, oy = (float(at[1]), float(at[2])) if at else (0.0, 0.0)
    rot = float(at[3]) if at and len(at) > 3 else 0.0
    out = BBox()
    if not best.empty:
        for x, y in ((best.xmin, best.ymin), (best.xmax, best.ymin),
                     (best.xmax, best.ymax), (best.xmin, best.ymax)):
            out.add(*transform(x, y, ox, oy, rot))
    return out


# --- the three scored terms -------------------------------------------------

def copper_layers(pcb: list) -> list[str]:
    block = sx.kid(pcb, "layers")
    if block is None:
        return []
    return [str(row[1]) for row in block[1:]
            if isinstance(row, list) and str(row[1]).endswith(".Cu")]


def count_vias(pcb: list) -> dict[str, int]:
    """Vias by type. A plated through-hole *pad* is not a via."""
    counts = {"through": 0, "blind_buried": 0, "micro": 0}
    for via in sx.find(pcb, "via"):
        flags = {str(v) for v in via[1:] if isinstance(v, str)}
        if "micro" in flags:
            counts["micro"] += 1
        elif "blind" in flags:
            counts["blind_buried"] += 1
        else:
            counts["through"] += 1
    counts["total"] = sum(counts.values())
    return counts


def outline_bbox(pcb: list) -> BBox:
    """Everything on Edge.Cuts, board-level and inside footprints."""
    box = BBox()
    for node in sx.walk(pcb):
        if "Edge.Cuts" in layers_of(node):
            box.add_all(shape_points(node))
    for fp in sx.find(pcb, "footprint"):
        at = sx.kid(fp, "at")
        ox, oy = (float(at[1]), float(at[2])) if at else (0.0, 0.0)
        rot = float(at[3]) if at and len(at) > 3 else 0.0
        for node in sx.walk(fp):
            if "Edge.Cuts" in layers_of(node):
                for x, y in shape_points(node):
                    box.add(*transform(x, y, ox, oy, rot))
    return box


# --- component data ---------------------------------------------------------

def prop(fp: list, key: str, default: str = "") -> str:
    for p in sx.kids(fp, "property"):
        if len(p) > 2 and p[1] == key:
            return str(p[2])
    return default


def lib_id(fp: list) -> str:
    return str(fp[1]) if len(fp) > 1 else "?"


def on_back(fp: list) -> bool:
    return str(sx.val(fp, "layer", "F.Cu")).startswith("B.")


def load_heights(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    table = raw.get("heights_mm", raw)
    return {k: (None if v is None else float(v)) for k, v in table.items()}


# --- top level --------------------------------------------------------------

def score_board(pcb_path: Path, heights_path: Path) -> dict:
    pcb = sx.load(pcb_path)
    heights = load_heights(heights_path)

    layers = copper_layers(pcb)
    vias = count_vias(pcb)

    outline = outline_bbox(pcb)
    extent = BBox().merge(outline)
    no_courtyard = []
    for fp in sx.find(pcb, "footprint"):
        extent.merge(footprint_bbox(fp))
        if local_layer_bbox(fp, ".CrtYd").empty:
            no_courtyard.append(prop(fp, "Reference", "?"))

    general = sx.kid(pcb, "general")
    thickness = float(sx.val(general, "thickness", 1.6)) if general else 1.6

    top = bottom = 0.0
    top_part = bottom_part = ""
    unknown: dict[str, list[str]] = {}
    for fp in sx.find(pcb, "footprint"):
        lib, ref = lib_id(fp), prop(fp, "Reference", "?")
        h = heights.get(lib)
        if h is None:
            unknown.setdefault(lib, []).append(ref)
        elif on_back(fp):
            if h > bottom:
                bottom, bottom_part = h, f"{ref} ({lib})"
        elif h > top:
            top, top_part = h, f"{ref} ({lib})"

    z = thickness + top + bottom
    volume = extent.area * z
    return {
        "file": str(pcb_path),
        "bbox_mm": {"x": round(extent.w, 3), "y": round(extent.h, 3), "z": round(z, 3)},
        "z_mm": {"board": thickness, "top": round(top, 3), "top_part": top_part,
                 "bottom": round(bottom, 3), "bottom_part": bottom_part},
        "vias": vias,
        "copper_layers": {"count": len(layers), "names": layers},
        "terms": {"volume": round(volume, 1),
                  "vias": VIA_WEIGHT * vias["total"],
                  "layers": LAYER_WEIGHT * len(layers)},
        "score": round(volume + VIA_WEIGHT * vias["total"] + LAYER_WEIGHT * len(layers), 1),
        "warnings": {"no_outline": outline.empty,
                     "no_courtyard": no_courtyard,
                     "unknown_heights": unknown},
    }


def report(r: dict) -> str:
    b, t, z, w = r["bbox_mm"], r["terms"], r["z_mm"], r["warnings"]
    out = [
        r["file"], "",
        f"  bounding box   {b['x']:.2f} x {b['y']:.2f} x {b['z']:.2f} mm",
        f"  volume         {t['volume']:>12,.1f}",
        f"  vias           {t['vias']:>12,}   ({r['vias']['total']} x {VIA_WEIGHT})",
        f"  copper layers  {t['layers']:>12,}   ({r['copper_layers']['count']} x {LAYER_WEIGHT})",
        "  " + "-" * 29,
        f"  SCORE          {r['score']:>12,.1f}", "",
        f"  z = {z['board']}mm board + {z['top']}mm top ({z['top_part'] or 'none'})"
        f" + {z['bottom']}mm bottom ({z['bottom_part'] or 'none'})",
    ]
    if w["no_outline"]:
        out += ["", "  !! no Edge.Cuts outline -- X/Y is footprint extents only"]
    if w["unknown_heights"]:
        out += ["", f"  !! no height for {len(w['unknown_heights'])} footprint(s) -- z is a LOWER BOUND:"]
        for lib, refs in sorted(w["unknown_heights"].items()):
            shown = ", ".join(refs[:6]) + ("..." if len(refs) > 6 else "")
            out.append(f"       {lib:<42} {len(refs):>3}x  {shown}")
    if w["no_courtyard"]:
        out += ["", f"  !! {len(w['no_courtyard'])} footprint(s) have no courtyard, so KiCad's"
                    f" overlap DRC will not protect them:",
                "       " + ", ".join(w["no_courtyard"][:12])
                + ("..." if len(w["no_courtyard"]) > 12 else "")]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcb", type=Path, nargs="?", default=Path("pcbgolf.kicad_pcb"))
    ap.add_argument("--heights", type=Path, default=Path(__file__).parent / "heights.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    r = score_board(args.pcb, args.heights)
    print(json.dumps(r, indent=2) if args.json else report(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sexpr as sx
from score import BBox, local_layer_bbox, pad_points

TEMPLATE = """\t(fp_rect
\t\t(start {x1:.3f} {y1:.3f})
\t\t(end {x2:.3f} {y2:.3f})
\t\t(stroke
\t\t\t(width 0.05)
\t\t\t(type solid)
\t\t)
\t\t(fill no)
\t\t(layer "F.CrtYd")
\t\t(uuid "{uid}")
\t)
"""


def part_extent(fp: list) -> BBox:
    """The space the part actually occupies: its pads plus its fab outline."""
    box = BBox()
    for pad in sx.find(fp, "pad"):
        box.add_all(pad_points(pad))
    return box.merge(local_layer_bbox(fp, ".Fab"))


def encloses(crt: BBox, part: BBox, eps: float = 1e-6) -> bool:
    return (crt.xmin <= part.xmin + eps and crt.ymin <= part.ymin + eps
            and crt.xmax >= part.xmax - eps and crt.ymax >= part.ymax - eps)


def courtyard_rect(fp: list, margin: float) -> tuple[float, float, float, float] | None:
    """Rectangle to add: the part, grown by margin, unioned with any existing
    courtyard so an undersized one is enlarged rather than contradicted."""
    part = part_extent(fp)
    if part.empty:
        return None
    box = BBox().merge(part)
    box.add(part.xmin - margin, part.ymin - margin)
    box.add(part.xmax + margin, part.ymax + margin)
    box.merge(local_layer_bbox(fp, ".CrtYd"))
    return (box.xmin, box.ymin, box.xmax, box.ymax)


def insert_before_final_paren(text: str, block: str) -> str:
    """Splice a new top-level child in just before the footprint's closing ')'.

    Inserts ahead of that paren's own indentation, so the new block lands at
    one tab and the closing paren keeps its original position.
    """
    idx = text.rstrip().rfind(")")
    if idx < 0:
        raise ValueError("no closing paren")
    while idx > 0 and text[idx - 1] in "\t ":
        idx -= 1
    return text[:idx] + block + text[idx:]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pretty", type=Path, nargs="?", default=Path("pcbgolf.pretty"))
    ap.add_argument("--margin", type=float, default=0.25,
                    help="clearance added on each side, mm (default 0.25)")
    ap.add_argument("--write", action="store_true", help="edit files; otherwise dry run")
    ap.add_argument("--fix-undersized", action="store_true",
                    help="also enlarge existing courtyards that do not enclose the part")
    args = ap.parse_args(argv)

    changed = skipped = 0
    for path in sorted(args.pretty.glob("*.kicad_mod")):
        fp = sx.load(path)
        existing = local_layer_bbox(fp, ".CrtYd")
        part = part_extent(fp)
        if not existing.empty:
            if encloses(existing, part):
                skipped += 1
                continue
            if not args.fix_undersized:
                print(f"  UNDERSIZED  {path.stem:<26} courtyard "
                      f"{existing.w:.2f}x{existing.h:.2f} does not enclose "
                      f"{part.w:.2f}x{part.h:.2f}  (use --fix-undersized)")
                skipped += 1
                continue
        rect = courtyard_rect(fp, args.margin)
        if rect is None:
            print(f"  SKIP  {path.name}: no pads or fab outline to measure")
            continue
        x1, y1, x2, y2 = rect
        print(f"  {'WRITE' if args.write else 'would'}  {path.stem:<30} "
              f"{x1:>8.3f},{y1:>8.3f} .. {x2:>8.3f},{y2:>8.3f}   "
              f"({x2 - x1:.2f} x {y2 - y1:.2f} mm)")
        if args.write:
            block = TEMPLATE.format(x1=x1, y1=y1, x2=x2, y2=y2, uid=uuid.uuid4())
            path.write_text(insert_before_final_paren(path.read_text(), block))
        changed += 1

    verb = "edited" if args.write else "would edit"
    print(f"\n{verb} {changed} footprint(s), {skipped} already had a courtyard")
    if changed and not args.write:
        print("re-run with --write to apply")
    if changed and args.write:
        print("\nNow pull these into the board:")
        print("  PCB editor -> Tools -> Update Footprints from Library... -> Update all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
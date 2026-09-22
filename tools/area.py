from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sexpr as sx
from score import footprint_bbox, lib_id, on_back, prop


def collect(pcb_path: Path) -> list[dict]:
    pcb = sx.load(pcb_path)
    rows = []
    for fp in sx.find(pcb, "footprint"):
        box = footprint_bbox(fp, local=True)   # local frame: area is rotation-free
        rows.append({
            "ref": prop(fp, "Reference", "?"),
            "value": prop(fp, "Value"),
            "mpn": prop(fp, "MPN"),
            "footprint": lib_id(fp),
            "sheet": str(sx.val(fp, "sheetname", "")),
            "side": "B" if on_back(fp) else "F",
            "w": round(box.w, 2),
            "h": round(box.h, 2),
            "area_mm2": round(box.area, 2),
        })
    return rows


def by_footprint(rows: list[dict]) -> None:
    agg: dict[str, list] = collections.defaultdict(lambda: [0.0, 0, (0.0, 0.0)])
    for r in rows:
        a = agg[r["footprint"]]
        a[0] += r["area_mm2"]
        a[1] += 1
        a[2] = (r["w"], r["h"])
    total = sum(a[0] for a in agg.values()) or 1.0
    print(f"{'total mm2':>10} {'%':>6} {'qty':>5} {'each':>8}  {'dims':<14} footprint")
    cum = 0.0
    for fpname, (area, qty, dims) in sorted(agg.items(), key=lambda kv: -kv[1][0]):
        cum += area
        print(f"{area:>10.1f} {100 * area / total:>5.1f}% {qty:>5} {area / qty:>8.2f}  "
              f"{dims[0]:>5.2f}x{dims[1]:<7.2f} {fpname}"
              + ("   <-- 80% of area above this line" if cum >= 0.8 * total
                 and cum - area < 0.8 * total else ""))
    print(f"\nTOTAL {total:.1f} mm2 of component area over {len(rows)} placements")
    print(f"  double-sided at 60% packing -> {total / 1.2:.0f} mm2 board "
          f"({(total / 1.2) ** 0.5:.1f} mm square)")


def by_part(rows: list[dict]) -> None:
    print(f"{'mm2':>8}  {'ref':<6} {'dims':<14} {'value':<18} {'MPN':<22} {'footprint':<34} sheet")
    for r in sorted(rows, key=lambda r: -r["area_mm2"]):
        print(f"{r['area_mm2']:>8.2f}  {r['ref']:<6} {r['w']:>5.2f}x{r['h']:<7.2f} "
              f"{r['value'][:18]:<18} {r['mpn'][:22]:<22} {r['footprint'][:34]:<34} {r['sheet']}")


def by_sheet(rows: list[dict]) -> None:
    agg: dict[str, list] = collections.defaultdict(lambda: [0.0, 0])
    for r in rows:
        agg[r["sheet"]][0] += r["area_mm2"]
        agg[r["sheet"]][1] += 1
    print(f"{'mm2':>9} {'qty':>5}  sheet")
    for sheet, (area, qty) in sorted(agg.items(), key=lambda kv: -kv[1][0]):
        print(f"{area:>9.1f} {qty:>5}  {sheet}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcb", type=Path, nargs="?", default=Path("pcbgolf.kicad_pcb"))
    ap.add_argument("--parts", action="store_true")
    ap.add_argument("--sheets", action="store_true")
    ap.add_argument("--csv", action="store_true")
    args = ap.parse_args(argv)

    rows = collect(args.pcb)
    if args.csv:
        w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    elif args.parts:
        by_part(rows)
    elif args.sheets:
        by_sheet(rows)
    else:
        by_footprint(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
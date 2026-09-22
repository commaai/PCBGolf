from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from area import collect
from score import LAYER_WEIGHT, VIA_WEIGHT


def load_swaps(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return raw.get("swaps", raw)


def apply_swaps(rows: list[dict], swaps: dict):
    """Per-footprint stock vs planned area, and the resulting totals."""
    agg: dict[str, list] = collections.defaultdict(lambda: [0.0, 0])
    for r in rows:
        agg[r["footprint"]][0] += r["area_mm2"]
        agg[r["footprint"]][1] += 1

    lines = []
    for fpname, (stock, qty) in agg.items():
        swap = swaps.get(fpname)
        planned = stock if swap is None else swap.get("area_mm2", 0.0) * qty
        lines.append({"footprint": fpname, "qty": qty, "stock": stock,
                      "planned": planned, "saved": stock - planned,
                      "why": (swap or {}).get("why", "")})
    lines.sort(key=lambda l: -l["saved"])
    return lines, sum(l["stock"] for l in lines), sum(l["planned"] for l in lines)


def tallest(rows: list[dict], swaps: dict, heights: dict) -> tuple[float, str]:
    """Tallest part after swaps, which is what sets Z."""
    best, who = 0.0, ""
    for fpname in {r["footprint"] for r in rows}:
        swap = swaps.get(fpname) or {}
        h = swap.get("height_mm", heights.get(fpname))
        if h is not None and h > best:
            best, who = float(h), fpname + (" (after swap)" if "height_mm" in swap else "")
    return best, who


def score_of(area: float, z: float, layers: int, vias: int, pack: float, sides: int):
    board = area / (sides * pack)
    volume = board * z
    return {"board": board, "volume": volume,
            "score": volume + VIA_WEIGHT * vias + LAYER_WEIGHT * layers}


def main(argv=None) -> int:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcb", type=Path, nargs="?", default=Path("pcbgolf.kicad_pcb"))
    ap.add_argument("--swaps", type=Path, default=here / "swaps.json")
    ap.add_argument("--heights", type=Path, default=here / "heights.json")
    ap.add_argument("--pack", type=float, default=0.60, help="usable fraction of board area")
    ap.add_argument("--sides", type=int, default=2, choices=(1, 2))
    ap.add_argument("--board-thickness", type=float, default=1.0)
    ap.add_argument("--z", type=float, default=None, help="override total Z in mm")
    ap.add_argument("--layers", type=int, nargs="+", default=[2, 4, 6])
    ap.add_argument("--vias", type=int, nargs="+", default=[100, 200, 350, 500])
    args = ap.parse_args(argv)

    rows = collect(args.pcb)
    swaps = load_swaps(args.swaps)
    heights = json.loads(args.heights.read_text()).get("heights_mm", {}) \
        if args.heights.exists() else {}

    lines, stock_total, planned_total = apply_swaps(rows, swaps)
    print(f"{'saved':>9} {'stock':>9} {'planned':>9} {'qty':>5}  footprint")
    for l in lines:
        if l["saved"] < 0.05 and l["stock"] < 20:
            continue
        print(f"{l['saved']:>9.1f} {l['stock']:>9.1f} {l['planned']:>9.1f} {l['qty']:>5}  "
              f"{l['footprint']}")
    print(f"{'':->9} {'':->9} {'':->9}")
    print(f"{stock_total - planned_total:>9.1f} {stock_total:>9.1f} {planned_total:>9.1f}"
          f"        component area (mm2)")

    tall, who = tallest(rows, swaps, heights)
    z = args.z if args.z is not None else args.board_thickness + tall
    print(f"\nZ = {args.board_thickness}mm board + {tall}mm tallest ({who or 'unknown'})"
          f" = {z:.1f}mm"
          + ("   [overridden]" if args.z is not None else "")
          + "\n  (bottom-side parts add to this -- double-sided assembly trades area for Z)")
    print(f"packing {args.pack:.0%}, {args.sides} side(s) assembled"
          f"  ->  board {planned_total / (args.sides * args.pack):.0f} mm2"
          f" ({(planned_total / (args.sides * args.pack)) ** 0.5:.1f} mm square)\n")

    print("score by layer count and via count:")
    print("  " + "vias:".rjust(10) + "".join(f"{v:>10}" for v in args.vias))
    for layers in args.layers:
        cells = []
        for vias in args.vias:
            s = score_of(planned_total, z, layers, vias, args.pack, args.sides)
            cells.append(f"{s['score']:>10,.0f}")
        print(f"  {layers:>6}L    " + "".join(cells))
    s = score_of(planned_total, z, args.layers[0], args.vias[0], args.pack, args.sides)
    print(f"\n  volume term at this area/Z: {s['volume']:,.0f}"
          f"   |   one copper layer: {LAYER_WEIGHT:,}"
          f"   |   100 vias: {100 * VIA_WEIGHT:,}")
    print("  leaderboard today: 84,578 / 116,226")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
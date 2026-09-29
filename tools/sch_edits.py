from __future__ import annotations

import argparse
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sexpr as sx

MM = 38.10                      # cluster pitch on the CAN-FD sheet
CAN_SHEET = "pcbgolf_4.kicad_sch"
MCU_SHEET = "pcbgolf_2.kicad_sch"
PWR_SHEET = "pcbgolf.kicad_sch"

# Cluster k (k=0..3): everything in this box goes, except what's right of it.
# x 184..223 takes the CANx_H/L labels (186.69), R50-52 (195.58), the +5V
# (186.69), U9 (214.63) and its +12V/GND (212.09); R62 at 229.87 is outside.
CLUSTER_X = (184.0, 223.0)
CLUSTER_Y0 = (19.5, 46.5)       # cluster 0; add k*MM for the rest
LED_NET_ANCHOR = (222.25, 31.75)  # freed end of the U9->R62 wire, cluster 0

MCU_REF = "U3"
LED_PINS = ["PE7", "PE8", "PE9", "PE10"]
LED_NETS = [f"LED_CAN{k}" for k in range(4)]

BH_BOX = ((198.0, 226.0), (105.0, 124.0))   # BH1-4, their GNDs, their wires


# --- top-level node splitting (exact spans, quote-aware) -----------------------

_TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+|\s+')

def top_level_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of every depth-1 node inside the root expression."""
    spans, depth, start = [], 0, None
    for m in _TOK.finditer(text):
        t = m.group()
        if t == "(":
            depth += 1
            if depth == 2:
                start = m.start()
        elif t == ")":
            if depth == 2 and start is not None:
                spans.append((start, m.end()))
                start = None
            depth -= 1
    return spans


def node_at(text: str, span) -> list:
    return sx.loads(text[span[0]:span[1]])


def at_of(node) -> tuple[float, float, float] | None:
    a = sx.kid(node, "at")
    if not a:
        return None
    return float(a[1]), float(a[2]), float(a[3]) if len(a) > 3 else 0.0


def prop(node, key, default=""):
    for p in sx.kids(node, "property"):
        if len(p) > 2 and p[1] == key:
            return str(p[2])
    return default


def inside(pt, box) -> bool:
    (x0, x1), (y0, y1) = box
    return x0 <= pt[0] <= x1 and y0 <= pt[1] <= y1


def wire_points(node):
    return [(float(p[1]), float(p[2])) for p in sx.find(node, "xy")]


def should_delete(node, boxes) -> bool:
    """A symbol/label/junction whose anchor is in a box, or a wire fully in one."""
    kind = sx.name(node)
    if kind == "wire":
        pts = wire_points(node)
        return any(all(inside(p, b) for p in pts) for b in boxes)
    if kind in ("symbol", "global_label", "label", "junction", "no_connect"):
        a = at_of(node)
        return a is not None and any(inside(a[:2], b) for b in boxes)
    return False


def rebuild(text: str, spans, keep_mask, inserts: list[str]) -> str:
    """Keep the header, the kept spans (with their original inter-node text),
    then the inserts, then the root's closing paren."""
    out = [text[:spans[0][0]]]
    prev_end = spans[0][0]
    for (s, e), keep in zip(spans, keep_mask):
        gap = text[prev_end:s]
        if keep:
            out.append(gap + text[s:e])
            prev_end = e
        else:
            prev_end = e
    tail = text[spans[-1][1]:]           # whitespace + final ')'
    out.append("".join(inserts))
    out.append(tail)
    return "".join(out)


def label_template(text: str, spans) -> str:
    """Borrow an existing global_label's exact formatting as the template."""
    for s in spans:
        if text[s[0]:].startswith("(global_label"):
            return text[s[0]:s[1]]
    raise SystemExit("no global_label to use as a template")


def make_label(template: str, name: str, x: float, y: float, rot: float) -> str:
    t = re.sub(r'^\(global_label "[^"]*"', f'(global_label "{name}"', template)
    t = re.sub(r"\(at [-\d.]+ [-\d.]+(?: [-\d.]+)?\)", f"(at {x:g} {y:g} {rot:g})", t, count=1)
    t = re.sub(r'\(uuid "[^"]*"\)', f'(uuid "{uuid.uuid4()}")', t, count=1)
    # the Intersheetrefs property carries its own uuid in some versions
    t = re.sub(r'\(uuid "[^"]*"\)', lambda m: f'(uuid "{uuid.uuid4()}")', t)
    return "\n\t" + t + "\n"


# --- per-sheet edits ---------------------------------------------------------------

def edit_can_sheet(text: str, notes: list[str]) -> str:
    spans = top_level_spans(text)
    boxes = [(CLUSTER_X, (CLUSTER_Y0[0] + k * MM, CLUSTER_Y0[1] + k * MM)) for k in range(4)]
    keep, deleted = [], []
    for s in spans:
        n = node_at(text, s)
        d = should_delete(n, boxes)
        keep.append(not d)
        if d:
            deleted.append(n)
    refs = sorted(prop(n, "Reference") for n in deleted
                  if sx.name(n) == "symbol" and not prop(n, "Reference").startswith("#"))
    kinds = {}
    for n in deleted:
        kinds[sx.name(n)] = kinds.get(sx.name(n), 0) + 1
    notes.append(f"CAN-FD: delete {len(deleted)} nodes {kinds} -> refs {refs}")
    expected = {f"U{n}" for n in range(9, 13)} | {f"R{n}" for n in range(50, 62)}
    missing = expected - set(refs)
    extra = set(refs) - expected
    if missing or extra:
        raise SystemExit(f"CAN-FD cluster selection wrong: missing={missing} extra={extra}")

    template = label_template(text, spans)
    inserts = [make_label(template, LED_NETS[k], LED_NET_ANCHOR[0], LED_NET_ANCHOR[1] + k * MM, 180)
               for k in range(4)]
    notes.append(f"CAN-FD: add global labels {LED_NETS} at x={LED_NET_ANCHOR[0]}")
    text = rebuild(text, spans, keep, inserts)

    n_val = len(re.findall(r'\(property "Value" "2k7"', text))
    if n_val != 4:
        raise SystemExit(f"expected exactly 4 x 2k7 (R62-R65), found {n_val}")
    text = text.replace('(property "Value" "2k7"', '(property "Value" "330"')
    notes.append("CAN-FD: R62-R65 value 2k7 -> 330 (3.3V GPIO drive instead of 12V op-amp)")
    return text


def mcu_pin_positions(text: str, spans) -> dict[str, tuple[float, float]]:
    """Sheet coordinates of the connection point of each LED pin on U3.

    KiCad library symbols are Y-up; the sheet is Y-down, so y is subtracted.
    Only the un-rotated, un-mirrored case is handled -- asserted below.
    """
    root = sx.loads(text)
    u3 = next(n for n in sx.kids(root, "symbol") if prop(n, "Reference") == MCU_REF)
    ax, ay, rot = at_of(u3)
    if rot != 0 or sx.kid(u3, "mirror") is not None:
        raise SystemExit("U3 is rotated/mirrored; pin transform not handled")
    lib_id = str(sx.val(u3, "lib_id"))
    libs = sx.kid(root, "lib_symbols")
    lib = next(s for s in sx.kids(libs, "symbol") if str(s[1]) == lib_id)
    out = {}
    for pin in sx.find(lib, "pin"):
        nm = sx.kid(pin, "name")
        if nm and str(nm[1]) in LED_PINS:
            px, py = float(sx.kid(pin, "at")[1]), float(sx.kid(pin, "at")[2])
            out[str(nm[1])] = (round(ax + px, 2), round(ay - py, 2))
    if set(out) != set(LED_PINS):
        raise SystemExit(f"could not find all LED pins on {lib_id}: {out}")
    return out


def edit_mcu_sheet(text: str, notes: list[str]) -> str:
    spans = top_level_spans(text)
    pins = mcu_pin_positions(text, spans)
    # self-check: each predicted pin must carry a no_connect marker today
    ncs = {at_of(node_at(text, s))[:2] for s in spans if text[s[0]:].startswith("(no_connect")}
    for name, pt in pins.items():
        if pt not in ncs:
            raise SystemExit(f"predicted {name} at {pt} has no no_connect marker -- transform wrong")
    notes.append(f"STM32H7: pin positions verified against no_connect markers: {pins}")

    targets = {pins[p] for p in LED_PINS}
    keep = []
    for s in spans:
        n = node_at(text, s)
        drop = sx.name(n) == "no_connect" and at_of(n)[:2] in targets
        keep.append(not drop)
    notes.append(f"STM32H7: remove {keep.count(False)} no_connect markers")

    template = label_template(text, spans)
    inserts = [make_label(template, LED_NETS[i], *pins[LED_PINS[i]], 180) for i in range(4)]
    notes.append("STM32H7: add " + ", ".join(f"{LED_NETS[i]}@{LED_PINS[i]}" for i in range(4)))
    return rebuild(text, spans, keep, inserts)


def edit_pwr_sheet(text: str, notes: list[str]) -> str:
    spans = top_level_spans(text)
    keep, refs = [], []
    for s in spans:
        n = node_at(text, s)
        d = should_delete(n, [BH_BOX])
        keep.append(not d)
        if d:
            refs.append(n)
    named = sorted(prop(n, "Reference") for n in refs
                   if sx.name(n) == "symbol" and not prop(n, "Reference").startswith("#"))
    if named != ["BH1", "BH2", "BH3", "BH4"]:
        raise SystemExit(f"Power sheet selection wrong: {named}")
    notes.append(f"Power: delete {len(refs)} nodes -> {named} + their GND symbols and wires")
    return rebuild(text, spans, keep, [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=Path("."))
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    notes: list[str] = []
    results = {}
    for fname, fn in ((CAN_SHEET, edit_can_sheet), (MCU_SHEET, edit_mcu_sheet), (PWR_SHEET, edit_pwr_sheet)):
        p = args.dir / fname
        results[p] = fn(p.read_text(), notes)

    for n in notes:
        print("  " + n)
    if args.write:
        for p, t in results.items():
            p.write_text(t)
        print("\nwritten. Next: ERC, then PCB editor -> Update PCB from Schematic"
              " with 'Delete footprints with no symbols' CHECKED.")
    else:
        print("\ndry run -- re-run with --write to apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
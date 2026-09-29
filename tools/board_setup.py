from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

THICKNESS_MM = 0.8

# (ordinal, canonical, type, user name). KiCad 9+/10 copper ordinals: F=0, B=2,
# inner layers 4, 6, 8 ... in stackup order. The user name is what the layer
# panel shows; the canonical name is what everything else references.
COPPER_LAYERS = [
    (0, "F.Cu", "signal", None),
    (4, "In1.Cu", "signal", "GND"),
    (6, "In2.Cu", "signal", "PWR"),
    (2, "B.Cu", "signal", None),
]

# JLCPCB standard: 0.15/0.15 track/clearance, 0.25/0.15 via, 0.2 preferred
# hole, hole-to-hole 0.5, copper-to-edge 0.2. Set just inside those so a
# DRC-clean board is comfortably manufacturable, not at the edge of yield.
RULES = {
    "min_clearance": 0.15,
    "min_track_width": 0.15,
    "min_via_annular_width": 0.075,
    "min_via_diameter": 0.30,
    "min_through_hole_diameter": 0.20,
    "min_hole_to_hole": 0.50,
    "min_hole_clearance": 0.25,
    "min_copper_edge_clearance": 0.25,
}

DEFAULT_CLASS = {"clearance": 0.2, "track_width": 0.2,
                 "via_diameter": 0.4, "via_drill": 0.2}

POWER_CLASS = {"name": "Power", "priority": 0,
               "clearance": 0.25, "track_width": 0.5,
               "via_diameter": 0.6, "via_drill": 0.3}

POWER_PATTERNS = ["+12V", "+5V", "+3V3", "GND", "VBUS",
                  "Net-(J1-PWR)", "Net-(J?-VBUS-PadA4)"]


# --- .kicad_pcb ----------------------------------------------------------------

def patch_pcb(text: str) -> tuple[str, list[str]]:
    notes = []

    new = re.sub(r"\(thickness [\d.]+\)", f"(thickness {THICKNESS_MM})", text, count=1)
    if new != text:
        notes.append(f"thickness -> {THICKNESS_MM} mm")
    text = new

    m = re.search(r"^\t\(layers\n(.*?)^\t\)\n", text, re.S | re.M)
    if not m:
        raise SystemExit("no (layers) block found")
    body = m.group(1)
    non_copper = [ln for ln in body.splitlines(keepends=True)
                  if not re.match(r'\t\t\(\d+ "[^"]*\.Cu"', ln)]
    copper = []
    for ordinal, canon, kind, user in COPPER_LAYERS:
        line = f'\t\t({ordinal} "{canon}" {kind}' + (f' "{user}"' if user else "") + ")\n"
        copper.append(line)
    new_body = "".join(copper + non_copper)
    if new_body != body:
        have = re.findall(r'"([^"]*\.Cu)"', body)
        notes.append(f"copper layers {have} -> {[c[1] for c in COPPER_LAYERS]}")
        text = text[:m.start(1)] + new_body + text[m.end(1):]
    return text, notes


# --- .kicad_pro ----------------------------------------------------------------

def patch_pro(pro: dict) -> tuple[dict, list[str]]:
    notes = []
    rules = pro.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
    for k, v in RULES.items():
        if rules.get(k) != v:
            notes.append(f"rules.{k}: {rules.get(k)} -> {v}")
            rules[k] = v

    ns = pro.setdefault("net_settings", {})
    classes = ns.setdefault("classes", [])
    by_name = {c.get("name"): c for c in classes}

    default = by_name.get("Default")
    if default is None:
        raise SystemExit("no Default net class in .kicad_pro")
    for k, v in DEFAULT_CLASS.items():
        if default.get(k) != v:
            notes.append(f"class Default.{k}: {default.get(k)} -> {v}")
            default[k] = v

    if "Power" not in by_name:
        power = dict(default)          # inherit every field KiCad expects
        power.update(POWER_CLASS)
        classes.append(power)
        notes.append("class Power: added")
    else:
        for k, v in POWER_CLASS.items():
            if by_name["Power"].get(k) != v:
                notes.append(f"class Power.{k}: {by_name['Power'].get(k)} -> {v}")
                by_name["Power"][k] = v

    patterns = ns.setdefault("netclass_patterns", [])
    have = {(p.get("netclass"), p.get("pattern")) for p in patterns}
    for pat in POWER_PATTERNS:
        if ("Power", pat) not in have:
            patterns.append({"netclass": "Power", "pattern": pat})
            notes.append(f"pattern Power <- {pat}")
    return pro, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcb", type=Path, default=Path("pcbgolf.kicad_pcb"))
    ap.add_argument("--pro", type=Path, default=Path("pcbgolf.kicad_pro"))
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    pcb_text, pcb_notes = patch_pcb(args.pcb.read_text())
    pro, pro_notes = patch_pro(json.loads(args.pro.read_text()))

    for label, notes in ((args.pcb.name, pcb_notes), (args.pro.name, pro_notes)):
        print(f"{label}:")
        for n in notes or ["  (no change)"]:
            print(f"  {n}")

    if args.write:
        args.pcb.write_text(pcb_text)
        args.pro.write_text(json.dumps(pro, indent=2) + "\n")
        print("\nwritten. Quit and reopen KiCad so it reloads both files.")
    elif pcb_notes or pro_notes:
        print("\ndry run -- re-run with --write to apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
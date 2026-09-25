"""Synthetic kitchen cases, generated from scratch from a seed.

Nothing here is derived from a real drawing, a customer file or any dataset. Each case
is built by a seeded random process from standard cabinet widths and a handful of
layout rules, and is emitted in the three shapes the verification layer consumes:

- ``spec``: a full specification that validates against ``mozaik_automation.models.CabinetSpec``;
- ``extraction``: the compact form the comparator reads (parsed counts, typed cabinets
  with free-text notes, appliances, room shape);
- ``analysis``: what a correct image analyser would report for a correct build, in the
  format of ``mozaik_automation.verification.comparator.ANALYSIS_SCHEMA``.

Fault injectors then corrupt a copy of ``analysis`` (a wrong build, or a wrong reading of
it) or of ``extraction`` (a wrong extraction, for the pre-build gate). Each injector names
the comparator check it is expected to trip, or ``None`` when the fault lies outside what
the comparator checks, so that the benchmark reports coverage honestly.

Usage:
    python benchmarks/synthetic.py --seed 20260925 --cases 3 --out tests/fixtures/synthetic
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Callable, Optional

GENERATOR_VERSION = "1"

SHAPES = ["single-wall", "L-shape", "U-shape", "galley"]
WALLS_BY_SHAPE = {
    "single-wall": ["back"],
    "L-shape": ["left", "back"],
    "U-shape": ["left", "back", "right"],
    "galley": ["back", "front"],
}
BASE_WIDTHS = [12, 15, 18, 21, 24, 27, 30, 33, 36]
WALL_WIDTHS = [12, 15, 18, 21, 24, 27, 30, 33, 36]
BASE_CONFIGS = [
    # (note, doors, drawers, cabinet_type)
    ("1 door 1 drawer", 1, 1, "base"),
    ("2 door 1 drawer", 2, 1, "base"),
    ("3 drawer", 0, 3, "drawer_base"),
    ("4 drawer", 0, 4, "drawer_base"),
]
WALL_CONFIGS = [("1 door", 1), ("2 door", 2)]
SKIPPED_BY_EXTRACTION = {"dishwasher", "microwave"}


def _position(i: int, n: int) -> str:
    if n == 1:
        return "center"
    if i == 0:
        return "leftmost"
    if i == n - 1:
        return "rightmost"
    return "center"


def make_case(rng: random.Random, case_id: int) -> dict[str, Any]:
    """Build one synthetic case: spec, extraction and a correct analysis."""
    shape = rng.choice(SHAPES)
    wall_ids = WALLS_BY_SHAPE[shape]
    wall_lengths = {w: rng.choice([96, 108, 120, 132, 144, 156, 168]) for w in wall_ids}
    ceiling = rng.choice([96, 108])

    # Walls laid out on a simple rectilinear frame (inches).
    frame = {
        "back": ((0, 0), (wall_lengths["back"], 0)),
        "left": ((0, wall_lengths.get("left", 0)), (0, 0)),
        "right": ((wall_lengths["back"], 0), (wall_lengths["back"], wall_lengths.get("right", 0))),
        "front": ((0, 120), (wall_lengths.get("front", 0), 120)),
    }
    walls = [
        {"id": w, "start": list(frame[w][0]), "end": list(frame[w][1]), "thickness": 4.5}
        for w in wall_ids
    ]

    sink_wall = rng.choice(wall_ids)
    bowls = rng.choice([1, 2])
    cabinets: list[dict[str, Any]] = []
    extraction_cabs: list[dict[str, Any]] = []
    analysis = {"base_cabinets": [], "wall_cabinets": [], "tall_cabinets": [], "appliances": []}
    appliances: list[dict[str, Any]] = []
    appliance_types: list[str] = []

    def add_appliance(kind: str, wall: str, offset: float, width: float, note: str = "") -> None:
        appliances.append({
            "id": f"A{len(appliances) + 1}",
            "appliance_type": kind,
            "position": {"wall_id": wall, "offset": offset, "elevation": 0},
            "dimensions": {"width": width},
        })
        # The extraction rules skip appliances the target application has no tab for
        # (docs/personas/extraction-qa.md), so they are drawn but never built or checked.
        if kind in SKIPPED_BY_EXTRACTION:
            return
        appliance_types.append(kind)
        entry = {"type": kind}
        if note:
            entry["note"] = note
        extraction_appliances.append(entry)

    extraction_appliances: list[dict[str, Any]] = []
    hood_spans: dict[str, tuple[float, float]] = {}
    for wall in wall_ids:
        # Leave the corner to the run that ends in it, so footprints do not overlap.
        corner = 24.0 if (wall == "back" and "left" in wall_ids) or wall == "right" else 0.0
        remaining = wall_lengths[wall] - corner
        offset = corner
        # A refrigerator at the start of the first wall, a tall pantry sometimes.
        if wall == wall_ids[0]:
            add_appliance("refrigerator", wall, offset, 36)
            offset += 36
            remaining -= 36
            if rng.random() < 0.5 and remaining >= 60:
                cabinets.append({
                    "id": f"T{len(cabinets) + 1}", "cabinet_type": "tall_pantry",
                    "position": {"wall_id": wall, "offset": offset, "elevation": 0},
                    "dimensions": {"width": 24, "height": 84, "depth": 24},
                    "configuration": {"door_count": 2, "drawer_count": 0},
                    "notes": "pantry 2 door",
                })
                extraction_cabs.append({"type": "tall", "wall": wall, "note": "pantry 2 door"})
                analysis["tall_cabinets"].append({"position": "left", "doors": 2})
                offset += 24
                remaining -= 24
        placed_sink = False
        placed_range = False
        while remaining >= 12:
            if wall == sink_wall and not placed_sink and remaining >= 60:
                width = 36
                note = f"sink base 2 door, {'double' if bowls == 2 else 'single'} bowl"
                cabinets.append({
                    "id": f"B{len(cabinets) + 1}", "cabinet_type": "base_sink",
                    "position": {"wall_id": wall, "offset": offset, "elevation": 0},
                    "dimensions": {"width": width, "height": 34.5, "depth": 24},
                    "configuration": {"door_count": 2, "drawer_count": 0},
                    "notes": note,
                })
                extraction_cabs.append({"type": "base", "wall": wall, "note": "sink base 2 door"})
                analysis["base_cabinets"].append(
                    {"doors": 2, "drawers": 0, "has_sink": True, "sink_bowls": bowls})
                add_appliance("sink", wall, offset + 3, 30, f"{'double' if bowls == 2 else 'single'} bowl")
                offset += width
                remaining -= width
                placed_sink = True
                if remaining >= 24:
                    add_appliance("dishwasher", wall, offset, 24)
                    offset += 24
                    remaining -= 24
                continue
            if wall != sink_wall and not placed_range and remaining >= 54 and "range" not in appliance_types:
                add_appliance("range", wall, offset, 30)
                add_appliance("hood", wall, offset, 30)
                hood_spans[wall] = (offset, offset + 30)
                offset += 30
                remaining -= 30
                placed_range = True
                continue
            width = rng.choice([w for w in BASE_WIDTHS if w <= remaining])
            note, doors, drawers, ctype = rng.choice(BASE_CONFIGS)
            cabinets.append({
                "id": f"B{len(cabinets) + 1}", "cabinet_type": ctype,
                "position": {"wall_id": wall, "offset": offset, "elevation": 0},
                "dimensions": {"width": width, "height": 34.5, "depth": 24},
                "configuration": {"door_count": doors, "drawer_count": drawers},
                "notes": note,
            })
            extraction_cabs.append({"type": "base", "wall": wall, "note": note})
            analysis["base_cabinets"].append(
                {"doors": doors, "drawers": drawers, "has_sink": False, "sink_bowls": None})
            offset += width
            remaining -= width

        # Wall cabinets above the run, skipping the hood position.
        w_offset = 36.0 if wall == wall_ids[0] else corner
        w_remaining = wall_lengths[wall] - w_offset
        n_wall = rng.randint(1, 3)
        for _ in range(n_wall):
            if wall in hood_spans and w_offset < hood_spans[wall][1]:
                start, end = hood_spans[wall]
                room_before = start - w_offset
                if room_before < 12:
                    # Not enough space before the hood: continue after it.
                    w_remaining -= end - w_offset
                    w_offset = end
            limit = w_remaining
            if wall in hood_spans and w_offset < hood_spans[wall][0]:
                limit = min(limit, hood_spans[wall][0] - w_offset)
            fits = [w for w in WALL_WIDTHS if w <= limit]
            if not fits:
                break
            width = rng.choice(fits)
            note, doors = rng.choice(WALL_CONFIGS)
            cabinets.append({
                "id": f"W{len(cabinets) + 1}", "cabinet_type": "wall",
                "position": {"wall_id": wall, "offset": w_offset, "elevation": 54},
                "dimensions": {"width": width, "height": 30, "depth": 12},
                "configuration": {"door_count": doors, "drawer_count": 0},
                "notes": note,
            })
            extraction_cabs.append({"type": "wall", "wall": wall, "note": note})
            analysis["wall_cabinets"].append({"doors": doors})
            w_offset += width
            w_remaining -= width

    # Guarantee a sink exists even when the sink wall was too short for the rule above.
    if "sink" not in appliance_types:
        add_appliance("sink", sink_wall, 0, 30, f"{'double' if bowls == 2 else 'single'} bowl")

    # Positions are informational for the comparator; fill them in reading order.
    for key in ("base_cabinets", "wall_cabinets", "tall_cabinets"):
        n = len(analysis[key])
        for i, entry in enumerate(analysis[key]):
            entry["position"] = _position(i, n)
    analysis["appliances"] = [
        {"type": t, "sink_bowls": bowls if t == "sink" else None} for t in appliance_types
    ]
    analysis["layout_shape"] = shape

    # The comparator matches cabinets by type-then-sequence, so order the extraction the same way.
    order = {"base": 0, "wall": 1, "tall": 2}
    extraction_cabs.sort(key=lambda c: order[c["type"]])
    parsed = {t: sum(1 for c in extraction_cabs if c["type"] == t) for t in ("base", "wall", "tall")}

    spec = {
        "metadata": {
            "job_name": f"Synthetic case {case_id:03d}",
            "client_name": None,
            "created_at": "2026-09-25T00:00:00",
            "source_file": f"synthetic_{case_id:03d}.png",
            "source_type": "floor_plan",
            "notes": f"Generated by benchmarks/synthetic.py v{GENERATOR_VERSION}; not derived from any drawing.",
        },
        "room": {"name": "Kitchen", "units": "in", "ceiling_height": ceiling, "walls": walls, "openings": []},
        "cabinets": cabinets,
        "appliances": appliances,
    }
    extraction = {
        "parsed": parsed,
        "cabinets": extraction_cabs,
        "appliances": extraction_appliances,
        "room": {"shape": shape, "walls": [{"name": w, "length": wall_lengths[w]} for w in wall_ids]},
    }
    notes = {a["type"]: a.get("note") for a in extraction_appliances}
    return {"id": f"synthetic_{case_id:03d}", "spec": spec, "extraction": extraction,
            "analysis": analysis, "extraction_notes": notes}


def generate(seed: int, n: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    return [make_case(rng, i) for i in range(n)]


# ---------------------------------------------------------------------------
# Fault injectors. Each returns the corrupted copy, or None when the case has
# nothing the fault can act on (for example, no tall cabinet to remove).
# ---------------------------------------------------------------------------

Fault = Callable[[dict[str, Any], random.Random], Optional[dict[str, Any]]]


def _first_with(entries: list[dict], pred) -> Optional[int]:
    for i, e in enumerate(entries):
        if pred(e):
            return i
    return None


def f_missing_base(a, rng):
    if not a["base_cabinets"]:
        return None
    a["base_cabinets"].pop(rng.randrange(len(a["base_cabinets"])))
    return a


def f_extra_wall(a, rng):
    a["wall_cabinets"].append({"position": "right", "doors": 2})
    return a


def f_missing_tall(a, rng):
    if not a["tall_cabinets"]:
        return None
    a["tall_cabinets"].pop()
    return a


def f_missing_appliance(a, rng):
    idx = [i for i, e in enumerate(a["appliances"]) if e["type"] not in ("sink",)]
    if not idx:
        return None
    a["appliances"].pop(rng.choice(idx))
    return a


def f_phantom_appliance(a, rng):
    present = {e["type"] for e in a["appliances"]}
    for kind in ("microwave", "wine_cooler", "wall_oven"):
        if kind not in present:
            a["appliances"].append({"type": kind, "sink_bowls": None})
            return a
    return None


def f_wrong_doors(a, rng):
    i = _first_with(a["base_cabinets"], lambda e: e["doors"] > 0 and not e["has_sink"])
    if i is None:
        return None
    a["base_cabinets"][i]["doors"] += 1
    return a


def f_wrong_drawers(a, rng):
    i = _first_with(a["base_cabinets"], lambda e: e["drawers"] > 0)
    if i is None:
        return None
    a["base_cabinets"][i]["drawers"] += 1
    return a


def f_sink_on_wrong_cabinet(a, rng):
    sink = _first_with(a["base_cabinets"], lambda e: e["has_sink"])
    other = _first_with(a["base_cabinets"], lambda e: not e["has_sink"])
    if sink is None or other is None:
        return None
    a["base_cabinets"][sink]["has_sink"] = False
    a["base_cabinets"][other]["has_sink"] = True
    return a


def f_wrong_bowls(a, rng):
    for e in a["appliances"]:
        if e["type"] == "sink" and e.get("sink_bowls"):
            e["sink_bowls"] = 1 if e["sink_bowls"] == 2 else 2
            return a
    return None


def f_wrong_shape(a, rng):
    a["layout_shape"] = rng.choice([s for s in SHAPES if s != a["layout_shape"]])
    return a


def f_wrong_width(a, rng):
    """A dimensional error. ANALYSIS_SCHEMA carries no widths, so the comparator cannot see it."""
    if not a["base_cabinets"]:
        return None
    a["base_cabinets"][0]["width_in"] = 99
    return a


# name -> (injector, check name or category the comparator is expected to fail; None = not covered)
BUILD_FAULTS: dict[str, tuple[Fault, Optional[str]]] = {
    "missing_base_cabinet": (f_missing_base, "base_cabinet_count"),
    "extra_wall_cabinet": (f_extra_wall, "wall_cabinet_count"),
    "missing_tall_cabinet": (f_missing_tall, "tall_cabinet_count"),
    "missing_appliance": (f_missing_appliance, "appliance"),
    "phantom_appliance": (f_phantom_appliance, "no_phantom_appliances"),
    "wrong_door_count": (f_wrong_doors, "cabinet_config"),
    "wrong_drawer_count": (f_wrong_drawers, "cabinet_config"),
    "sink_on_wrong_cabinet": (f_sink_on_wrong_cabinet, "cabinet_config"),
    "wrong_sink_bowls": (f_wrong_bowls, "sink_bowl_match"),
    "wrong_layout_shape": (f_wrong_shape, "layout_shape"),
    "wrong_cabinet_width": (f_wrong_width, None),
}


def e_missing_base(x, rng):
    if x["parsed"]["base"] == 0:
        return None
    x["parsed"]["base"] -= 1
    return x


def e_two_missing_base(x, rng):
    if x["parsed"]["base"] < 2:
        return None
    x["parsed"]["base"] -= 2
    return x


def e_phantom_appliance(x, rng):
    x["appliances"].append({"type": "microwave"})
    return x


# Pre-build gate faults act on the extraction and are checked against the upload analysis.
PREBUILD_FAULTS: dict[str, tuple[Fault, Optional[str]]] = {
    "extraction_missed_one_base": (e_missing_base, "pre_build_base_count"),
    "extraction_missed_two_base": (e_two_missing_base, "pre_build_base_count"),
    "extraction_phantom_appliance": (e_phantom_appliance, "pre_build_appliance_types"),
}


def inject(case: dict[str, Any], fault: Fault, target: str, seed: int) -> Optional[dict[str, Any]]:
    rng = random.Random(seed)
    return fault(copy.deepcopy(case[target]), rng)


# ---------------------------------------------------------------------------
# Plan-view rendering, for the extraction benchmark. Drawn from the spec alone.
# ---------------------------------------------------------------------------

def render_plan(case: dict[str, Any], path: Path, scale: float = 4.0) -> Path:
    from PIL import Image, ImageDraw

    spec = case["spec"]
    margin = 60
    xs = [p for w in spec["room"]["walls"] for p in (w["start"][0], w["end"][0])]
    ys = [p for w in spec["room"]["walls"] for p in (w["start"][1], w["end"][1])]
    width = int((max(xs) + 40) * scale) + 2 * margin
    height = int((max(ys) + 60) * scale) + 2 * margin
    img = Image.new("RGB", (max(width, 400), max(height, 400)), "white")
    d = ImageDraw.Draw(img)

    def pt(x, y):
        return (margin + x * scale, margin + y * scale)

    walls = {w["id"]: w for w in spec["room"]["walls"]}
    for w in walls.values():
        d.line([pt(*w["start"]), pt(*w["end"])], fill="black", width=6)

    def footprint(wall_id, offset, w, depth):
        wall = walls[wall_id]
        (x0, y0), (x1, y1) = wall["start"], wall["end"]
        length = max(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5, 1)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = -uy, ux
        if wall_id in ("back",):
            nx, ny = 0, 1
        if wall_id == "front":
            nx, ny = 0, -1
        if wall_id == "left":
            nx, ny = 1, 0
        if wall_id == "right":
            nx, ny = -1, 0
        a = (x0 + ux * offset, y0 + uy * offset)
        b = (a[0] + ux * w, a[1] + uy * w)
        c = (b[0] + nx * depth, b[1] + ny * depth)
        e = (a[0] + nx * depth, a[1] + ny * depth)
        return [pt(*a), pt(*b), pt(*c), pt(*e)]

    codes = {"base": "B", "drawer_base": "DB", "base_sink": "SB", "wall": "W", "tall_pantry": "T"}
    for cab in spec["cabinets"]:
        pos, dim = cab["position"], cab["dimensions"]
        depth = dim.get("depth") or 24
        poly = footprint(pos["wall_id"], pos["offset"], dim["width"], depth)
        dashed = cab["cabinet_type"] == "wall"
        d.polygon(poly, outline="gray" if dashed else "black", width=2)
        # Wall-cabinet labels sit near the wall, base labels near the room edge, so the
        # two runs drawn over each other stay legible.
        wall_mid = ((poly[0][0] + poly[1][0]) / 2, (poly[0][1] + poly[1][1]) / 2)
        room_mid = ((poly[2][0] + poly[3][0]) / 2, (poly[2][1] + poly[3][1]) / 2)
        t = 0.3 if dashed else 0.75
        if cab["cabinet_type"] == "base_sink":
            t = 0.85  # keep the label clear of the bowls drawn at the centre
        cx = wall_mid[0] + (room_mid[0] - wall_mid[0]) * t
        cy = wall_mid[1] + (room_mid[1] - wall_mid[1]) * t
        label = f"{codes.get(cab['cabinet_type'], 'B')}{int(dim['width'])}"
        d.text((cx - 12, cy - 6), label, fill="blue" if dashed else "black")
    hooded = {(a["position"]["wall_id"], a["position"]["offset"])
              for a in spec["appliances"] if a["appliance_type"] == "hood"}
    for app in spec["appliances"]:
        pos, dim = app["position"], app["dimensions"]
        kind = app["appliance_type"]
        if kind == "hood":
            continue  # drawn with the range it sits above
        poly = footprint(pos["wall_id"], pos["offset"], dim["width"], 24)
        cx = sum(p[0] for p in poly) / 4
        cy = sum(p[1] for p in poly) / 4
        if kind == "sink":
            bowls = 2 if "double" in (case["extraction_notes"].get("sink") or "") else 1
            if bowls == 2:
                d.ellipse([cx - 26, cy - 10, cx - 2, cy + 10], outline="black", width=2)
                d.ellipse([cx + 2, cy - 10, cx + 26, cy + 10], outline="black", width=2)
            else:
                d.ellipse([cx - 16, cy - 10, cx + 16, cy + 10], outline="black", width=2)
            continue
        d.polygon(poly, outline="darkgreen", width=2)
        label = {"refrigerator": "REF", "dishwasher": "DW", "range": "RANGE"}.get(kind, kind.upper()[:6])
        d.text((cx - 14, cy - 12), label, fill="darkgreen")
        if kind == "range" and (pos["wall_id"], pos["offset"]) in hooded:
            d.text((cx - 14, cy + 2), "HOOD", fill="darkgreen")
    d.text((margin, 15), f"{spec['metadata']['job_name']} (synthetic plan view, inches)", fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--cases", type=int, default=3)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--no-images", action="store_true", help="skip plan-view PNGs")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {"generator": "benchmarks/synthetic.py", "generator_version": GENERATOR_VERSION,
                "seed": args.seed, "cases": args.cases, "files": {}}
    for case in generate(args.seed, args.cases):
        p = args.out / f"{case['id']}.json"
        p.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n")
        manifest["files"][p.name] = _sha256(p)
        if not args.no_images:
            img = render_plan(case, args.out / f"{case['id']}.png")
            manifest["files"][img.name] = _sha256(img)
    if not args.no_images:
        import PIL
        manifest["pillow_version"] = PIL.__version__
    (args.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.cases} cases to {args.out}")


if __name__ == "__main__":
    main()

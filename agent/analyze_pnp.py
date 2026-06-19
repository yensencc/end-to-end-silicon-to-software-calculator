#!/usr/bin/env python3
"""
SMT Pick-and-Place Trajectory Analyzer
Simulates Fuji AIMEX III head travel, computes statistics,
generates path visualization, and suggests sequence optimization.

Usage:
  python analyze_pnp.py                    # console report only
  python analyze_pnp.py --view             # static analysis PNG
  python analyze_pnp.py --animate          # animated trajectory GIF
  python analyze_pnp.py --all              # both + report
"""

import csv
import math
import sys
import os
import argparse
import re

try:
    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    import matplotlib.patches as mpatches
    import numpy as np
except ImportError:
    print("matplotlib not found — run: pip install matplotlib numpy", file=sys.stderr)
    sys.exit(1)

FAB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fab")
POS_FILE = os.path.join(FAB_DIR, "calculator_pos.csv")
SCHEMATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schematic")

BOARD_W, BOARD_H = 62, 42
FEEDER = (BOARD_W / 2, -8)

PCB_BG_CACHE = os.path.join(FAB_DIR, ".pcb_background.png")


def load_pcb_background():
    """Render and cache a PCB background image using kicad-cli SVG export.

    Returns (image_array, extent) for use with ax.imshow(), or None.
    """
    svg_path = os.path.join(FAB_DIR, ".pcb_background.svg")
    png_path = PCB_BG_CACHE
    kicad_pcb = os.path.join(SCHEMATIC_DIR, "calculator.kicad_pcb")

    if not os.path.exists(kicad_pcb):
        return None

    # Regenerate if PCB source is newer than cached image
    need_regenerate = (not os.path.exists(png_path) or
                       os.path.getmtime(kicad_pcb) > os.path.getmtime(png_path))

    if need_regenerate:
        # Use pre-rendered PNG if available, else render from KiCad
        pre_render = os.path.join(FAB_DIR, "calculator_pcb.png")
        if os.path.exists(pre_render):
            im = plt.imread(pre_render)
            return (im, [0, BOARD_W, 0, BOARD_H])

        # Export SVG from KiCad (fast export, moderate resolution)
        cmd = (f"/opt/homebrew/bin/kicad-cli pcb export svg "
               f"\"{kicad_pcb}\" --layers F.Cu,F.SilkS,Edge.Cuts,F.Mask "
               f"--output \"{svg_path}\" --fit-page-to-board "
               f"--exclude-drawing-sheet --mode-single --scale 5 2>&1")
        ret = os.system(cmd)
        if ret != 0 or not os.path.exists(svg_path):
            return None
        try:
            import cairosvg
            cairosvg.svg2png(url=svg_path, write_to=png_path, scale=2)
        except Exception:
            return None

    if not os.path.exists(png_path):
        return None

    im = plt.imread(png_path)
    # SVG viewBox covers the board from (0,0) to (BOARD_W, BOARD_H)
    extent = [0, BOARD_W, 0, BOARD_H]
    return (im, extent)

HEAD_SPEED_MM_S = 500     # mm/s (0.5 m/s typical for SMT gantry)
PICK_TIME_S = 0.3          # time to pick a component from feeder
PLACE_TIME_S = 0.3         # time to place a component on PCB

# Type inference from reference designator prefix
TYPE_PREFIXES = {
    "U": "IC", "DISP": "Display", "J": "Connector",
    "R": "Resistor", "SW": "Switch",
}

COLORS_PLOT = {"IC": "#e74c3c", "Display": "#9b59b6",
               "Connector": "#3498db", "Resistor": "#2ecc71",
               "Switch": "#e67e22", "Other": "#95a5a6"}


def comp_type(ref):
    """Extract type from reference designator (e.g. R1 -> Resistor)."""
    m = re.match(r"^([A-Z]+)", ref)
    prefix = m.group(1) if m else ""
    return TYPE_PREFIXES.get(prefix, "Other")


def load_components():
    components = []
    with open(POS_FILE) as f:
        reader = csv.DictReader(f)
        for row in reader:
            components.append({
                "ref": row["Ref"],
                "val": row["Val"],
                "x": float(row["PosX"]),
                "y": float(row["PosY"]),
                "side": row["Side"],
            })
    type_order = {t: i for i, t in enumerate(["Connector", "IC", "Display", "Resistor", "Switch"])}
    components.sort(key=lambda c: (type_order.get(comp_type(c["ref"]), 99), c["ref"]))
    return components


def comp_pos(c):
    return (c["x"], -c["y"])


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ─── Trajectory model ────────────────────────────────────────

def build_trajectory(comps, feeder=FEEDER):
    """Build full head trajectory as list of segments.

    Returns (waypoints, segments) where:
      waypoints: [(x,y,comp_idx,label), ...] for every stop
      segments:  [(x1,y1,x2,y2,type,comp_idx,dist_mm), ...]
    """
    waypoints = []
    segments = []

    for i, c in enumerate(comps):
        target = comp_pos(c)

        # Feeder → target (pick + place)
        waypoints.append((feeder[0], feeder[1], None, "pick"))
        waypoints.append((target[0], target[1], i, "place"))

        seg_dist = dist(feeder, target)
        segments.append((feeder[0], feeder[1], target[0], target[1],
                         "feed2board", i, seg_dist))

        # Return to feeder (except last)
        if i < len(comps) - 1:
            waypoints.append((feeder[0], feeder[1], None, "return"))
            seg_dist2 = dist(target, feeder)
            segments.append((target[0], target[1], feeder[0], feeder[1],
                             "board2feed", i, seg_dist2))

    return waypoints, segments


def trajectory_stats(comps, feeder=FEEDER):
    """Compute full trajectory statistics."""
    total_dist = 0.0
    feed2board_dist = 0.0
    board2feed_dist = 0.0
    per_comp = []

    for i, c in enumerate(comps):
        target = comp_pos(c)
        d_out = dist(feeder, target)
        feed2board_dist += d_out
        total_dist += d_out

        if i < len(comps) - 1:
            d_back = dist(target, feeder)
            board2feed_dist += d_back
            total_dist += d_back

        travel_time = total_dist / HEAD_SPEED_MM_S
        cycle_time = len(comps) * (PICK_TIME_S + PLACE_TIME_S) + travel_time

        per_comp.append({
            "ref": c["ref"],
            "val": c["val"],
            "type": comp_type(c["ref"]),
            "x": target[0], "y": target[1],
            "dist_feed2board": d_out,
            "dist_total_accum": total_dist,
        })

    total_time = total_dist / HEAD_SPEED_MM_S
    total_cycle = total_time + len(comps) * (PICK_TIME_S + PLACE_TIME_S)
    placements_per_hour = 3600 / total_cycle if total_cycle > 0 else 0

    return {
        "total_distance_mm": total_dist,
        "feed2board_mm": feed2board_dist,
        "board2feed_mm": board2feed_dist,
        "travel_time_s": total_time,
        "pick_place_time_s": len(comps) * (PICK_TIME_S + PLACE_TIME_S),
        "total_cycle_s": total_cycle,
        "placements_per_hour": placements_per_hour,
        "per_component": per_comp,
    }


# ─── Optimization (nearest-neighbor) ─────────────────────────

def optimize_sequence(comps, feeder=FEEDER):
    """Reorder components using nearest-neighbor heuristic.

    Starts from feeder position, then repeatedly picks the closest
    unplaced component.  This minimizes travel for single-nozzle heads.
    """
    if not comps:
        return []

    remaining = list(comps)
    current = feeder
    ordered = []

    while remaining:
        nearest = min(remaining,
                      key=lambda c: dist(current, comp_pos(c)))
        ordered.append(nearest)
        remaining.remove(nearest)
        current = comp_pos(nearest)

    return ordered


# ─── Static analysis view (PNG) ──────────────────────────────

COLORS_PLOT = {"IC": "#e74c3c", "Display": "#9b59b6",
               "Connector": "#3498db", "Resistor": "#2ecc71",
               "Switch": "#e67e22"}


def plot_analysis(comps, save_path=None):
    n = len(comps)
    _, segments = build_trajectory(comps)
    stats = trajectory_stats(comps)
    opt_comps = optimize_sequence(comps)
    opt_stats = trajectory_stats(opt_comps)

    fig = plt.figure(figsize=(18, 10), constrained_layout=False)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.6, 1], wspace=0.3)

    # ── Left panel: PCB path map ──
    ax = fig.add_subplot(gs[0])
    ax.set_xlim(-5, BOARD_W + 5)
    ax.set_ylim(-10, BOARD_H + 5)
    ax.set_aspect("equal")
    ax.set_title("Placement Path & Sequence", fontsize=14, weight="bold")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")

    # PCB background (actual board image from KiCad)
    bg = load_pcb_background()
    if bg:
        bg_im, bg_extent = bg
        ax.imshow(bg_im, extent=bg_extent, origin="lower", zorder=0,
                  alpha=0.85)
    board = mpatches.Rectangle((0, 0), BOARD_W, BOARD_H,
                               linewidth=2, edgecolor="black",
                               facecolor="none", zorder=1)
    ax.add_patch(board)

    # Feeder (below board)
    feeder_rect = mpatches.Rectangle((-4, -14), BOARD_W + 8, 8,
                                     linewidth=1, edgecolor="#888",
                                     facecolor="#fff3cd", alpha=0.5)
    ax.add_patch(feeder_rect)
    ax.text(FEEDER[0], FEEDER[1] - 3, "FEEDER", ha="center", fontsize=9,
            color="#666", weight="bold")
    ax.plot(FEEDER[0], FEEDER[1], marker="v", color="#cc7700",
            markersize=14, zorder=5)

    # Components (colored dots on top of PCB)
    for i, c in enumerate(comps):
        pt = comp_pos(c)
        color = COLORS_PLOT.get(comp_type(c["ref"]), "gray")
        size = 180 if c["ref"].startswith("U") else 100
        ax.scatter(pt[0], pt[1], c=color, s=size, alpha=0.7,
                   edgecolors="white", linewidth=1.5, zorder=4)
        ax.annotate(f"{i + 1}", (pt[0], pt[1]),
                    fontsize=7, ha="center", va="center",
                    weight="bold", color="white")

    # Path arrows + step numbers on board
    prev_pt = FEEDER
    for i, c in enumerate(comps):
        pt = comp_pos(c)
        ax.annotate("", xy=pt, xytext=prev_pt,
                    arrowprops=dict(arrowstyle="->", color="red",
                                    lw=1.5, alpha=0.6))
        # Step number near component, offset to not overlap
        off_x = 2.5 if pt[0] < BOARD_W / 2 else -2.5
        off_y = 2.5 if pt[1] > BOARD_H / 2 else -2.5
        ax.text(pt[0] + off_x, pt[1] + off_y, str(i + 1),
                fontsize=7, color="white", weight="bold",
                bbox=dict(boxstyle="circle,pad=0.15", facecolor="red",
                          edgecolor="darkred", alpha=0.8))
        prev_pt = pt

        # Return arrow (except last)
        if i < n - 1:
            ax.annotate("", xy=FEEDER, xytext=pt,
                        arrowprops=dict(arrowstyle="->", color="#888",
                                        lw=1, alpha=0.4, linestyle="dashed"))

    # Legend
    leg_elements = [
        mpatches.Patch(color=c, label=l)
        for c, l in [("#e74c3c", "IC (U1)"), ("#9b59b6", "Display"),
                     ("#3498db", "Connector"), ("#2ecc71", "Resistor"),
                     ("#e67e22", "Switch")]
    ]
    leg_elements.append(plt.Line2D([0], [0], color="red", lw=1.5,
                                   label="Travel path"))
    leg_elements.append(plt.Line2D([0], [0], color="#888", lw=1, ls="--",
                                   label="Return path"))
    ax.legend(handles=leg_elements, loc="lower left", fontsize=7)

    # ── Right panel: Stats + Optimization ──
    ax2 = fig.add_subplot(gs[1])
    ax2.axis("off")
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)

    # Title
    ax2.text(0.5, 0.98, "TRAJECTORY ANALYSIS", ha="center", fontsize=14,
             weight="bold", transform=ax2.transAxes)
    ax2.text(0.5, 0.94, f"Fuji AIMEX III  |  {n} components  |  "
             f"Board {BOARD_W}x{BOARD_H}mm",
             ha="center", fontsize=9, color="#555", transform=ax2.transAxes)

    y = 0.88

    # Distance breakdown
    ax2.text(0.05, y, "DISTANCE", fontsize=11, weight="bold",
             transform=ax2.transAxes)
    y -= 0.04
    for label, key in [("Feed → Board", "feed2board_mm"),
                       ("Board → Feed", "board2feed_mm"),
                       ("Total travel", "total_distance_mm")]:
        val = stats[key]
        ax2.text(0.1, y, f"{label}:  {val:.1f} mm", fontsize=9,
                 transform=ax2.transAxes)
        y -= 0.035

    # Timing
    y -= 0.02
    ax2.text(0.05, y, "TIMING", fontsize=11, weight="bold",
             transform=ax2.transAxes)
    y -= 0.04
    for label, key in [("Travel time", "travel_time_s"),
                       ("Pick+Place time", "pick_place_time_s"),
                       ("Total cycle", "total_cycle_s")]:
        val = stats[key]
        ax2.text(0.1, y, f"{label}:  {val:.1f} s",
                 fontsize=9, transform=ax2.transAxes)
        y -= 0.035

    cph = stats["placements_per_hour"]
    ax2.text(0.1, y, f"Throughput:  {cph:.0f} placements/hr",
             fontsize=9, weight="bold", transform=ax2.transAxes)
    y -= 0.05

    # Sequence table (first N / last N)
    y -= 0.01
    ax2.text(0.05, y, "PLACEMENT SEQUENCE (top 15)", fontsize=11,
             weight="bold", transform=ax2.transAxes)
    y -= 0.04

    # Table header
    cols = ["#", "Ref", "Type", "X", "Y", "Dist\n(mm)"]
    col_x = [0.05, 0.12, 0.22, 0.32, 0.42, 0.52]
    for ci, (cx, col) in enumerate(zip(col_x, cols)):
        ax2.text(cx, y, col, fontsize=7, weight="bold", va="bottom",
                 transform=ax2.transAxes)
    y -= 0.03

    for i, pc in enumerate(stats["per_component"][:15]):
        vals = [str(i + 1), pc["ref"],
                pc["type"][:4],
                f"{pc['x']:.1f}", f"{pc['y']:.1f}",
                f"{pc['dist_feed2board']:.1f}"]
        for cx, val in zip(col_x, vals):
            ax2.text(cx, y, val, fontsize=6, va="top",
                     transform=ax2.transAxes)
        y -= 0.028

    # Optimization box
    if n > 1:
        y -= 0.03
        rect = mpatches.FancyBboxPatch((0.03, y - 0.22), 0.94, 0.22,
                                        boxstyle="round,pad=0.03",
                                        facecolor="#e8f8e8",
                                        edgecolor="#27ae60", lw=1.5,
                                        transform=ax2.transAxes)
        ax2.add_patch(rect)
        box_y = y
        ax2.text(0.5, box_y + 0.01, "OPTIMIZATION (Nearest-Neighbor)",
                 ha="center", fontsize=10, weight="bold",
                 transform=ax2.transAxes, color="#27ae60")
        box_y -= 0.04

        orig_dist = stats["total_distance_mm"]
        opt_dist = opt_stats["total_distance_mm"]
        saved = orig_dist - opt_dist
        saved_pct = (saved / orig_dist * 100) if orig_dist > 0 else 0

        ax2.text(0.1, box_y, f"Original distance:  {orig_dist:.0f} mm",
                 fontsize=8, transform=ax2.transAxes)
        box_y -= 0.03
        ax2.text(0.1, box_y, f"Optimized distance: {opt_dist:.0f} mm",
                 fontsize=8, transform=ax2.transAxes)
        box_y -= 0.03
        ax2.text(0.1, box_y, f"Saving:  {saved:.0f} mm  ({saved_pct:.1f}%)",
                 fontsize=8, weight="bold",
                 transform=ax2.transAxes, color="#27ae60")
        box_y -= 0.03
        ax2.text(0.1, box_y, f"Est. cycle improvement:  "
                 f"{stats['total_cycle_s'] - opt_stats['total_cycle_s']:.1f} s",
                 fontsize=8, transform=ax2.transAxes)

    if save_path:
        print(f"Saving analysis to {save_path} ...")
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print("Done.")
    else:
        plt.show()

    plt.close(fig)


# ─── Optimized path overlay PNG ──────────────────────────────

def plot_optimization_overlay(comps, save_path=None):
    """Side-by-side comparison of original vs optimized path."""
    if len(comps) < 3:
        print("Too few components for optimization overlay.")
        return

    opt = optimize_sequence(comps)
    orig_stats = trajectory_stats(comps)
    opt_stats = trajectory_stats(opt)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    for ax, c_list, title, stats in [
        (ax1, comps, f"ORIGINAL Sequence  ({orig_stats['total_distance_mm']:.0f} mm)",
         orig_stats),
        (ax2, opt, f"OPTIMIZED Sequence ({opt_stats['total_distance_mm']:.0f} mm)",
         opt_stats)
    ]:
        ax.set_xlim(-5, BOARD_W + 5)
        ax.set_ylim(-10, BOARD_H + 5)
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=12, weight="bold")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")

        bg = load_pcb_background()
        if bg:
            bg_im, bg_extent = bg
            ax.imshow(bg_im, extent=bg_extent, origin="lower", zorder=0,
                      alpha=0.85)
        board = mpatches.Rectangle((0, 0), BOARD_W, BOARD_H,
                                   linewidth=2, edgecolor="black",
                                   facecolor="none", zorder=1)
        ax.add_patch(board)
        ax.plot(FEEDER[0], FEEDER[1], marker="v", color="#cc7700",
                markersize=10, zorder=5)
        ax.text(FEEDER[0], FEEDER[1] - 3, "Feeder", ha="center",
                fontsize=7, color="#cc7700")

        # Components
        for i, c in enumerate(c_list):
            pt = comp_pos(c)
            color = COLORS_PLOT.get(comp_type(c["ref"]))
            ax.scatter(pt[0], pt[1], c=color, s=100, alpha=0.8,
                       edgecolors="black", linewidth=0.5, zorder=4)
            ax.annotate(c["ref"], (pt[0], pt[1]), fontsize=6,
                        ha="center", va="bottom")

        # Path
        prev = FEEDER
        for i, c in enumerate(c_list):
            pt = comp_pos(c)
            ax.annotate("", xy=pt, xytext=prev,
                        arrowprops=dict(arrowstyle="->", color="red",
                                        lw=1.5, alpha=0.5))
            # Step number
            mid = ((prev[0] + pt[0]) / 2, (prev[1] + pt[1]) / 2)
            ax.text(mid[0], mid[1], str(i + 1), fontsize=6, color="red",
                    ha="center", va="bottom", alpha=0.7, weight="bold")
            prev = pt
            if i < len(c_list) - 1:
                ax.annotate("", xy=FEEDER, xytext=pt,
                            arrowprops=dict(arrowstyle="->", color="#bbb",
                                            lw=1, alpha=0.4, ls="dashed"))

    plt.tight_layout()

    if save_path:
        print(f"Saving optimization overlay to {save_path} ...")
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print("Done.")
    else:
        plt.show()

    plt.close(fig)


# ─── Animation ───────────────────────────────────────────────

def animate_trajectory(comps, save_path=None):
    """Smooth animated trajectory with stats overlay."""
    n = len(comps)

    # Build frame data (same as visualize_pnp.py)
    TRAVEL_STEPS = 6
    DWELL_STEPS = 2
    frame_data = []

    for i, c in enumerate(comps):
        target = comp_pos(c)
        start = FEEDER

        for t in range(TRAVEL_STEPS):
            frac = (t + 1) / TRAVEL_STEPS
            frame_data.append({
                "x": start[0] + (target[0] - start[0]) * frac,
                "y": start[1] + (target[1] - start[1]) * frac,
                "comp_idx": i, "placed": None,
                "label": f"Move to step {i + 1}/{n}: {c['ref']}"
            })

        for t in range(DWELL_STEPS):
            frame_data.append({
                "x": target[0], "y": target[1],
                "comp_idx": i, "placed": i,
                "label": f"Place step {i + 1}/{n}: {c['ref']} ({c['val']})"
            })

        if i < n - 1:
            for t in range(TRAVEL_STEPS):
                frac = (t + 1) / TRAVEL_STEPS
                frame_data.append({
                    "x": target[0] + (FEEDER[0] - target[0]) * frac,
                    "y": target[1] + (FEEDER[1] - target[1]) * frac,
                    "comp_idx": i, "placed": i,
                    "label": f"Return for step {i + 2}/{n}: {comps[i + 1]['ref']}"
                })

    last = comps[-1]
    frame_data.append({
        "x": comp_pos(last)[0], "y": comp_pos(last)[1],
        "comp_idx": n - 1, "placed": n - 1,
        "label": f"ALL {n} COMPONENTS PLACED"
    })

    total_frames = len(frame_data)
    stats = trajectory_stats(comps)

    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_xlim(-5, BOARD_W + 5)
    ax.set_ylim(-10, BOARD_H + 5)
    ax.set_aspect("equal")
    ax.set_title("Fuji AIMEX III  —  Pick & Place Head Travel", fontsize=14,
                 weight="bold")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")

    # Board + feeder
    bg = load_pcb_background()
    if bg:
        bg_im, bg_extent = bg
        ax.imshow(bg_im, extent=bg_extent, origin="lower", zorder=0,
                  alpha=0.85)
    board = mpatches.Rectangle((0, 0), BOARD_W, BOARD_H,
                               linewidth=2, edgecolor="black",
                               facecolor="none", zorder=1)
    ax.add_patch(board)
    feeder_rect = mpatches.Rectangle((-4, -14), BOARD_W + 8, 8,
                                     linewidth=1, edgecolor="#888",
                                     facecolor="#fff3cd", alpha=0.5)
    ax.add_patch(feeder_rect)
    ax.text(FEEDER[0], FEEDER[1] - 3, "FEEDER", ha="center", fontsize=9,
            color="#666", weight="bold")
    ax.plot(FEEDER[0], FEEDER[1], marker="v", color="#cc7700",
            markersize=14, zorder=5)

    # ── Static: step numbers + path arrows + component dots ──
    placed_dots = []
    unplaced_dots = []
    prev_pt = FEEDER
    for i, c in enumerate(comps):
        pt = comp_pos(c)
        color = COLORS_PLOT.get(comp_type(c["ref"]))

        # Path arrow from previous stop to this component
        ax.annotate("", xy=pt, xytext=prev_pt,
                    arrowprops=dict(arrowstyle="->", color="#bbb",
                                    lw=1, alpha=0.5))

        # Step number in circle near component
        off_x = 2.5 if pt[0] < BOARD_W / 2 else -2.5
        off_y = 2.5 if pt[1] > BOARD_H / 2 else -2.5
        ax.text(pt[0] + off_x, pt[1] + off_y, str(i + 1),
                fontsize=7, color="white", weight="bold",
                bbox=dict(boxstyle="circle,pad=0.15", facecolor="red",
                          edgecolor="darkred", alpha=0.8))

        # Component dot
        size = 180 if c["ref"].startswith("U") else 100
        su = ax.scatter(pt[0], pt[1], c=color, s=size, alpha=0.15,
                        edgecolors="black", linewidth=0.5, zorder=3)
        unplaced_dots.append(su)
        sp = ax.scatter(pt[0], pt[1], c=color, s=size * 1.3,
                        alpha=0.95, edgecolors="black", linewidth=1,
                        zorder=3, visible=False)
        placed_dots.append(sp)
        ax.annotate(c["ref"], (pt[0], pt[1] + 3.5), fontsize=6,
                    ha="center", va="bottom")

        prev_pt = pt
        if i < n - 1:
            ax.annotate("", xy=FEEDER, xytext=pt,
                        arrowprops=dict(arrowstyle="->", color="#ddd",
                                        lw=1, alpha=0.3, linestyle="dashed"))

    # Legend
    leg_elements = [
        mpatches.Patch(color=c, label=l)
        for c, l in [("#e74c3c", "IC"), ("#9b59b6", "Display"),
                     ("#3498db", "Connector"), ("#2ecc71", "Resistor"),
                     ("#e67e22", "Switch")]
    ]
    leg_elements.append(plt.Line2D([0], [0], color="red", lw=2, label="Head trail"))
    ax.legend(handles=leg_elements, loc="lower left", fontsize=7)

    # ── Animated overlay ──
    (head_dot,) = ax.plot([], [], "o", color="#ff2200", markersize=18,
                          markeredgecolor="black", markeredgewidth=2.5, zorder=8)
    (head_glow,) = ax.plot([], [], "o", color="#ff8800", markersize=28,
                           alpha=0.35, zorder=7)
    (trail_line,) = ax.plot([], [], "r-", linewidth=3, alpha=0.8, zorder=5)
    (target_line,) = ax.plot([], [], "r--", linewidth=1.5, alpha=0.5, zorder=4)

    # Placement burst
    burst_ring = mpatches.Circle((0, 0), 0, fill=False,
                                  edgecolor="#ffcc00", linewidth=3, alpha=0,
                                  zorder=9)
    ax.add_patch(burst_ring)
    (impact_cross,) = ax.plot([], [], "w+", markersize=20, alpha=0,
                               markeredgewidth=2.5, zorder=9)

    # Value labels that appear on placement
    val_labels = []
    for i, c in enumerate(comps):
        pt = comp_pos(c)
        t = ax.text(pt[0], pt[1] - 4.5, c["val"],
                     fontsize=5, ha="center", va="top",
                     color="#333", alpha=0, zorder=4)
        val_labels.append(t)
    # Info panel (bottom strip)
    label_text = ax.text(0.02, -7.5, "", fontsize=9,
                         transform=ax.transData)
    progress_text = ax.text(BOARD_W - 0.02, -7.5, "",
                            fontsize=9, ha="right", transform=ax.transData)
    stats_text = ax.text(0.02, -9, "", fontsize=8,
                         color="#444", transform=ax.transData)

    # Progress bar
    bar_ax = fig.add_axes([0.12, 0.04, 0.76, 0.025])
    bar_ax.set_xlim(0, 1)
    bar_ax.set_ylim(0, 1)
    bar_ax.axis("off")
    bar_ax.add_patch(mpatches.Rectangle((0, 0.2), 1, 0.6,
                                         facecolor="#ddd", edgecolor="none"))
    bar_fill = mpatches.Rectangle((0, 0.2), 0, 0.6,
                                   facecolor="#e74c3c", edgecolor="none")
    bar_ax.add_patch(bar_fill)

    all_artists = [trail_line, head_dot, head_glow, target_line,
                   label_text, progress_text, stats_text, bar_fill,
                   burst_ring, impact_cross] + val_labels

    trail_x, trail_y = [], []
    last_placed = -1  # track last placed component index for burst effect
    burst_frame = 0   # countdown for burst animation

    def init():
        trail_x.clear()
        trail_y.clear()
        trail_line.set_data([], [])
        head_dot.set_data([], [])
        head_glow.set_data([], [])
        target_line.set_data([], [])
        label_text.set_text("")
        progress_text.set_text("")
        stats_text.set_text("")
        bar_fill.set_width(0)
        burst_ring.set_center((0, 0))
        burst_ring.set_radius(0)
        burst_ring.set_alpha(0)
        impact_cross.set_data([], [])
        impact_cross.set_alpha(0)
        for sp in placed_dots:
            sp.set_visible(False)
        for vt in val_labels:
            vt.set_alpha(0)
        nonlocal last_placed, burst_frame
        last_placed = -1
        burst_frame = 0
        return all_artists + placed_dots + unplaced_dots

    def animate(frame_idx):
        nonlocal last_placed, burst_frame
        fd = frame_data[frame_idx]
        hx, hy = fd["x"], fd["y"]
        head_dot.set_data([hx], [hy])
        head_glow.set_data([hx], [hy])

        trail_x.append(hx)
        trail_y.append(hy)
        trail_line.set_data(trail_x, trail_y)

        ci = fd["comp_idx"]
        c = comps[ci]
        ct = comp_pos(c)
        target_line.set_data([hx, ct[0]], [hy, ct[1]])

        placed_up_to = fd["placed"]
        for i in range(n):
            if placed_up_to is not None and i <= placed_up_to:
                placed_dots[i].set_visible(True)
                unplaced_dots[i].set_alpha(0.15)
            else:
                placed_dots[i].set_visible(False)
                unplaced_dots[i].set_alpha(0.15)

        # ── "Printing" burst effect ──
        if placed_up_to is not None and placed_up_to > last_placed:
            # Freshly placed — start burst
            last_placed = placed_up_to
            burst_frame = DWELL_STEPS
            impact_cross.set_data([ct[0]], [ct[1]])
            impact_cross.set_alpha(1)
            # Show value label
            val_labels[placed_up_to].set_alpha(0.9)

        if burst_frame > 0:
            # Expanding ring + fading cross
            t = burst_frame / DWELL_STEPS
            r = 2 + 6 * (1 - t)  # radius shrinks from 8 to 2
            a = 0.6 * t          # alpha fades from 0.6 to 0
            burst_ring.set_center(ct)
            burst_ring.set_radius(r)
            burst_ring.set_alpha(a)
            impact_cross.set_alpha(t)
            burst_frame -= 1
        else:
            burst_ring.set_alpha(0)
            impact_cross.set_alpha(0)

        label_text.set_text(f"{fd['label']}")
        progress_text.set_text(
            f"Frame {frame_idx + 1}/{total_frames}  |  "
            f"Dist: {stats['total_distance_mm']:.0f} mm  |  "
            f"Cycle: {stats['total_cycle_s']:.1f}s"
        )
        stats_text.set_text(
            f"Head speed: {HEAD_SPEED_MM_S} mm/s  |  "
            f"Pick/Place: {PICK_TIME_S}/{PLACE_TIME_S}s  |  "
            f"Throughput: {stats['placements_per_hour']:.0f} pph"
        )

        bar_fill.set_width((frame_idx + 1) / total_frames)

        return all_artists + placed_dots + unplaced_dots

    use_blit = save_path is None
    ani = animation.FuncAnimation(
        fig, animate, frames=total_frames,
        init_func=init, interval=80, repeat=use_blit, blit=use_blit
    )

    if save_path:
        print(f"Saving animation ({total_frames} frames) to {save_path} ...")
        ani.save(save_path, writer="pillow", fps=8, dpi=80)
        print("Done.")
    else:
        plt.show()

    plt.close(fig)
    return ani


# ─── Animated analysis view (GIF) ────────────────────────────
# Combines the full layout from plot_analysis with head animation.

def animate_analysis_view(comps, save_path=None):
    """Animated version of the analysis view: PCB map + stats panel + head travel."""
    n = len(comps)
    stats = trajectory_stats(comps)
    opt_comps = optimize_sequence(comps)
    opt_stats = trajectory_stats(opt_comps)

    # ── Build frame data (same as animate_trajectory) ──
    TRAVEL = 6
    DWELL = 2
    frame_data = []
    for i, c in enumerate(comps):
        target = comp_pos(c)
        for t in range(TRAVEL):
            frac = (t + 1) / TRAVEL
            frame_data.append({
                "x": FEEDER[0] + (target[0] - FEEDER[0]) * frac,
                "y": FEEDER[1] + (target[1] - FEEDER[1]) * frac,
                "comp_idx": i, "placed": None,
            })
        for _ in range(DWELL):
            frame_data.append({
                "x": target[0], "y": target[1],
                "comp_idx": i, "placed": i,
            })
        if i < n - 1:
            for t in range(TRAVEL):
                frac = (t + 1) / TRAVEL
                frame_data.append({
                    "x": target[0] + (FEEDER[0] - target[0]) * frac,
                    "y": target[1] + (FEEDER[1] - target[1]) * frac,
                    "comp_idx": i, "placed": i,
                })
    frame_data.append({
        "x": comp_pos(comps[-1])[0], "y": comp_pos(comps[-1])[1],
        "comp_idx": n - 1, "placed": n - 1,
    })

    total_frames = len(frame_data)

    # ── Figure layout (same as plot_analysis) ──
    fig = plt.figure(figsize=(18, 10), constrained_layout=False)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.6, 1], wspace=0.3)

    # ── LEFT: PCB path map ──
    ax = fig.add_subplot(gs[0])
    ax.set_xlim(-5, BOARD_W + 5)
    ax.set_ylim(-10, BOARD_H + 5)
    ax.set_aspect("equal")
    ax.set_title("Placement Path & Sequence  (head traveling\u2026)", fontsize=14,
                 weight="bold")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")

    # PCB background (actual board image from KiCad)
    bg = load_pcb_background()
    if bg:
        bg_im, bg_extent = bg
        ax.imshow(bg_im, extent=bg_extent, origin="lower", zorder=0,
                  alpha=0.85)
    board = mpatches.Rectangle((0, 0), BOARD_W, BOARD_H,
                               linewidth=2, edgecolor="black",
                               facecolor="none", zorder=1)
    ax.add_patch(board)

    # Feeder (below board)
    feeder_rect = mpatches.Rectangle((-4, -14), BOARD_W + 8, 8,
                                     linewidth=1, edgecolor="#888",
                                     facecolor="#fff3cd", alpha=0.5)
    ax.add_patch(feeder_rect)
    ax.text(FEEDER[0], FEEDER[1] - 3, "FEEDER", ha="center", fontsize=9,
            color="#666", weight="bold")
    ax.plot(FEEDER[0], FEEDER[1], marker="v", color="#cc7700",
            markersize=14, zorder=5)

    # Components + step numbers + path arrows (static)
    for i, c in enumerate(comps):
        pt = comp_pos(c)
        color = COLORS_PLOT.get(comp_type(c["ref"]))
        size = 180 if c["ref"].startswith("U") else 100
        ax.scatter(pt[0], pt[1], c=color, s=size, alpha=0.8,
                   edgecolors="black", linewidth=0.5, zorder=4)
        ax.annotate(c["ref"], (pt[0], pt[1] + 3.5), fontsize=6,
                    ha="center", va="bottom")

    # Step numbers in circles (offset from component) + store for highlighting
    step_boxes = []
    prev_pt = FEEDER
    for i, c in enumerate(comps):
        pt = comp_pos(c)
        ax.annotate("", xy=pt, xytext=prev_pt,
                    arrowprops=dict(arrowstyle="->", color="#ccc",
                                    lw=1, alpha=0.5))
        off_x = 2.5 if pt[0] < BOARD_W / 2 else -2.5
        off_y = 2.5 if pt[1] > BOARD_H / 2 else -2.5
        bbox_props = dict(boxstyle="circle,pad=0.15", facecolor="red",
                          edgecolor="darkred", alpha=0.8)
        tb = ax.text(pt[0] + off_x, pt[1] + off_y, str(i + 1),
                     fontsize=7, color="white", weight="bold", bbox=bbox_props)
        step_boxes.append(tb)
        prev_pt = pt
        if i < n - 1:
            ax.annotate("", xy=FEEDER, xytext=pt,
                        arrowprops=dict(arrowstyle="->", color="#ddd",
                                        lw=1, alpha=0.3, linestyle="dashed"))

    # Legend
    leg_elements = [
        mpatches.Patch(color=c, label=l)
        for c, l in [("#e74c3c", "IC (U1)"), ("#9b59b6", "Display"),
                     ("#3498db", "Connector"), ("#2ecc71", "Resistor"),
                     ("#e67e22", "Switch")]
    ]
    leg_elements.append(plt.Line2D([0], [0], color="red", lw=2, label="Head trail"))
    ax.legend(handles=leg_elements, loc="lower left", fontsize=7)

    # ── Animated overlays on PCB ──
    # Head: very large bright dot with white core + red glow
    (head_dot,) = ax.plot([], [], "o", color="white", markersize=22,
                          markeredgecolor="#ff0000", markeredgewidth=5,
                          zorder=10)
    (head_glow,) = ax.plot([], [], "o", color="#ff0000", markersize=48,
                           alpha=0.7, zorder=9)
    (head_halo,) = ax.plot([], [], "o", color="#ff4400", markersize=70,
                           alpha=0.35, zorder=8)
    # Head label (diamond)
    (head_label,) = ax.plot([], [], "D", color="#00ffaa", markersize=12,
                             markeredgecolor="#00ffaa", zorder=11)

    # Trail: thick bright line
    (trail_line,) = ax.plot([], [], "-", color="#ff2200", linewidth=3.5,
                            alpha=0.85, zorder=7)

    # Dashed line from head to target
    (target_line,) = ax.plot([], [], "--", color="#ff6600", linewidth=2,
                             alpha=0.7, zorder=6)

    # Placement burst (green expanding ring)
    burst_ring = mpatches.Circle((0, 0), 0, fill=False,
                                  edgecolor="#00ff88", linewidth=5, alpha=0,
                                  zorder=11)
    ax.add_patch(burst_ring)
    (impact_cross,) = ax.plot([], [], "w+", markersize=28, alpha=0,
                               markeredgewidth=3.5, zorder=11)
    (impact_sparkle1,) = ax.plot([], [], "o", color="#ffff00", markersize=8,
                                  alpha=0, zorder=11)
    (impact_sparkle2,) = ax.plot([], [], "o", color="#00ffff", markersize=6,
                                  alpha=0, zorder=11)

    # Value labels that appear on placement
    val_labels = []
    for i, c in enumerate(comps):
        pt = comp_pos(c)
        t = ax.text(pt[0], pt[1] - 4.5, c["val"],
                     fontsize=6, ha="center", va="top",
                     color="#222", weight="bold", alpha=0, zorder=5)
        val_labels.append(t)

    # ── RIGHT: Stats panel ──
    ax2 = fig.add_subplot(gs[1])
    ax2.axis("off")
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)

    y = 0.98
    ax2.text(0.5, y, "TRAJECTORY ANALYSIS", ha="center", fontsize=14,
             weight="bold", transform=ax2.transAxes)
    y -= 0.04
    ax2.text(0.5, y, f"Fuji AIMEX III  |  {n} components  |  "
             f"Board {BOARD_W}x{BOARD_H}mm",
             ha="center", fontsize=9, color="#555", transform=ax2.transAxes)
    y -= 0.05

    # Live status
    ax2.text(0.05, y, "LIVE STATUS", fontsize=11, weight="bold",
             transform=ax2.transAxes)
    y -= 0.04
    current_step_txt = ax2.text(0.1, y, "Step: 0 / 0", fontsize=9,
                                transform=ax2.transAxes)
    y -= 0.03
    placed_txt = ax2.text(0.1, y, "Placed: 0", fontsize=9,
                          transform=ax2.transAxes, color="#27ae60")
    y -= 0.03
    head_pos_txt = ax2.text(0.1, y, "Head: (--, --)", fontsize=9,
                            transform=ax2.transAxes)
    y -= 0.05

    # Distance
    ax2.text(0.05, y, "DISTANCE", fontsize=11, weight="bold",
             transform=ax2.transAxes)
    y -= 0.04
    for label, key in [("Feed \u2192 Board", "feed2board_mm"),
                       ("Board \u2192 Feed", "board2feed_mm"),
                       ("Total travel", "total_distance_mm")]:
        val = stats[key]
        ax2.text(0.1, y, f"{label}:  {val:.1f} mm", fontsize=9,
                 transform=ax2.transAxes)
        y -= 0.035

    y -= 0.02
    ax2.text(0.05, y, "TIMING", fontsize=11, weight="bold",
             transform=ax2.transAxes)
    y -= 0.04
    for label, key in [("Travel", "travel_time_s"),
                       ("Pick+Place", "pick_place_time_s"),
                       ("Total cycle", "total_cycle_s")]:
        val = stats[key]
        ax2.text(0.1, y, f"{label}:  {val:.1f} s", fontsize=9,
                 transform=ax2.transAxes)
        y -= 0.035
    cph = stats["placements_per_hour"]
    ax2.text(0.1, y, f"Throughput:  {cph:.0f} placements/hr", fontsize=9,
             weight="bold", transform=ax2.transAxes)
    y -= 0.06

    # Optimization
    if n > 1:
        rect = mpatches.FancyBboxPatch((0.03, y - 0.16), 0.94, 0.16,
                                        boxstyle="round,pad=0.03",
                                        facecolor="#e8f8e8",
                                        edgecolor="#27ae60", lw=1.5,
                                        transform=ax2.transAxes)
        ax2.add_patch(rect)
        orig_dist = stats["total_distance_mm"]
        opt_dist_val = opt_stats["total_distance_mm"]
        saved = orig_dist - opt_dist_val
        saved_pct = (saved / orig_dist * 100) if orig_dist > 0 else 0
        ax2.text(0.5, y + 0.01, "OPTIMIZATION (Nearest-Neighbor)",
                 ha="center", fontsize=10, weight="bold",
                 transform=ax2.transAxes, color="#27ae60")
        ax2.text(0.1, y - 0.03,
                 f"Original: {orig_dist:.0f} mm  |  "
                 f"Optimized: {opt_dist_val:.0f} mm",
                 fontsize=8, transform=ax2.transAxes)
        ax2.text(0.1, y - 0.06,
                 f"Saving: {saved:.0f} mm ({saved_pct:.1f}%)",
                 fontsize=8, weight="bold",
                 transform=ax2.transAxes, color="#27ae60")

    # ── Progress bar (below PCB) ──
    bar_ax = fig.add_axes([0.12, 0.04, 0.76, 0.025])
    bar_ax.set_xlim(0, 1)
    bar_ax.set_ylim(0, 1)
    bar_ax.axis("off")
    bar_ax.add_patch(mpatches.Rectangle((0, 0.2), 1, 0.6,
                                         facecolor="#ddd", edgecolor="none"))
    bar_fill = mpatches.Rectangle((0, 0.2), 0, 0.6,
                                   facecolor="#e74c3c", edgecolor="none")
    bar_ax.add_patch(bar_fill)

    all_artists = [head_dot, head_glow, head_halo, head_label, trail_line,
                   target_line, burst_ring, impact_cross,
                   impact_sparkle1, impact_sparkle2,
                   current_step_txt, placed_txt, head_pos_txt,
                   bar_fill] + val_labels + step_boxes

    trail_x, trail_y = [], []
    last_placed = -1
    burst_ct = 0

    def init():
        trail_x.clear()
        trail_y.clear()
        head_dot.set_data([], [])
        head_glow.set_data([], [])
        head_halo.set_data([], [])
        head_label.set_data([], [])
        trail_line.set_data([], [])
        target_line.set_data([], [])
        burst_ring.set_center((0, 0))
        burst_ring.set_radius(0)
        burst_ring.set_alpha(0)
        impact_cross.set_data([], [])
        impact_cross.set_alpha(0)
        impact_sparkle1.set_data([], [])
        impact_sparkle1.set_alpha(0)
        impact_sparkle2.set_data([], [])
        impact_sparkle2.set_alpha(0)
        current_step_txt.set_text("Step: 0 / 0")
        placed_txt.set_text("Placed: 0")
        head_pos_txt.set_text("Head: (--, --)")
        bar_fill.set_width(0)
        for vt in val_labels:
            vt.set_alpha(0)
        # Reset step box colors
        for tb in step_boxes:
            tb.set_bbox(dict(boxstyle="circle,pad=0.15", facecolor="red",
                             edgecolor="darkred", alpha=0.8))
        nonlocal last_placed, burst_ct
        last_placed = -1
        burst_ct = 0
        return all_artists

    def animate(frame_idx):
        nonlocal last_placed, burst_ct
        fd = frame_data[frame_idx]
        hx, hy = fd["x"], fd["y"]

        head_dot.set_data([hx], [hy])
        head_glow.set_data([hx], [hy])
        # Pulse the head for visibility
        pulse = 0.75 + 0.25 * math.sin(frame_idx * 0.25)
        head_halo.set_data([hx], [hy])
        head_halo.set_markersize(70 * pulse)
        head_glow.set_markersize(48 * (0.9 + 0.1 * math.sin(frame_idx * 0.35)))
        head_dot.set_markersize(22 * (0.9 + 0.1 * math.sin(frame_idx * 0.4)))
        head_label.set_data([hx], [hy])
        trail_x.append(hx)
        trail_y.append(hy)
        trail_line.set_data(trail_x, trail_y)

        ci = fd["comp_idx"]
        c = comps[ci]
        ct = comp_pos(c)
        target_line.set_data([hx, ct[0]], [hy, ct[1]])
        target_line.set_color("#ff6600")
        target_line.set_alpha(0.4 + 0.3 * math.sin(frame_idx * 0.2))
        target_line.set_linewidth(2 + 0.5 * math.sin(frame_idx * 0.3))

        # Highlight current step number
        for i, tb in enumerate(step_boxes):
            if i == ci:
                tb.set_bbox(dict(boxstyle="circle,pad=0.18", facecolor="#ff8800",
                                 edgecolor="gold", alpha=1.0))
            else:
                tb.set_bbox(dict(boxstyle="circle,pad=0.15", facecolor="red",
                                 edgecolor="darkred", alpha=0.8))

        # ── "Printing" burst ──
        placed_up_to = fd["placed"]
        if placed_up_to is not None and placed_up_to > last_placed:
            last_placed = placed_up_to
            burst_ct = DWELL
            impact_cross.set_data([ct[0]], [ct[1]])
            impact_cross.set_alpha(1)
            impact_sparkle1.set_data([ct[0] + 3], [ct[1] + 3])
            impact_sparkle1.set_alpha(1)
            impact_sparkle2.set_data([ct[0] - 3], [ct[1] - 3])
            impact_sparkle2.set_alpha(1)
            val_labels[placed_up_to].set_alpha(0.9)

        if burst_ct > 0:
            t = burst_ct / DWELL
            burst_ring.set_center(ct)
            burst_ring.set_radius(2 + 8 * (1 - t))
            burst_ring.set_alpha(0.7 * t)
            impact_cross.set_alpha(t * 0.8)
            impact_sparkle1.set_alpha(t * 0.6)
            impact_sparkle2.set_alpha(t * 0.6)
            burst_ct -= 1
        else:
            burst_ring.set_alpha(0)
            impact_cross.set_alpha(0)
            impact_sparkle1.set_alpha(0)
            impact_sparkle2.set_alpha(0)

        # ── Update stats panel ──
        step = (placed_up_to + 1) if placed_up_to is not None else 0
        current_step_txt.set_text(f"Step: {step} / {n}")
        placed_txt.set_text(f"Placed: {step}")
        head_pos_txt.set_text(f"Head: ({hx:.1f}, {hy:.1f}) mm")

        bar_fill.set_width((frame_idx + 1) / total_frames)

        return all_artists

    use_blit = save_path is None
    ani = animation.FuncAnimation(
        fig, animate, frames=total_frames,
        init_func=init, interval=80, repeat=use_blit, blit=use_blit
    )

    if save_path:
        print(f"Saving animated analysis ({total_frames} frames) to {save_path} ...")
        ani.save(save_path, writer="pillow", fps=8, dpi=80)
        print("Done.")
    else:
        plt.show()

    plt.close(fig)
    return ani


# ─── Console report ──────────────────────────────────────────

def print_report(comps):
    stats = trajectory_stats(comps)
    opt = optimize_sequence(comps)
    opt_stats = trajectory_stats(opt)

    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  SMT PICK-&-PLACE TRAJECTORY ANALYSIS")
    print(f"  Fuji AIMEX III  |  {len(comps)} components")
    print(f"  Board: {BOARD_W} x {BOARD_H} mm")
    print(f"{sep}")

    print(f"\n── DISTANCE ──")
    print(f"  Feed → Board:     {stats['feed2board_mm']:>8.1f} mm")
    print(f"  Board → Feed:     {stats['board2feed_mm']:>8.1f} mm")
    print(f"  Total travel:     {stats['total_distance_mm']:>8.1f} mm")
    print(f"  Avg per comp:     {stats['total_distance_mm'] / len(comps):>8.1f} mm")

    print(f"\n── TIMING (at {HEAD_SPEED_MM_S} mm/s) ──")
    print(f"  Travel time:      {stats['travel_time_s']:>8.1f} s")
    print(f"  Pick+Place time:  {stats['pick_place_time_s']:>8.1f} s")
    print(f"  Total cycle:      {stats['total_cycle_s']:>8.1f} s")
    print(f"  Throughput:       {stats['placements_per_hour']:>8.0f} pph")

    print(f"\n── SEQUENCE ──")
    print(f"  {'Step':>4} {'Ref':<8} {'Type':<12} {'X(mm)':>8} {'Y(mm)':>8} "
          f"{'Dist(mm)':>8}")
    print(f"  {'-'*4} {'-'*8} {'-'*12} {'-'*8} {'-'*8} {'-'*8}")
    for i, pc in enumerate(stats["per_component"]):
        print(f"  {i + 1:>4} {pc['ref']:<8} {pc['type']:<12} "
              f"{pc['x']:>8.1f} {pc['y']:>8.1f} {pc['dist_feed2board']:>8.1f}")

    if len(comps) > 1:
        orig_dist = stats["total_distance_mm"]
        opt_dist = opt_stats["total_distance_mm"]
        saved = orig_dist - opt_dist
        saved_pct = (saved / orig_dist * 100) if orig_dist > 0 else 0
        saved_time = stats["total_cycle_s"] - opt_stats["total_cycle_s"]

        print(f"\n── OPTIMIZATION (Nearest-Neighbor) ──")
        print(f"  Original:   {orig_dist:>8.0f} mm  {stats['total_cycle_s']:>5.1f} s")
        print(f"  Optimized:  {opt_dist:>8.0f} mm  {opt_stats['total_cycle_s']:>5.1f} s")
        print(f"  Saving:     {saved:>8.0f} mm ({saved_pct:.1f}%)  "
              f"{saved_time:.1f} s")
        print(f"\n  Optimized order: {' → '.join(c['ref'] for c in opt)}")

    print(f"\n{sep}\n")


# ─── Main ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SMT Pick-and-Place Trajectory Analyzer"
    )
    parser.add_argument("--view", action="store_true",
                        help="Generate static analysis PNG")
    parser.add_argument("--optimize", action="store_true",
                        help="Generate optimization comparison PNG")
    parser.add_argument("--animate", action="store_true",
                        help="Generate animated trajectory GIF")
    parser.add_argument("--animate-view", action="store_true",
                        help="Generate animated analysis view (PCB + stats + head)")
    parser.add_argument("--all", action="store_true",
                        help="Generate all outputs + console report")
    args = parser.parse_args()

    comps = load_components()
    print(f"Loaded {len(comps)} components from {POS_FILE}")

    run_all = args.all or not (args.view or args.optimize or args.animate
                               or args.animate_view)

    if run_all or args.view:
        matplotlib.use("Agg")
        plot_analysis(comps, os.path.join(FAB_DIR, "trajectory_analysis.png"))

    if run_all or args.optimize:
        matplotlib.use("Agg")
        plot_optimization_overlay(
            comps, os.path.join(FAB_DIR, "optimization_compare.png")
        )

    if run_all or args.animate:
        matplotlib.use("Agg")
        animate_trajectory(comps, os.path.join(FAB_DIR, "trajectory.gif"))

    if run_all or args.animate_view:
        matplotlib.use("Agg")
        animate_analysis_view(comps, os.path.join(FAB_DIR, "trajectory_analysis.gif"))

    if run_all or True:
        print_report(comps)


if __name__ == "__main__":
    main()

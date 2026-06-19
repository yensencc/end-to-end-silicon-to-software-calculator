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

BOARD_W, BOARD_H = 62, 42
FEEDER = (BOARD_W / 2, 9)

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
    ax.set_ylim(-BOARD_H - 5, 5)
    ax.set_aspect("equal")
    ax.set_title("Placement Path & Sequence", fontsize=14, weight="bold")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")

    # Board
    board = mpatches.Rectangle((0, -BOARD_H), BOARD_W, BOARD_H,
                               linewidth=2, edgecolor="black",
                               facecolor="#f0f8e8")
    ax.add_patch(board)

    # Feeder
    feeder_rect = mpatches.Rectangle((-4, 5), BOARD_W + 8, 8,
                                     linewidth=1, edgecolor="#888",
                                     facecolor="#fff3cd", alpha=0.5)
    ax.add_patch(feeder_rect)
    ax.text(FEEDER[0], 9, "FEEDER", ha="center", fontsize=9, color="#666",
            weight="bold")
    ax.plot(FEEDER[0], FEEDER[1], marker="v", color="#cc7700",
            markersize=14, zorder=5)

    # Components
    for i, c in enumerate(comps):
        pt = comp_pos(c)
        color = COLORS_PLOT.get(comp_type(c["ref"]), "gray")
        size = 180 if c["ref"].startswith("U") else 100
        ax.scatter(pt[0], pt[1], c=color, s=size, alpha=0.8,
                   edgecolors="black", linewidth=0.5, zorder=4)
        ax.annotate(f"{i + 1}", (pt[0], pt[1]),
                    fontsize=7, ha="center", va="center",
                    weight="bold", color="white")

    # Path arrows
    prev_pt = FEEDER
    for i, c in enumerate(comps):
        pt = comp_pos(c)
        dx, dy = pt[0] - prev_pt[0], pt[1] - prev_pt[1]
        ax.annotate("", xy=pt, xytext=prev_pt,
                    arrowprops=dict(arrowstyle="->", color="red",
                                    lw=1.5, alpha=0.6))
        # Step number along path (midpoint)
        mid = ((prev_pt[0] + pt[0]) / 2, (prev_pt[1] + pt[1]) / 2)
        ax.text(mid[0], mid[1], str(i + 1), fontsize=6, color="red",
                ha="center", va="bottom", alpha=0.7, weight="bold")
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
        ax.set_ylim(-BOARD_H - 5, 5)
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=12, weight="bold")
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")

        board = mpatches.Rectangle((0, -BOARD_H), BOARD_W, BOARD_H,
                                   linewidth=2, edgecolor="black",
                                   facecolor="#f0f8e8")
        ax.add_patch(board)
        ax.plot(FEEDER[0], FEEDER[1], marker="v", color="#cc7700",
                markersize=10, zorder=5)
        ax.text(FEEDER[0], 10.5, "Feeder", ha="center", fontsize=7,
                color="#cc7700")

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
    TRAVEL_STEPS = 8
    DWELL_STEPS = 3
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
    ax.set_ylim(-BOARD_H - 8, 5)
    ax.set_aspect("equal")
    ax.set_title("Fuji AIMEX III  —  Pick & Place Trajectory", fontsize=14,
                 weight="bold")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")

    # Board + feeder
    board = mpatches.Rectangle((0, -BOARD_H), BOARD_W, BOARD_H,
                               linewidth=2, edgecolor="black",
                               facecolor="#f0f8e8")
    ax.add_patch(board)
    feeder_rect = mpatches.Rectangle((-4, 5), BOARD_W + 8, 8,
                                     linewidth=1, edgecolor="#888",
                                     facecolor="#fff3cd", alpha=0.5)
    ax.add_patch(feeder_rect)
    ax.plot(FEEDER[0], FEEDER[1], marker="v", color="#cc7700",
            markersize=12, zorder=5)

    # Component dots
    placed_dots = []
    unplaced_dots = []
    for i, c in enumerate(comps):
        pt = comp_pos(c)
        color = COLORS_PLOT.get(comp_type(c["ref"]))
        size = 180 if c["ref"].startswith("U") else 100
        su = ax.scatter(pt[0], pt[1], c=color, s=size, alpha=0.15,
                        edgecolors="black", linewidth=0.5, zorder=3)
        unplaced_dots.append(su)
        sp = ax.scatter(pt[0], pt[1], c=color, s=size * 1.3,
                        alpha=0.95, edgecolors="black", linewidth=1,
                        zorder=3, visible=False)
        placed_dots.append(sp)
        ax.annotate(c["ref"], (pt[0], pt[1]), fontsize=6,
                    ha="center", va="bottom")

    # Legend
    leg_elements = [
        mpatches.Patch(color=c, label=l)
        for c, l in [("#e74c3c", "IC"), ("#9b59b6", "Display"),
                     ("#3498db", "Connector"), ("#2ecc71", "Resistor"),
                     ("#e67e22", "Switch")]
    ]
    ax.legend(handles=leg_elements, loc="lower left", fontsize=7)

    # Animated elements
    (trail_line,) = ax.plot([], [], "r-", linewidth=2.5, alpha=0.7, zorder=4)
    (head_dot,) = ax.plot([], [], "o", color="#ff2200", markersize=14,
                          markeredgecolor="black", markeredgewidth=2, zorder=6)
    (head_glow,) = ax.plot([], [], "o", color="#ff8800", markersize=22,
                           alpha=0.3, zorder=5)
    (target_line,) = ax.plot([], [], "r--", linewidth=1.5, alpha=0.5, zorder=4)

    # Info panel (bottom strip)
    label_text = ax.text(0.02, -BOARD_H - 5, "", fontsize=9,
                         transform=ax.transData)
    progress_text = ax.text(BOARD_W - 0.02, -BOARD_H - 5, "",
                            fontsize=9, ha="right", transform=ax.transData)
    stats_text = ax.text(0.02, -BOARD_H - 6.8, "", fontsize=8,
                         color="#444", transform=ax.transData)

    # Progress bar background
    bar_ax = fig.add_axes([0.12, 0.04, 0.76, 0.025])
    bar_ax.set_xlim(0, 1)
    bar_ax.set_ylim(0, 1)
    bar_ax.axis("off")
    bar_ax.add_patch(mpatches.Rectangle((0, 0.2), 1, 0.6,
                                         facecolor="#ddd", edgecolor="none"))
    bar_fill = mpatches.Rectangle((0, 0.2), 0, 0.6,
                                   facecolor="#e74c3c", edgecolor="none")
    bar_ax.add_patch(bar_fill)

    artists = [trail_line, head_dot, head_glow, target_line,
               label_text, progress_text, stats_text, bar_fill]

    trail_x, trail_y = [], []

    def init():
        trail_line.set_data([], [])
        head_dot.set_data([], [])
        head_glow.set_data([], [])
        target_line.set_data([], [])
        label_text.set_text("")
        progress_text.set_text("")
        stats_text.set_text("")
        bar_fill.set_width(0)
        for sp in placed_dots:
            sp.set_visible(False)
        return artists + placed_dots + unplaced_dots

    def animate(frame_idx):
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

        return artists + placed_dots + unplaced_dots

    use_blit = save_path is None
    ani = animation.FuncAnimation(
        fig, animate, frames=total_frames,
        init_func=init, interval=80, repeat=use_blit, blit=use_blit
    )

    if save_path:
        print(f"Saving animation ({total_frames} frames) to {save_path} ...")
        ani.save(save_path, writer="pillow", fps=8, dpi=100)
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
    parser.add_argument("--all", action="store_true",
                        help="Generate all outputs + console report")
    args = parser.parse_args()

    comps = load_components()
    print(f"Loaded {len(comps)} components from {POS_FILE}")

    run_all = args.all or not (args.view or args.optimize or args.animate)

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

    if run_all or True:
        print_report(comps)


if __name__ == "__main__":
    main()

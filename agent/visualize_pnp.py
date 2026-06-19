#!/usr/bin/env python3
"""
Pick-and-Place Head Travel Visualizer
Simulates the Fuji AIMEX III head moving across the PCB placing components.
Reads the POS CSV and animates the placement sequence with smooth interpolation.

Usage:
  python visualize_pnp.py           # interactive window
  python visualize_pnp.py --save gif # save animated GIF to fab/
"""

import csv
import sys
import os
import argparse

try:
    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    import matplotlib.patches as patches
except ImportError:
    print("matplotlib not found — run: pip install matplotlib", file=sys.stderr)
    sys.exit(1)

FAB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fab")
POS_FILE = os.path.join(FAB_DIR, "calculator_pos.csv")

TRAVEL_STEPS = 10
DWELL_STEPS = 4

color_map = {"U": "red", "DISP": "purple", "J": "blue",
             "R": "green", "SW": "orange"}


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
    priority = {"J": 0, "U": 1, "DISP": 2, "R": 3, "SW": 4}
    components.sort(key=lambda c: (priority.get(c["ref"][:4], 99), c["ref"]))
    return components


def build_frame_data(comps):
    """Build interpolated frame sequence.

    Returns list of dicts: {x, y, comp_idx, placed, label}
    """
    board_w, board_h = 62, 42
    feeder = (board_w / 2, 9)
    frames = []

    for i, c in enumerate(comps):
        target = (c["x"], -c["y"])
        start = feeder

        # Travel from start (feeder) to target component
        for t in range(TRAVEL_STEPS):
            frac = (t + 1) / TRAVEL_STEPS
            frames.append({
                "x": start[0] + (target[0] - start[0]) * frac,
                "y": start[1] + (target[1] - start[1]) * frac,
                "comp_idx": i,
                "placed": None,
                "label": f"Moving to {c['ref']}"
            })

        # Dwell at component
        for t in range(DWELL_STEPS):
            frames.append({
                "x": target[0],
                "y": target[1],
                "comp_idx": i,
                "placed": i,
                "label": f"Placing {c['ref']} ({c['val']})"
            })

        # Return to feeder (except after last component)
        if i < len(comps) - 1:
            for t in range(TRAVEL_STEPS):
                frac = (t + 1) / TRAVEL_STEPS
                frames.append({
                    "x": target[0] + (feeder[0] - target[0]) * frac,
                    "y": target[1] + (feeder[1] - target[1]) * frac,
                    "comp_idx": i,
                    "placed": i,
                    "label": f"Returning for {comps[i+1]['ref']}"
                })

    return frames


def build_animation(comps, frame_data, save_path=None):
    board_w, board_h = 62, 42
    n = len(comps)

    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(-5, board_w + 5)
    ax.set_ylim(-board_h - 5, 5)
    ax.set_aspect("equal")
    ax.set_title("Fuji AIMEX III \u2014 Pick & Place Head Travel", fontsize=14)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")

    # Board
    board = patches.Rectangle((0, -board_h), board_w, board_h,
                              linewidth=2, edgecolor="black", facecolor="#f0f8e8")
    ax.add_patch(board)

    # Feeder
    feeder_rect = patches.Rectangle((-4, 5), board_w + 8, 8,
                                    linewidth=1, edgecolor="#888",
                                    facecolor="#fff3cd", alpha=0.5)
    ax.add_patch(feeder_rect)
    ax.text(board_w / 2, 9, "FEEDER BANK (reels + trays)",
            ha="center", fontsize=9, color="#666")

    # Component dots
    scatter_placed = []
    scatter_unplaced = []
    for i, c in enumerate(comps):
        color = color_map.get(c["ref"][:4], "gray")
        size = 120 if c["ref"].startswith("U") else 60
        su = ax.scatter(c["x"], -c["y"], c=color, s=size, alpha=0.15, zorder=3)
        scatter_unplaced.append(su)
        sp = ax.scatter(c["x"], -c["y"], c=color, s=size * 1.5,
                        alpha=0.95, edgecolors="black", linewidth=0.5,
                        zorder=3, visible=False)
        scatter_placed.append(sp)
        ax.annotate(c["ref"], (c["x"], -c["y"]),
                    fontsize=6, ha="center", va="bottom", color=color)

    # Legend
    legend_elements = [
        patches.Patch(color=c, label=l)
        for c, l in [("red", "IC (U1)"), ("purple", "Display"),
                     ("blue", "Connector"), ("green", "Resistor"),
                     ("orange", "Switch")]
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=8)

    # Trail line (head path history)
    (trail_line,) = ax.plot([], [], "r-", linewidth=1.5, alpha=0.4, zorder=4)

    # Head dot
    (head_dot,) = ax.plot([], [], "ro", markersize=10,
                          markeredgecolor="darkred", markeredgewidth=1.5,
                          zorder=5)

    # Dashed line from head to target
    (target_line,) = ax.plot([], [], "r--", linewidth=1, alpha=0.5, zorder=4)

    # Texts
    nozzle_text = ax.text(0, 0, "", fontsize=8, color="darkred", weight="bold")
    step_text = ax.text(board_w / 2, -board_h - 3, "", ha="center", fontsize=9)

    artists = [trail_line, head_dot, target_line, nozzle_text, step_text] + scatter_placed

    def init():
        trail_line.set_data([], [])
        head_dot.set_data([], [])
        target_line.set_data([], [])
        nozzle_text.set_text("")
        step_text.set_text("")
        for sp in scatter_placed:
            sp.set_visible(False)
        return artists

    # Precompute trail for each frame (cumulative path up to that frame)
    trail_x_history = []
    trail_y_history = []
    for fd in frame_data:
        trail_x_history.append(fd["x"])
        trail_y_history.append(fd["y"])

    def animate(frame_idx):
        fd = frame_data[frame_idx]

        # Head position
        hx, hy = fd["x"], fd["y"]
        head_dot.set_data([hx], [hy])

        # Trail up to this frame
        trail_line.set_data(trail_x_history[:frame_idx + 1],
                            trail_y_history[:frame_idx + 1])

        # Placed/unplaced dots
        placed_up_to = fd["placed"]
        for i in range(n):
            sp = scatter_placed[i]
            su = scatter_unplaced[i]
            if placed_up_to is not None and i <= placed_up_to:
                sp.set_visible(True)
                su.set_alpha(0.15)
            else:
                sp.set_visible(False)
                su.set_alpha(0.15)

        # Dashed line to target
        ci = fd["comp_idx"]
        c = comps[ci]
        target_line.set_data([hx, c["x"]], [hy, -c["y"]])

        nozzle_text.set_text(f"Nozzle: {c['ref']} ({c['val']})")
        nozzle_text.set_position((hx + 1.5, hy + 1.5))

        step_text.set_text(
            f"Frame {frame_idx + 1}/{len(frame_data)} | {fd['label']}"
        )

        return artists

    ani = animation.FuncAnimation(
        fig, animate, frames=len(frame_data),
        init_func=init, interval=80, repeat=True, blit=True
    )

    plt.tight_layout()

    if save_path:
        print(f"Saving animation ({len(frame_data)} frames) to {save_path} ...")
        ani.save(save_path, writer="pillow", fps=10, dpi=100)
        print("Done.")
    else:
        plt.show()

    return ani


def main():
    parser = argparse.ArgumentParser(
        description="Visualize pick-and-place head travel"
    )
    parser.add_argument("--save", nargs="?", const="gif",
                        help="Save animation to path (default: fab/placement.gif)")
    args = parser.parse_args()

    comps = load_components()
    print(f"Loaded {len(comps)} components from {POS_FILE}")

    save_path = None
    if args.save:
        if args.save == "gif":
            save_path = os.path.join(FAB_DIR, "placement.gif")
        else:
            save_path = args.save

    if save_path:
        matplotlib.use("Agg")

    fd = build_frame_data(comps)
    print(f"Generated {len(fd)} animation frames")

    build_animation(comps, fd, save_path)


if __name__ == "__main__":
    main()

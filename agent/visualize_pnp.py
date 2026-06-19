#!/usr/bin/env python3
"""
Pick-and-Place Head Travel Visualizer
Simulates the Fuji AIMEX III head moving across the PCB placing components.
Reads the POS CSV and animates the placement sequence.

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
    print("Installing matplotlib...", file=sys.stderr)
    sys.exit(1)

FAB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fab")
POS_FILE = os.path.join(FAB_DIR, "calculator_pos.csv")


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


def build_animation(comps, save_path=None):
    board_w, board_h = 62, 42

    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(-5, board_w + 5)
    ax.set_ylim(-board_h - 5, 5)
    ax.set_aspect("equal")
    ax.set_title("Fuji AIMEX III \u2014 Pick & Place Head Travel", fontsize=14)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")

    board = patches.Rectangle((0, -board_h), board_w, board_h,
                              linewidth=2, edgecolor="black", facecolor="#f0f8e8")
    ax.add_patch(board)
    ax.text(board_w / 2, -board_h / 2, "62mm x 42mm PCB",
            ha="center", va="center", fontsize=10, color="#aaa")

    feeder_rect = patches.Rectangle((-4, 5), board_w + 8, 8,
                                    linewidth=1, edgecolor="#888",
                                    facecolor="#fff3cd", alpha=0.5)
    ax.add_patch(feeder_rect)
    ax.text(board_w / 2, 9, "FEEDER BANK (reels + trays)",
            ha="center", fontsize=9, color="#666")

    color_map = {"U": "red", "DISP": "purple", "J": "blue",
                 "R": "green", "SW": "orange"}
    for c in comps:
        color = color_map.get(c["ref"][:4], "gray")
        size = 120 if c["ref"].startswith("U") else 60
        ax.scatter(c["x"], -c["y"], c=color, s=size, alpha=0.6, zorder=3)
        ax.annotate(c["ref"], (c["x"], -c["y"]),
                    fontsize=6, ha="center", va="bottom", color=color)

    legend_elements = [
        patches.Patch(color="red", label="IC (U1)"),
        patches.Patch(color="purple", label="Display"),
        patches.Patch(color="blue", label="Connector"),
        patches.Patch(color="green", label="Resistor"),
        patches.Patch(color="orange", label="Switch"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=8)

    (head_line,) = ax.plot([], [], "r-", linewidth=1.5, alpha=0.7, zorder=4)
    (head_dot,) = ax.plot([], [], "ro", markersize=8, zorder=5)
    nozzle_text = ax.text(0, 0, "", fontsize=8, color="darkred", weight="bold")
    step_text = ax.text(board_w / 2, -board_h - 3, "",
                        ha="center", fontsize=9)

    def init():
        head_line.set_data([], [])
        head_dot.set_data([], [])
        nozzle_text.set_text("")
        step_text.set_text("")
        return head_line, head_dot, nozzle_text, step_text

    def animate(frame):
        n = len(comps)
        if frame == 0:
            c = comps[0]
            x_vals = [board_w / 2, c["x"]]
            y_vals = [9, -c["y"]]
        elif frame < n:
            prev = comps[frame - 1]
            c = comps[frame]
            x_vals = [prev["x"], board_w / 2, board_w / 2, c["x"]]
            y_vals = [-prev["y"], 9, 9, -c["y"]]
        else:
            c = comps[-1]
            x_vals = [c["x"]]
            y_vals = [-c["y"]]

        head_line.set_data(x_vals, y_vals)
        head_dot.set_data([x_vals[-1]], [y_vals[-1]])

        nozzle_text.set_text(f"Nozzle: {c['ref']} ({c['val']})")
        nozzle_text.set_position((x_vals[-1] + 1, y_vals[-1] + 1))

        step = min(frame + 1, n)
        step_text.set_text(
            f"Step {step}/{n} \u2014 "
            f"Placing {c['ref']} at ({c['x']:.1f}, {c['y']:.1f})mm [{c['side']}]"
        )
        return head_line, head_dot, nozzle_text, step_text

    ani = animation.FuncAnimation(
        fig, animate, frames=len(comps) + 1,
        init_func=init, interval=800, repeat=True, blit=True
    )

    plt.tight_layout()

    if save_path:
        print(f"Saving animation to {save_path} ...")
        ani.save(save_path, writer="pillow", fps=1.25, dpi=120)
        print("Done.")
    else:
        plt.show()


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

    # Use non-interactive backend if saving
    if save_path:
        matplotlib.use("Agg")

    build_animation(comps, save_path)


if __name__ == "__main__":
    main()

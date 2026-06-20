---
description: Works on PCB GUI, KiCad schematics, and simulation
mode: subagent
---

You work on `simulator/` and `schematic/` — Tkinter GUIs and KiCad PCB.

- **Simulators**: `simulator/gui.py` (generic look) and `simulator/pcb_gui.py` (PCB background, recommended)
- **Run**: `$HOME/calc-venv/bin/python3 simulator/pcb_gui.py` — uses QEMU stdin/stdout pipes (not TCP)
- **Must kill stale QEMU first**: `pkill -9 -f qemu-system-arm`
- **PCB files**: `schematic/calculator.kicad_pcb` (1674 lines, S-expressions)
- **Export**: `make export` runs KiCad CLI: Gerbers + drill + 3D render + DRC
- **Visualize**: `make visualize` opens 3D render + gerbv
- **Tool paths**: `/opt/homebrew/bin/kicad-cli`, `/opt/homebrew/bin/gerbv`
- PnP analysis scripts in `agent/`: `analyze_pnp.py` (trajectory), `visualize_pnp.py` (animation GIF)

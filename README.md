# Calculator MVP — End-to-End Silicon to Software

A zero-hardware calculator build that spans RTL (Verilog) → PCB (KiCad) → Firmware (Rust) → Agent (Python). Simulate everything on your Mac — no physical hardware required.

## Architecture

```
┌──────────────────────────────────────────┐
│  AGENT  (agent/build_agent.py)          │
│  Runs: make simulate-rtl, simulate-fw   │
│  Reports: PASS/FAIL per layer           │
└──────────────────────────────────────────┘
                    │
┌──────────────────────────────────────────┐
│  FIRMWARE  (firmware/src/main.rs)       │
│  ARM Cortex-M3 no_std Rust              │
│  ALU ops: add, sub, mul                 │
│  Runs in QEMU lm3s6965evb              │
└──────────────────────────────────────────┘
                    │
┌──────────────────────────────────────────┐
│  RTL  (rtl/*.v)                         │
│  8-bit ALU, 4x4 keypad, 7-seg display  │
│  Simulated with Verilator 5.x           │
│  Tests: 2+2=4, 5+3=8, 10-3=7, 200-50=150│
└──────────────────────────────────────────┘
                    │
┌──────────────────────────────────────────┐
│  PCB  (schematic/calculator.kicad_pcb)  │
│  LQFP-48 MCU, 4x4 keypad matrix,        │
│  7-segment display, SWD programming,    │
│  62×42mm board with routed traces       │
│  Gerbers + POS CSV → ready for fab      │
└──────────────────────────────────────────┘
```

## Quick Start

```bash
# Full pipeline: RTL sim → Firmware sim → Agent report
make all

# Or step by step:
make simulate-rtl       # Verilator: 4 ALU tests
make simulate-fw        # QEMU: prints 2+2=4
make export             # Gerbers + 3D render + DRC
make visualize          # Export + open 3D render + gerbv
make agent              # Pipeline status report
```

## Project Structure

```
calculator-mvp/
├── Makefile                  # Build targets (see below)
├── rtl/                      # Verilog RTL
│   ├── alu.v                 # 8-bit ALU (add/sub) with carry, zero, overflow
│   ├── keypad.v              # 4x4 matrix decoder
│   ├── display.v             # 7-segment driver (common cathode)
│   ├── top.v                 # Top-level integration
│   └── tb_top.cpp            # Verilator C++ testbench
├── firmware/
│   ├── Cargo.toml            # Rust project (thumbv7m-none-eabi)
│   ├── memory.x              # Linker script (256K FLASH, 64K RAM)
│   ├── .cargo/config.toml    # Build target config
│   └── src/main.rs           # Calculator logic, semihosting output
├── schematic/
│   ├── calculator.kicad_pro  # KiCad project
│   ├── calculator.kicad_sch  # Schematic (placeholder)
│   ├── calculator.kicad_pcb  # PCB with routed traces (1674 lines)
│   └── calculator.kicad_prl  # Project local settings
├── agent/
│   └── build_agent.py        # Pipeline runner script
├── fab/                      # Generated outputs (gitignored)
│   ├── calculator-F_Cu.gtl   # Top copper Gerber
│   ├── calculator-B_Cu.gbl   # Bottom copper Gerber
│   ├── calculator-F_Mask.gts # Top solder mask
│   ├── calculator-B_Mask.gbs # Bottom solder mask
│   ├── calculator-F_Silkscreen.gto  # Top silkscreen
│   ├── calculator-Edge_Cuts.gm1     # Board outline
│   ├── calculator.drl        # NC drill file
│   ├── calculator_pos.csv    # Pick-and-place (27 components)
│   ├── calculator_3d.png     # 3D board render
│   └── calculator-job.gbrjob        # Gerber job file
└── README.md
```

## Make Targets

| Target | Description |
|--------|-------------|
| `make setup` | Check dependencies (verilator, qemu) |
| `make simulate-rtl` | Compile Verilog + run ALU tests via Verilator |
| `make simulate-fw` | Build Rust firmware + run in QEMU ARM Cortex-M3 |
| `make check-schematic` | KiCad ERC (schematic electrical rules) |
| `make export` | Generate Gerbers, drill, 3D render, DRC report |
| `make visualize` | Export + open 3D render in Preview and gerbv |
| `make agent` | Run all pipeline steps and report PASS/FAIL |
| `make all` | setup → simulate-rtl → simulate-fw → check-schematic → agent |
| `make clean` | Remove build artifacts |

## Dependencies (macOS)

```bash
brew install verilator gtkwave icarus-verilog qemu python@3.12 rustup-init
brew install --cask kicad
rustup target add thumbv7m-none-eabi
```

## PCB Specification

| Parameter | Value |
|-----------|-------|
| Board size | 62mm × 42mm |
| Layers | 2 (F.Cu, B.Cu) |
| Copper thickness | 0.035mm (1oz) |
| Min track width | 0.2mm (design rule) |
| Min via diameter | 0.5mm |
| Components | 27 (1 MCU, 16 switches, 1 display, 1 header, 8 resistors) |
| Nets | 19 (power, ground, keypad matrix, segments, SWD) |
| Traces | 107 copper segments routing all connections |
| Power planes | GND and +3.3V copper fills on F.Cu |

### Component Placement

| Ref | Package | Position | Role |
|-----|---------|----------|------|
| U1 | LQFP-48 (7×7mm) | (31, -7) mm | MCU |
| DISP1 | 7-segment LED | (10, -35) mm | Display |
| J1 | PinHeader 1×04 | (55, -37) mm | SWD programming |
| SW1–SW16 | Tactile 6mm | 4×4 grid | Keypad matrix |
| R1–R4 | 0805 | (35–40, -26–-31) mm | Row pull-ups |
| R5–R8 | 0805 | (45–50, -26–-31) mm | Segment current limit |

## Fabrication Outputs

The `fab/` directory contains everything needed for PCB fabrication and assembly:

- **Gerber files**: Top/bottom copper, solder mask, silkscreen, edge cuts
- **Drill file**: NC drill hits (`.drl`)
- **Pick-and-place CSV**: Component XY positions for Fuji/PnP machines
- **3D render**: PNG preview of the assembled board
- **DRC report**: Design rules check results

## Agent Context

The `build_agent.py` script runs three pipeline steps:

1. **RTL Compile** — Verilator compiles Verilog + runs 4 arithmetic tests
2. **Firmware Build** — Cargo builds for ARM Cortex-M3 + QEMU executes with semihosting output
3. **Schematic Check** — KiCad ERC validates schematic (placeholder)

The agent runs `make` targets from the project root and exits with status 0 only if all steps pass.

## Iteration Loop

```
1. Edit rtl/alu.v            → Add a new ALU operation
   make simulate-rtl          → See test results
2. Edit firmware/src/main.rs  → Use the new operation
   make simulate-fw           → See QEMU output
3. Edit schematic/calculator.kicad_pcb → Add/reposition components
   make visualize              → See 3D render + Gerber preview
4. Run make agent              → Full pipeline report
```

Sub-second rebuilds for RTL (Verilator cache) and firmware (Cargo incremental).

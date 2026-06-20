# Calculator MVP — Agent Guide

## Project structure

```
calculator-mvp/
├── rtl/            Verilog RTL (alu, keypad, display, top) + Verilator testbench
├── firmware/       no_std Rust for ARM Cortex-M3 (thumbv7m-none-eabi)
├── schematic/      KiCad PCB files (calculator.kicad_pcb)
├── simulator/      Python Tkinter GUIs (gui.py, pcb_gui.py)
├── agent/          Pipeline runner + PnP analysis scripts
└── fab/            Generated outputs (gitignored)
```

## Key commands

| Command | What it does | Notes |
|---------|-------------|-------|
| `make simulate-rtl` | Verilator compiles Verilog + runs ALU tests | Must be run from project root |
| `make simulate-fw` | Build firmware + QEMU with serial stdio | Ctrl-C to exit QEMU |
| `make simulate` | Interactive Tkinter GUI + QEMU | Uses `$HOME/calc-venv/bin/python3` |
| `make simulate-pcb` | PCB background GUI + QEMU (recommended) | Uses `$HOME/calc-venv/bin/python3` |
| `make export` | KiCad CLI: Gerbers, drill, 3D render, DRC | Needs `/opt/homebrew/bin/kicad-cli` |
| `make agent` | Run 5-step pipeline (RTL→Firmware→Schematic→PnP) | Stops on first failure |
| `make all` | setup → simulate-rtl → simulate-fw → check-schematic → agent | Full CI-style run |

## Firmware build quirks

- **Target**: `thumbv7m-none-eabi` (no_std, no heap, no files)
- **Must set**: `RUSTFLAGS="-C link-arg=-Tlink.ld"` (sets memory.x layout)
- **Must convert**: ELF → flat binary via `rust-objcopy -O binary` before QEMU
- **Linker script**: `firmware/memory.x` — 256K FLASH at 0x0, 64K RAM at 0x20000000
- **Only dependency**: `panic-halt = "0.2"` (no alloc, no std)

## Serial protocol (firmware ↔ GUI)

All lines are `\n`-terminated (`\n` is expanded to `\n\r` by `uart_puts`):

| Prefix | Example | Purpose |
|--------|---------|---------|
| `O:` | `O:CALCULATOR 1.0\|    READY    ` | OLED display (two fields separated by `\|`) |
| `D:` | `D:        0` | 7-segment display — format `D: ` + 8 chars right-aligned (skip 3 chars to parse) |
| `E:` | `E:error message` | Error state |

Key input: single ASCII byte per key (`0-9`, `+`, `-`, `*`, `/`, `=`, `C`).

## Simulator quirks

- **Python**: Uses `$HOME/calc-venv/bin/python3`, not system `python3` (system Python 3.9.6 Tkinter crashes on this macOS)
- **QEMU serial**: Uses stdin/stdout pipes (not TCP — QEMU 11 TCP chardev is broken on macOS 15)
- **Must kill stale QEMU**: Before re-launching, kill any leftover `qemu-system-arm` processes
- **QEMU path**: `/opt/homebrew/bin/qemu-system-arm`

## Agent pipeline (`agent/build_agent.py`)

Runs sequentially: RTL Compile → Firmware Build → Schematic Check → PnP Animate → Trajectory Report. Stops at first failure. Each step calls `make <target>` from project root with `/opt/homebrew/bin` added to PATH.

## Key tool paths

- QEMU: `/opt/homebrew/bin/qemu-system-arm`
- Verilator: `/opt/homebrew/bin/verilator`
- KiCad CLI: `/opt/homebrew/bin/kicad-cli`
- Rust target: `thumbv7m-none-eabi` (add via `rustup target add thumbv7m-none-eabi`)

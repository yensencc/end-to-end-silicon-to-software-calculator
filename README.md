# Calculator MVP — End-to-End Silicon to Software

A zero-hardware calculator build that spans RTL (Verilog) → PCB (KiCad) → Firmware (Rust) → Interactive Simulation (QEMU + Tkinter) → PnP Analysis (Python). Simulate everything on your Mac — no physical hardware required.

Click the keypad on the actual PCB layout and watch the 7-segment display update, driven by real firmware on an emulated ARM Cortex-M3.

## Architecture

```
┌──────────────────────────────────────────────┐
│  INTERACTIVE PCB GUI (simulator/pcb_gui.py) │
│  KiCad PCB image as window, clickable keys   │
│  at real switch positions, live 7-segment    │
│  display — talks to QEMU via TCP serial      │
└──────────────────────┬───────────────────────┘
                       │ TCP :12345
┌──────────────────────────────────────────────┐
│  QEMU ARM Cortex-M3 — real firmware          │
│  (firmware/src/main.rs) no_std Rust          │
│  Calculator state machine: + - * / = C      │
│  UART polled driver at 0x4000C000           │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────────────────────────────┐
│  AGENT & ANALYSIS (agent/)                   │
│  build_agent.py — 5-step pipeline runner    │
│  visualize_pnp.py — PnP head travel GIF     │
│  analyze_pnp.py — trajectory analysis with  │
│    PCB background, head animation, stats    │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────────────────────────────┐
│  FIRMWARE (firmware/src/main.rs)            │
│  compiled for thumbv7m-none-eabi            │
│  runs in QEMU lm3s6965evb                   │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────────────────────────────┐
│  RTL (rtl/*.v)                              │
│  8-bit ALU, 4x4 keypad, 7-seg display      │
│  Simulated with Verilator 5.x               │
│  Tests: 2+2=4, 5+3=8, 10-3=7, 200-50=150   │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────────────────────────────┐
│  PCB (schematic/calculator.kicad_pcb)       │
│  LQFP-48 MCU, 4x4 keypad matrix,            │
│  7-segment display, SWD programming,        │
│  62×42mm board, 107 routed traces           │
│  Gerbers + POS CSV → ready for fab          │
└──────────────────────────────────────────────┘
```

## Quick Start

```bash
# Interactive: click the actual PCB keypad, see live results
make simulate-pcb

# Or the full pipeline: RTL sim → Firmware sim → Agent report
make all

# Or step by step:
make simulate-rtl       # Verilator: 4 ALU tests
make simulate-fw        # QEMU: prints 2+2=4
make simulate           # Interactive: Tkinter calculator + QEMU
make simulate-pcb       # Interactive: PCB background + QEMU
make export             # Gerbers + 3D render + DRC
make visualize          # Export + open 3D render + gerbv
make visualize-pnp      # PnP head travel animation GIF
make analyze-pnp        # Full trajectory analysis (4 outputs)
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
│   └── src/main.rs           # Calculator logic, UART polled driver
├── schematic/
│   ├── calculator.kicad_pro  # KiCad project
│   ├── calculator.kicad_sch  # Schematic (placeholder)
│   ├── calculator.kicad_pcb  # PCB with routed traces (1674 lines)
│   └── calculator.kicad_prl  # Project local settings
├── simulator/
│   ├── gui.py                # Tkinter calculator (generic look)
│   └── pcb_gui.py            # PCB-based GUI (actual board image)
├── agent/
│   ├── build_agent.py        # 5-step pipeline runner
│   ├── visualize_pnp.py      # PnP head travel animation
│   └── analyze_pnp.py        # Full trajectory analysis
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
│   ├── calculator_pcb.png    # PCB background image for GUI
│   ├── trajectory_analysis.png   # Static path map with stats
│   ├── trajectory_analysis.gif   # Animated head travel + PCB
│   ├── trajectory.gif            # Simple head animation
│   ├── optimization_compare.png  # Original vs optimized sequence
│   ├── placement.gif             # PnP head travel GIF
│   └── calculator-job.gbrjob     # Gerber job file
└── README.md
```

## Make Targets

| Target | Description |
|--------|-------------|
| `make setup` | Check dependencies (verilator, qemu) |
| `make simulate-rtl` | Compile Verilog + run ALU tests via Verilator |
| `make simulate-fw` | Build Rust firmware + run in QEMU, then exit |
| `make simulate` | Interactive: Tkinter calculator GUI + QEMU firmware |
| `make simulate-pcb` | **Interactive: actual PCB image as GUI** + QEMU firmware |
| `make check-schematic` | KiCad ERC (schematic electrical rules) |
| `make export` | Generate Gerbers, drill, 3D render, DRC report |
| `make visualize` | Export + open 3D render in Preview and gerbv |
| `make visualize-pnp` | PnP head travel animation → `fab/placement.gif` |
| `make analyze-pnp` | Full SMT trajectory analysis (4 outputs to `fab/`) |
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

## Interactive Simulation

Two GUI modes connect the real firmware running on QEMU to a clickable calculator:

### `make simulate` — Generic Calculator GUI
A clean Tkinter window with a 7-segment-style display and keypad buttons. Fast, simple, no dependencies beyond tkinter.

### `make simulate-pcb` — PCB-Based GUI (recommended)
Shows the **actual KiCad PCB** as the background — copper traces, silkscreen, component outlines all visible. Clickable switch overlays at the real SW1–SW16 positions on the board, with the 7-segment LED display rendered at the DISP1 location.

```
┌─────────────────────────────────────────────┐
│  Calculator PCB — QEMU Cortex-M3           │
│  ┌───────────────────────────────────┐     │
│  │ ┌───────────────────────────────┐ │     │
│  │ │  ╔═╗ ╔═╗ ╔═╗ ╔═╗ ╔═╗ ╔═╗ ╔═╗ ╔═╗│ │     │
│  │ │  ║ ║ ║ ║ ║7║ ║ ║ ║ ║ ║ ║ ║ ║ ║ │ │     │
│  │ │  ╚═╝ ╚═╝ ╚═╝ ╚═╝ ╚═╝ ╚═╝ ╚═╝ ╚═╝│ │     │
│  │ └───────────────────────────────┘ │     │
│  │                                    │     │
│  │   [7]  [8]  [9]  [/]   ← actual   │     │
│  │   [4]  [5]  [6]  [*]   switch     │     │
│  │   [1]  [2]  [3]  [-]   positions  │     │
│  │   [C]  [0]  [=]  [+]   on PCB     │     │
│  └───────────────────────────────────┘     │
│  Status: Running                           │
└─────────────────────────────────────────────┘
```

Key mapping (standard calculator layout on the 4×4 matrix):

```
SW1(7)  SW2(8)  SW3(9)  SW4(/)
SW5(4)  SW6(5)  SW7(6)  SW8(*)
SW9(1)  SW10(2) SW11(3) SW12(-)
SW13(C) SW14(0) SW15(=) SW16(+)
```

Both modes use TCP serial (`tcp::12345`) to communicate with QEMU — no PTY race conditions.

## Pick-and-Place Analysis

Two visualization targets simulate the SMT assembly process:

| Target | Output | What It Shows |
|--------|--------|---------------|
| `make visualize-pnp` | `fab/placement.gif` | Head traveling from feeder to each component, placing them one by one (373 frames) |
| `make analyze-pnp` | `fab/trajectory_analysis.png` | Static PCB map with component dots, path arrows, step circles, stats panel |
| | `fab/optimization_compare.png` | Side-by-side original vs. optimized placement sequence |
| | `fab/trajectory.gif` | Head travel animation with step numbers |
| | `fab/trajectory_analysis.gif` | Full animated analysis: PCB background, head travel, placement burst, live stats |

The trajectory analyzer uses the actual PCB background (exported from KiCad), places components at their real coordinates, and simulates the Fuji AIMEX III head path with smooth interpolation (TRAVEL: 6 steps, DWELL: 2 steps).

## Iteration Loop

```
1. Edit rtl/alu.v               → Add a new ALU operation
   make simulate-rtl             → See test results
2. Edit firmware/src/main.rs     → Use the new operation
   make simulate-fw              → See QEMU output
3. Edit schematic/calculator.kicad_pcb → Add/reposition components
   make simulate-pcb              → See the updated board as an interactive GUI
4. Run make agent                 → Full pipeline report
5. Run make visualize-pnp         → See assembly animation
6. Run make analyze-pnp           → See trajectory analysis
```

Sub-second rebuilds for RTL (Verilator cache) and firmware (Cargo incremental).

---

## For Junior Engineers: How This Calculator Works End-to-End

### The Mental Model

Think of this project like a **full-stack web app**, but for hardware:

| Layer | Analogy | What It Does |
|-------|---------|--------------|
| **RTL (Verilog)** | The backend server logic | Defines *how* the math hardware works at the transistor level |
| **Firmware (Rust)** | The application code | Decides *what* math to do and prints the result |
| **PCB (KiCad)** | The server hardware | The physical board that connects everything |
| **Agent (Python)** | CI/CD pipeline | Runs tests and tells you if things pass or fail |

You edit code → run `make` → see output. Exactly like writing Node.js and running `npm test`.

### What Each File Actually Does

#### `rtl/alu.v` — The Math Brain (Verilog)

Verilog is a **hardware description language**. It's not a program that runs step-by-step — it describes wires and logic gates that *exist simultaneously*.

```verilog
// This is NOT a function that runs.
// It's a blueprint for physical circuits.
always @(posedge clk) begin
    result <= a + b;  // These wires exist forever
    carry  <= a + b > 255;  // This check is always happening
end
```

**Key insight**: Everything in Verilog happens at the same time (parallel), not line by line like Python/JavaScript.

The ALU has:
- **Inputs**: `a`, `b` (8-bit numbers), `opcode` (which operation)
- **Outputs**: `result`, `carry`, `zero`, `overflow` flags
- **Operations**: `00` = add, `01` = subtract

#### `rtl/tb_top.cpp` — The Test Driver (C++)

This is a normal C++ program that:
1. Creates a "virtual chip" from your Verilog design
2. Pushes buttons (sets inputs like `btn_a = 2`)
3. Checks that the outputs match (`alu_result == 4`)
4. Prints PASS or FAIL for each test

Think of it like a unit test for a physical chip.

#### `firmware/src/main.rs` — The On-Device App (Rust)

This is `no_std` Rust — which means **no operating system, no heap, no files**. It's running directly on a simulated ARM Cortex-M3 microcontroller.

```rust
fn alu_add(a: i8, b: i8) -> i8 { a + b }
```

It prints to your Mac's terminal via **semihosting** — a debug feature where the simulated chip asks QEMU "hey, please print this string for me."

#### `schematic/calculator.kicad_pcb` — The Circuit Board Layout (S-expressions)

This file describes the physical PCB: where components sit and how copper traces connect them. It's 1674 lines of nested parentheses that look like JSON without keys:

```lisp
(segment           ; A copper wire
  (start 31 7)     ; Starting at position (31mm, 7mm)
  (end 31.5 7.5)   ; Ending at (31.5mm, 7.5mm)
  (width 0.25)     ; 0.25mm thick trace
  (layer "F.Cu")   ; On the top copper layer
  (net 1)          ; Belongs to net #1
)
```

The file was **generated by a Python script** (`/tmp/gen_full_pcb.py`), not written by hand. You can modify the Python generator or edit the file directly in VS Code.

### How the Layers Connect

```
Software Land                     Hardware Land
─────────────                     ─────────────
                                   ┌─────────┐
You run: make simulate-fw          │ PCB     │
  └─► QEMU boots a virtual ARM    │ (physical│
      Cortex-M3 chip               │  layout) │
        └─► It runs main.rs        └────┬────┘
            └─► Calls alu_add(2,2)      │
                └─► Which matches        │
                    the Verilog ALU  ────┘
                    simulation
```

The Verilog ALU and the Rust `alu_add` should produce the **same result**. That's the point: the hardware (Verilog) and the software (Rust) implement the same math.

### How to Make Your First Change

Let's walk through adding a new operation: **bitwise AND**.

#### Step 1: Add the hardware operation (`rtl/alu.v`)

Find the `case (opcode)` block and add `2'b10`:

```verilog
2'b10: begin
    result   <= a & b;     // bitwise AND
    carry    <= 1'b0;
    zero     <= ((a & b) == 8'b0);
    overflow <= 1'b0;
end
```

#### Step 2: Add a test for it (`rtl/tb_top.cpp`)

Add after the subtraction test:

```cpp
printf("\nTest 5: 0b11001100 & 0b10101010 = 0b10001000\n");
top->btn_a  = 0b11001100;
top->btn_b  = 0b10101010;
top->opcode = 2;
// ... clock ticks ...
printf("  result=%d %s\n", top->alu_result,
       top->alu_result == 0b10001000 ? "PASS" : "FAIL");
```

#### Step 3: Run the RTL test

```bash
make simulate-rtl
```

If it passes, your hardware can do AND.

#### Step 4: Add the same operation in Rust (`firmware/src/main.rs`)

```rust
fn alu_and(a: i8, b: i8) -> i8 { a & b }
```

And call it:

```rust
hprintln!("{} & {} = {}", a, b, alu_and(a, b));
```

#### Step 5: Run the firmware test

```bash
make simulate-fw
```

If both pass, your hardware AND software agree on what AND means.

#### Step 6: Run the full pipeline

```bash
make all
```

### Common Questions

**Q: Why do I need both Verilog AND Rust? Can't I just write Rust?**

The Verilog describes what the *physical chip* does — if you were to manufacture this calculator, the ALU would be etched in silicon. The Rust is the *program* that runs on the chip. In a real product, the Verilog might be in a custom ASIC or FPGA, and the Rust runs on the CPU.

But for this MVP, the Verilog simulation and the Rust program run **independently**. They both compute `2+2=4`, and the agent checks that both layers pass. In a real chip, the Rust would actually talk to the Verilog hardware over GPIO pins.

**Q: I don't understand S-expressions. Do I need to edit the PCB file manually?**

No. The PCB was auto-generated by a Python script and is included as-is. To modify the PCB:
1. Install KiCad
2. Open `schematic/calculator.kicad_pcb` in the PCB Editor (GUI)
3. Drag components, route traces with the mouse
4. Save — it writes the S-expressions for you

Or modify the generator script at `/tmp/gen_full_pcb.py` and re-run it.

**Q: What's the difference between `simulate-rtl` and `simulate-fw`?**

| Target | What it tests | How |
|--------|---------------|-----|
| `simulate-rtl` | The Verilog hardware design | C++ testbench drives Verilator simulation |
| `simulate-fw` | The Rust firmware | QEMU emulates an ARM Cortex-M3 chip |

They're independent tests for the same behavior (calculator math), from two different layers.

**Q: Can I make this without understanding electronics?**

Yes. This MVP is designed for software engineers. You need to know:
- **Verilog**: Think of it like describing a circuit diagram in code. Keywords: `module`, `wire`, `reg`, `always`, `assign`.
- **Rust**: `no_std` means no standard library. No `Vec`, no `String`, no `HashMap`. Just integers and loops.
- **KiCad**: Install it, open the `.kicad_pcb` file, use the GUI to move things around. It's like Illustrator for circuit boards.

**Q: How long does each step take?**

| Step | Time |
|------|------|
| Edit a Verilog file | 30 seconds |
| `make simulate-rtl` | ~2 seconds (cached) |
| Edit Rust firmware | 30 seconds |
| `make simulate-fw` | ~1 second (cached) |
| Edit PCB | 5 minutes (KiCad GUI) |
| `make export` | ~10 seconds |
| Full `make all` | ~5 seconds (all cached) |

You can iterate on code changes in under 30 seconds.

### The Core Loop

```
1. Edit code (VS Code)
2. Run make (terminal)
3. See result (PASS/FAIL)
4. Repeat
```

That's it. Nothing else matters for the MVP. No factory, no manufacturing, no BOM — just code, simulate, verify.

---
description: Works on Verilog RTL and runs Verilator simulations
mode: subagent
---

You work on `rtl/` — Verilog hardware design and Verilator testbench.

- **Files**: `rtl/alu.v` (8-bit ALU: add, sub), `rtl/keypad.v` (4x4 matrix decoder), `rtl/display.v` (7-segment driver), `rtl/top.v` (top-level integration), `rtl/tb_top.cpp` (C++ testbench)
- **Test**: `cd rtl && /opt/homebrew/bin/verilator --top-module top --cc --exe --build -j 0 -Wall -Wno-MULTITOP -Wno-UNUSEDSIGNAL tb_top.cpp top.v alu.v keypad.v display.v && ./obj_dir/Vtop`
- **Test shortcut**: `make simulate-rtl` from project root
- ALU opcodes: `00` = add, `01` = subtract. Outputs: `result`, `carry`, `zero`, `overflow`.
- Tests: 2+2=4, 5+3=8, 10-3=7, 200-50=150 (in tb_top.cpp)

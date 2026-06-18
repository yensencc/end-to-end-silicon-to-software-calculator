.PHONY: all setup simulate-rtl simulate-fw check-schematic agent export visualize clean

SHELL := /bin/bash
PATH := /opt/homebrew/bin:/opt/homebrew/sbin:$(HOME)/.cargo/bin:$(PATH)

all: setup simulate-rtl simulate-fw check-schematic agent

# === PCB Export & Visualization (edit .kicad_pcb in VS Code, then run these) ===

FAB_DIR := fab
export:
	@echo "--- Exporting Gerbers, Drill, and 3D Render ---"
	mkdir -p $(FAB_DIR)
	kicad-cli pcb export gerbers --output $(FAB_DIR) schematic/calculator.kicad_pcb
	kicad-cli pcb export drill   --output $(FAB_DIR) schematic/calculator.kicad_pcb
	kicad-cli pcb export pos     --output $(FAB_DIR) --format csv schematic/calculator.kicad_pcb 2>/dev/null || true
	kicad-cli pcb render --output $(FAB_DIR)/calculator_3d.png --width 1920 --height 1080 schematic/calculator.kicad_pcb
	kicad-cli pcb drc --output $(FAB_DIR)/drc_report.txt schematic/calculator.kicad_pcb
	@echo "Exported to $(FAB_DIR)/"
	ls -lh $(FAB_DIR)/

visualize: export
	@echo "--- Opening Gerber Viewer & 3D Render ---"
	open $(FAB_DIR)/calculator_3d.png
	gerbv $(FAB_DIR)/calculator-F_Cu.gtl $(FAB_DIR)/calculator-B_Cu.gbl $(FAB_DIR)/calculator-Edge_Cuts.gm1 &

# === Hardware Simulation ===

setup:
	@echo "Checking dependencies..."
	@which verilator >/dev/null || (echo "Install verilator: brew install verilator" && exit 1)
	@which qemu-system-arm >/dev/null || (echo "Install qemu: brew install qemu" && exit 1)
	@echo "All dependencies found."

simulate-rtl:
	@echo "--- RTL Simulation ---"
	cd rtl && verilator --top-module top --cc --exe --build -j 0 -Wall -Wno-MULTITOP -Wno-UNUSEDSIGNAL tb_top.cpp top.v alu.v keypad.v display.v
	cd rtl && ./obj_dir/Vtop
	@echo "RTL simulation complete."

simulate-fw:
	@echo "--- Firmware Simulation ---"
	cd firmware && cargo build --target thumbv7m-none-eabi 2>&1
	qemu-system-arm -M lm3s6965evb -nographic -semihosting -kernel firmware/target/thumbv7m-none-eabi/debug/calculator
	@echo "Firmware simulation complete."

check-schematic:
	@echo "--- Schematic Check ---"
	@if which kicad-cli >/dev/null 2>&1; then \
		kicad-cli sch erc schematic/calculator.kicad_sch; \
		echo "Schematic ERC complete."; \
	else \
		echo "kicad-cli not found - install KiCad via 'brew install --cask kicad'"; \
		echo "Skipping schematic check (optional for MVP)."; \
	fi

agent:
	@echo "--- Agent Run ---"
	python3 agent/build_agent.py

clean:
	rm -rf rtl/obj_dir rtl/waveform.vcd firmware/target

.PHONY: all setup simulate-rtl simulate-fw check-schematic agent export visualize simulate simulate-pcb clean

SHELL := /bin/bash
PATH := $(HOME)/.cargo/bin:$(PATH)

all: setup simulate-rtl simulate-fw check-schematic agent

# === PCB Export & Visualization (edit .kicad_pcb in VS Code, then run these) ===

FAB_DIR := fab
export:
	@echo "--- Exporting Gerbers, Drill, and 3D Render ---"
	mkdir -p $(FAB_DIR)
	/opt/homebrew/bin/kicad-cli pcb export gerbers --output $(FAB_DIR) schematic/calculator.kicad_pcb
	/opt/homebrew/bin/kicad-cli pcb export drill   --output $(FAB_DIR) schematic/calculator.kicad_pcb
	/opt/homebrew/bin/kicad-cli pcb export pos     --output $(FAB_DIR) --format csv schematic/calculator.kicad_pcb 2>/dev/null || true
	/opt/homebrew/bin/kicad-cli pcb render --output $(FAB_DIR)/calculator_3d.png --width 1920 --height 1080 schematic/calculator.kicad_pcb
	/opt/homebrew/bin/kicad-cli pcb drc --output $(FAB_DIR)/drc_report.txt schematic/calculator.kicad_pcb
	@echo "Exported to $(FAB_DIR)/"
	ls -lh $(FAB_DIR)/

visualize: export
	@echo "--- Opening Gerber Viewer & 3D Render ---"
	open $(FAB_DIR)/calculator_3d.png
	/opt/homebrew/bin/gerbv $(FAB_DIR)/calculator-F_Cu.gtl $(FAB_DIR)/calculator-B_Cu.gbl $(FAB_DIR)/calculator-Edge_Cuts.gm1 &

visualize-pnp:
	@echo "--- Pick-and-Place Head Travel Animation ---"
	$(HOME)/calc-venv/bin/python3 agent/visualize_pnp.py --save gif
	@echo "Animation saved to $(FAB_DIR)/placement.gif"
	open $(FAB_DIR)/placement.gif

analyze-pnp:
	@echo "--- SMT Trajectory Analysis ---"
	$(HOME)/calc-venv/bin/python3 agent/analyze_pnp.py --all
	@echo "Outputs:"
	@ls -lh $(FAB_DIR)/trajectory_analysis.png $(FAB_DIR)/optimization_compare.png $(FAB_DIR)/trajectory.gif $(FAB_DIR)/trajectory_analysis.gif
	open $(FAB_DIR)/trajectory_analysis.png

# === Hardware Simulation ===

setup:
	@echo "Checking dependencies..."
	@test -x /opt/homebrew/bin/verilator || (echo "Install verilator: brew install verilator" && exit 1)
	@test -x /opt/homebrew/bin/qemu-system-arm || (echo "Install qemu: brew install qemu" && exit 1)
	@echo "All dependencies found."

simulate-rtl:
	@echo "--- RTL Simulation ---"
	cd rtl && /opt/homebrew/bin/verilator --top-module top --cc --exe --build -j 0 -Wall -Wno-MULTITOP -Wno-UNUSEDSIGNAL tb_top.cpp top.v alu.v keypad.v display.v
	cd rtl && ./obj_dir/Vtop
	@echo "RTL simulation complete."

FIRMWARE_ELF := firmware/target/thumbv7m-none-eabi/debug/calculator
FIRMWARE_BIN := $(FIRMWARE_ELF).bin

# Build ELF then convert to flat binary (required for correct VMA 0x0 loading)
$(FIRMWARE_BIN): $(FIRMWARE_ELF)
	rust-objcopy -O binary $< $@

$(FIRMWARE_ELF):
	cd firmware && RUSTFLAGS="-C link-arg=-Tlink.ld" cargo build --target thumbv7m-none-eabi 2>&1

simulate-fw: $(FIRMWARE_BIN)
	@echo "--- Firmware Simulation (type calculator keys, Ctrl-C to exit) ---"
	/opt/homebrew/bin/qemu-system-arm -M lm3s6965evb -serial stdio -kernel $(FIRMWARE_BIN)

check-schematic:
	@echo "--- Schematic Check ---"
	@if which /opt/homebrew/bin/kicad-cli >/dev/null 2>&1; then \
		/opt/homebrew/bin/kicad-cli sch erc schematic/calculator.kicad_sch; \
		echo "Schematic ERC complete."; \
	else \
		echo "/opt/homebrew/bin/kicad-cli not found - install KiCad via 'brew install --cask kicad'"; \
		echo "Skipping schematic check (optional for MVP)."; \
	fi

simulate: $(FIRMWARE_BIN)
	@echo "--- Interactive QEMU Calculator (close GUI to exit) ---"
	$$HOME/calc-venv/bin/python3 simulator/gui.py

simulate-pcb: $(FIRMWARE_BIN)
	@echo "--- Interactive QEMU Calculator on PCB (close GUI to exit) ---"
	$$HOME/calc-venv/bin/python3 simulator/pcb_gui.py

agent:
	@echo "--- Agent Run ---"
	python3 agent/build_agent.py

clean:
	rm -rf rtl/obj_dir rtl/waveform.vcd firmware/target

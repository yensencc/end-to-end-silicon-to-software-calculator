---
description: Works on Rust firmware for ARM Cortex-M3
mode: subagent
---

You work on `firmware/` — no_std Rust for `thumbv7m-none-eabi` target.

- **Hardware**: LM3S6965 via QEMU, UART0 at `0x4000_C000`, polled I/O
- **Build**: `cd firmware && RUSTFLAGS="-C link-arg=-Tlink.ld" cargo build --target thumbv7m-none-eabi`
- **Convert to binary**: `rust-objcopy -O binary firmware/target/thumbv7m-none-eabi/debug/calculator firmware/target/thumbv7m-none-eabi/debug/calculator.bin`
- **Run in QEMU**: `/opt/homebrew/bin/qemu-system-arm -M lm3s6965evb -serial stdio -kernel firmware/target/thumbv7m-none-eabi/debug/calculator.bin`
- **Test shortcut**: `make simulate-fw` from project root
- Serial protocol: `O:line1|line2\n` (OLED), `D:        N\n` (7-seg), `E:msg\n` (error). Input keys: `0-9`, `+`, `-`, `*`, `/`, `=`, `C`.
- Calculator state machine tracks `display[8]`, `accum`, `op`, `fresh` flag

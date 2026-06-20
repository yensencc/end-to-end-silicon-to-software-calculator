#!/usr/bin/env python3
"""
Interactive calculator simulator: QEMU Cortex-M3 + UART + Tkinter GUI.

Usage:
  python simulator/gui.py

Launches QEMU with the firmware, opens a calculator window with a
7-segment numeric display, an OLED status panel, and a keypad.
Key presses are sent via QEMU's serial stdin; display updates are
received from QEMU's serial stdout.
"""

import subprocess
import time
import tkinter as tk
import os
import sys
import fcntl

FIRMWARE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firmware")
FIRMWARE_ELF = os.path.join(FIRMWARE_DIR,
                             "target/thumbv7m-none-eabi/debug/calculator")
FIRMWARE_BIN = FIRMWARE_ELF + ".bin"
QEMU = "/opt/homebrew/bin/qemu-system-arm"


class CalculatorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Calculator MVP  —  QEMU Cortex-M3")
        self.root.resizable(False, False)

        self.process = None
        self.running = True
        self.display_text = tk.StringVar(value="       0")
        self.oled_lines = ["", ""]
        self._line_buf = ""

        self._build_ui()
        self._launch_qemu()
        self.status.config(text="Starting QEMU...")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_serial)

    def _build_ui(self):
        # ── 7-segment style display ──
        display_frame = tk.Frame(self.root)
        display_frame.pack(fill="x", padx=10, pady=(10, 2))

        disp_canvas = tk.Canvas(display_frame, width=400, height=80,
                                 bg="white", highlightthickness=0)
        disp_canvas.pack()
        self.disp_canvas = disp_canvas

        # 8-digit LCD segments
        self.seg_digits = []
        seg_w = 42
        gap = 6
        start_x = 20
        for i in range(8):
            x = start_x + i * (seg_w + gap)
            seg = SevenSegment(disp_canvas, x, 12, seg_w, 56, i)
            self.seg_digits.append(seg)

        # ── OLED panel (main user display) ──
        oled_frame = tk.Frame(self.root)
        oled_frame.pack(fill="x", padx=10, pady=(2, 10))
        self.oled_canvas = tk.Canvas(oled_frame, width=400, height=64,
                                      bg="#f0f4ff", highlightthickness=0)
        self.oled_canvas.pack()
        self.oled_canvas.create_text(4, 2, text="OLED", anchor="nw",
            fill="#888", font=("Courier", 7))
        self.oled_line1 = self.oled_canvas.create_text(200, 18, text="",
            fill="#036", font=("Courier", 16, "bold"), anchor="center")
        self.oled_line2 = self.oled_canvas.create_text(200, 42, text="",
            fill="#036", font=("Courier", 16, "bold"), anchor="center")

        # ── Keypad ──
        keypad = tk.Frame(self.root)
        keypad.pack(padx=10, pady=(0, 10))

        key_defs = [
            ("7", "8", "9", "/"),
            ("4", "5", "6", "*"),
            ("1", "2", "3", "-"),
            ("C", "0", "=", "+"),
        ]

        self.key_send = {
            "0": b"0", "1": b"1", "2": b"2", "3": b"3",
            "4": b"4", "5": b"5", "6": b"6", "7": b"7",
            "8": b"8", "9": b"9",
            "+": b"+", "-": b"-", "*": b"*", "/": b"/",
            "=": b"=", "C": b"C",
        }

        for row_keys in key_defs:
            row = tk.Frame(keypad)
            row.pack()
            for k in row_keys:
                bg = "#d45" if k == "C" else "#e82" if k == "=" else "#555"
                fg = "white"
                btn = tk.Button(row, text=k, font=("Courier", 16, "bold"),
                                width=4, height=2, bg=bg, fg=fg,
                                activebackground="#777",
                                command=lambda key=k: self._send_key(key))
                btn.pack(side="left", padx=3, pady=3)

        # Status bar
        self.status = tk.Label(self.root, text="Starting QEMU...",
                                bg="#eee", fg="#666", anchor="w",
                                font=("Courier", 9))
        self.status.pack(fill="x", padx=10)

    def _launch_qemu(self):
        # Build firmware with flat binary
        env = os.environ.copy()
        env["RUSTFLAGS"] = "-C link-arg=-Tlink.ld"
        build = subprocess.run(
            ["cargo", "build", "--target", "thumbv7m-none-eabi"],
            cwd=FIRMWARE_DIR, capture_output=True, text=True, env=env)
        if build.returncode != 0:
            self.status.config(text="Firmware build FAILED")
            self.running = False
            return
        # Convert ELF to flat binary
        subprocess.run(
            ["rust-objcopy", "-O", "binary", FIRMWARE_BIN[:-4], FIRMWARE_BIN],
            capture_output=True)

        # Launch QEMU with serial over stdio (via -nographic)
        # Note: -serial tcp is not used because QEMU 11 on macOS 15.6
        # has a compatibility issue with the TCP chardev backend.
        cmd = [
            QEMU, "-M", "lm3s6965evb",
            "-nographic",
            "-kernel", FIRMWARE_BIN,
        ]
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0)
        # Set stdout to non-blocking so _poll_serial never hangs
        fl = fcntl.fcntl(self.process.stdout, fcntl.F_GETFL)
        fcntl.fcntl(self.process.stdout, fcntl.F_SETFL, fl | os.O_NONBLOCK)
        # Let QEMU boot before first poll
        time.sleep(2)
        self.status.config(text="Running")

    def _send_key(self, key):
        if self.process and self.process.stdin:
            data = self.key_send.get(key)
            if data:
                try:
                    self.process.stdin.write(data)
                    self.process.stdin.flush()
                except Exception:
                    self.status.config(text="Connection lost")
                    self.process = None

    def _poll_serial(self):
        if not self.running:
            return
        if self.process and self.process.stdout:
            try:
                data = os.read(self.process.stdout.fileno(), 4096)
                if data:
                    self._line_buf += data.decode(errors="replace")
                    while "\n" in self._line_buf:
                        raw, self._line_buf = self._line_buf.split("\n", 1)
                        line = raw.strip("\r")
                        if line:
                            self._handle_serial_line(line)
            except BlockingIOError:
                pass
            except (BrokenPipeError, OSError):
                self.status.config(text="Connection lost")
                self.process = None
        self.root.after(50, self._poll_serial)

    def _handle_serial_line(self, line):
        if line.startswith("D:"):
            val_str = line[3:]
            self._update_display(val_str)
        elif line.startswith("O:"):
            parts = line[2:].split("|", 1)
            l1 = parts[0].strip() if parts else ""
            l2 = parts[1].strip() if len(parts) > 1 else ""
            self.oled_lines = [l1, l2]
            self.oled_canvas.itemconfig(self.oled_line1, text=l1)
            self.oled_canvas.itemconfig(self.oled_line2, text=l2)
            self.status.config(text=f"OLED: {l1}  |  {l2}" if l2 else f"OLED: {l1}")
        elif line.startswith("E:"):
            self._update_display("Error   ")
            self.status.config(text=line[2:])
        elif line:
            self.status.config(text=line[:50])

    def _update_display(self, val_str):
        raw = val_str.ljust(8)[:8]
        self.display_text.set(raw)
        for i, ch in enumerate(raw):
            self.seg_digits[i].set_char(ch)

    def _on_close(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


class SevenSegment:
    """Simplified 7-segment display digit."""
    # Segment mapping: which dots belong to each digit character
    SEGMENTS = {
        '0': (1,1,1,1,1,1,0),
        '1': (0,1,1,0,0,0,0),
        '2': (1,1,0,1,1,0,1),
        '3': (1,1,1,1,0,0,1),
        '4': (0,1,1,0,0,1,1),
        '5': (1,0,1,1,0,1,1),
        '6': (1,0,1,1,1,1,1),
        '7': (1,1,1,0,0,0,0),
        '8': (1,1,1,1,1,1,1),
        '9': (1,1,1,1,0,1,1),
        '-': (0,0,0,0,0,0,1),
        ' ': (0,0,0,0,0,0,0),
        'E': (1,0,0,1,1,1,1),
        'r': (0,0,0,0,1,0,1),
    }

    def __init__(self, canvas, x, y, w, h, index):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.index = index
        self.seg_ids = []
        self._draw_segments()
        self.set_char(' ')

    def _draw_segments(self):
        x, y, w, h = self.x, self.y, self.w, self.h
        t = 2  # segment thickness
        hw = max(t, w // 6)  # horizontal segment width
        vw = max(t, w // 6)   # vertical segment width

        cx = x + w / 2
        cy = y + h / 2

        # Segment coordinates (a..g)
        segs = {
            'a': (x + vw, y, x + w - vw, y + hw),     # top horizontal
            'b': (x + w - vw, y + hw, x + w, cy),      # top-right vertical
            'c': (x + w - vw, cy, x + w, y + h - hw),  # bottom-right vertical
            'd': (x + vw, y + h - hw, x + w - vw, y + h),  # bottom horizontal
            'e': (x, y + h - hw, x + vw, cy),           # bottom-left vertical
            'f': (x, y + hw, x + vw, cy),               # top-left vertical
            'g': (x + vw, cy - hw // 2, x + w - vw, cy + hw // 2),  # middle horizontal
        }

        self.seg_ids = {}
        for name, (x1, y1, x2, y2) in segs.items():
            # Draw as rectangle for thicker segments
            if name in ('a', 'd', 'g'):
                # Horizontal
                rid = self.canvas.create_rectangle(
                    x1, y1, x2, y2, fill="#1a1a1a", outline="", width=0)
            else:
                # Vertical
                rid = self.canvas.create_rectangle(
                    x1, y1, x2, y2, fill="#1a1a1a", outline="", width=0)
            self.seg_ids[name] = rid

    def set_char(self, ch):
        on_color = "#080"
        off_color = "#ddd"
        segments = self.SEGMENTS.get(ch, (0,0,0,0,0,0,0))
        names = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
        for name, state in zip(names, segments):
            color = on_color if state else off_color
            self.canvas.itemconfig(self.seg_ids[name], fill=color)


def main():
    gui = CalculatorGUI()
    gui.run()


if __name__ == "__main__":
    main()

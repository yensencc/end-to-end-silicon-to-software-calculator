#!/usr/bin/env python3
"""
Interactive calculator simulator: QEMU Cortex-M3 + UART + Tkinter GUI.

Usage:
  python simulator/gui.py

Launches QEMU with the firmware, opens a calculator window with a
numeric display and keypad. Key presses are sent via UART, display
updates are received and shown on the 7-segment-style LED.
"""

import subprocess
import time
import socket
import tkinter as tk
import os
import sys

FIRMWARE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firmware")
FIRMWARE_ELF = os.path.join(FIRMWARE_DIR,
                             "target/thumbv7m-none-eabi/debug/calculator")
QEMU = "/opt/homebrew/bin/qemu-system-arm"


class CalculatorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Calculator MVP  —  QEMU Cortex-M3")
        self.root.resizable(False, False)

        self.process = None
        self.sock = None
        self.running = True
        self.display_text = tk.StringVar(value="       0")

        self._build_ui()
        self._launch_qemu()
        self.root.after(500, self._connect_serial)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_serial)

    def _build_ui(self):
        # ── 7-segment style display ──
        display_frame = tk.Frame(self.root, bg="#222", padx=10, pady=10)
        display_frame.pack(fill="x")

        disp_canvas = tk.Canvas(display_frame, width=400, height=80,
                                 bg="#1a1a1a", highlightthickness=2,
                                 highlightbackground="#444")
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

        # ── Keypad ──
        keypad = tk.Frame(self.root, padx=10, pady=10, bg="#333")
        keypad.pack()

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
            row = tk.Frame(keypad, bg="#333")
            row.pack()
            for k in row_keys:
                bg = "#d45" if k == "C" else "#e82" if k == "=" else "#555"
                fg = "white"
                btn = tk.Button(row, text=k, font=("Courier", 16, "bold"),
                                width=4, height=2, bg=bg, fg=fg,
                                activebackground="#777",
                                command=lambda key=k: self._press_key(key))
                btn.pack(side="left", padx=3, pady=3)

        # Status bar
        self.status = tk.Label(self.root, text="Connecting to QEMU...",
                                bg="#222", fg="#aaa", anchor="w", padx=10)
        self.status.pack(fill="x")

    def _launch_qemu(self):
        # Build firmware first
        build = subprocess.run(
            ["cargo", "build", "--target", "thumbv7m-none-eabi"],
            cwd=FIRMWARE_DIR, capture_output=True, text=True)
        if build.returncode != 0:
            self.status.config(text="Firmware build FAILED")
            print(build.stderr)
            self.running = False
            return

        # Launch QEMU with serial via TCP (no PTY to parse)
        cmd = [
            QEMU, "-M", "lm3s6965evb",
            "-nographic",
            "-serial", "tcp::12345,server,nowait",
            "-kernel", FIRMWARE_ELF,
        ]
        self.process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _connect_serial(self):
        import socket, time
        for attempt in range(10):
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(1)
                self.sock.connect(("127.0.0.1", 12345))
                self.sock.settimeout(0.05)
                self.status.config(text="Running")
                return
            except Exception:
                time.sleep(0.5)
        self.status.config(text="Failed to connect to QEMU")

    def _send_key(self, key):
        if self.sock:
            data = self.key_send.get(key)
            if data:
                try:
                    self.sock.sendall(data)
                except Exception:
                    self.status.config(text="Connection lost")
                    self.sock = None

    def _poll_serial(self):
        if not self.running:
            return
        if self.sock:
            try:
                data = self.sock.recv(4096)
                if data:
                    for line in data.decode(errors="replace").split("\n"):
                        line = line.strip()
                        if line:
                            self._handle_serial_line(line)
            except socket.timeout:
                pass
            except (ConnectionResetError, BrokenPipeError, OSError):
                self.status.config(text="Connection lost")
                self.sock = None
        self.root.after(50, self._poll_serial)

    def _handle_serial_line(self, line):
        if line.startswith("D:"):
            val_str = line[2:].strip()
            self._update_display(val_str)
        elif line.startswith("E:"):
            self._update_display("Error   ")
            self.status.config(text=line[2:])
        elif line:
            self.status.config(text=line[:50])

    def _update_display(self, val_str):
        # val_str is 8 characters: right-aligned number with leading spaces
        self.display_text.set(val_str)
        for i, ch in enumerate(val_str):
            if i < 8:
                self.seg_digits[i].set_char(ch)

    def _on_close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except Exception:
                self.process.kill()
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
        on_color = "#00ff88"
        off_color = "#2a2a2a"
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

#!/usr/bin/env python3
"""
PCB-based interactive calculator simulator.
Shows the actual PCB design as the interface — click switches
at their real positions on the board, see the 7-segment display
and OLED panel update live, all backed by real firmware on
QEMU Cortex-M3 (serial over stdio).

Usage:
  python simulator/pcb_gui.py
"""

import subprocess
import time
import tkinter as tk
import os
import sys
import fcntl

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIRMWARE_DIR = os.path.join(BASE, "firmware")
FIRMWARE_ELF = os.path.join(FIRMWARE_DIR,
                             "target/thumbv7m-none-eabi/debug/calculator")
FIRMWARE_BIN = FIRMWARE_ELF + ".bin"
QEMU = "/opt/homebrew/bin/qemu-system-arm"

BOARD_W_MM = 62.0
BOARD_H_MM = 42.0
SCALE = 2.0
W = int(468 * SCALE)
H = int(317 * SCALE)

SWITCHES = [
    ("SW1",  12, -16, "7"), ("SW2",  22, -16, "8"),
    ("SW3",  32, -16, "9"), ("SW4",  42, -16, "/"),
    ("SW5",  12, -21, "4"), ("SW6",  22, -21, "5"),
    ("SW7",  32, -21, "6"), ("SW8",  42, -21, "*"),
    ("SW9",  12, -26, "1"), ("SW10", 22, -26, "2"),
    ("SW11", 32, -26, "3"), ("SW12", 42, -26, "-"),
    ("SW13", 12, -31, "C"), ("SW14", 22, -31, "0"),
    ("SW15", 32, -31, "="), ("SW16", 42, -31, "+"),
]

DISP_X, DISP_Y = 10, -35


def mm_to_canvas(x_mm, y_mm):
    cx = (x_mm / BOARD_W_MM) * W
    cy = H - ((-y_mm) / BOARD_H_MM) * H
    return cx, cy


class SevenSegment:
    SEGMENTS = {
        '0': (1,1,1,1,1,1,0), '1': (0,1,1,0,0,0,0),
        '2': (1,1,0,1,1,0,1), '3': (1,1,1,1,0,0,1),
        '4': (0,1,1,0,0,1,1), '5': (1,0,1,1,0,1,1),
        '6': (1,0,1,1,1,1,1), '7': (1,1,1,0,0,0,0),
        '8': (1,1,1,1,1,1,1), '9': (1,1,1,1,0,1,1),
        '-': (0,0,0,0,0,0,1), ' ': (0,0,0,0,0,0,0),
        'E': (1,0,0,1,1,1,1), 'r': (0,0,0,0,1,0,1),
    }

    def __init__(self, canvas, x, y, w, h):
        self.canvas = canvas
        self.x, self.y, self.w, self.h = x, y, w, h
        self.seg_ids = {}
        self._draw()

    def _draw(self):
        x, y, w, h = self.x, self.y, self.w, self.h
        t = max(2, w // 6)
        hw = t
        vw = t
        cx = x + w / 2
        cy = y + h / 2
        segs = {
            'a': (x + vw, y, x + w - vw, y + hw),
            'b': (x + w - vw, y + hw, x + w, cy),
            'c': (x + w - vw, cy, x + w, y + h - hw),
            'd': (x + vw, y + h - hw, x + w - vw, y + h),
            'e': (x, y + h - hw, x + vw, cy),
            'f': (x, y + hw, x + vw, cy),
            'g': (x + vw, cy - hw // 2, x + w - vw, cy + hw // 2),
        }
        for name, (x1, y1, x2, y2) in segs.items():
            rid = self.canvas.create_rectangle(
                x1, y1, x2, y2, fill="#1a1a1a", outline="", width=0)
            self.seg_ids[name] = rid

    def set_char(self, ch):
        on = "#00ff88"
        off = "#1a1a1a"
        segs = self.SEGMENTS.get(ch, (0,0,0,0,0,0,0))
        for name, state in zip(['a','b','c','d','e','f','g'], segs):
            self.canvas.itemconfig(self.seg_ids[name], fill=on if state else off)


class PcbCalculatorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Calculator PCB  —  QEMU Cortex-M3")
        self.root.resizable(False, False)

        self.process = None
        self.running = True
        self.oled_lines = ["", ""]
        self._line_buf = ""

        self.buttons = {}
        self._build_ui()
        self._launch_qemu()
        self.status_label.config(text="Starting QEMU...")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_serial)

    def _build_ui(self):
        main = tk.Frame(self.root)
        main.pack()

        # Canvas
        self.canvas = tk.Canvas(main, width=W, height=H, bg="white",
                                highlightthickness=0)
        self.canvas.pack()

        # Status bar
        self.status = tk.Frame(main, height=24)
        self.status.pack(fill="x")
        self.status_label = tk.Label(
            self.status, text="Connecting to QEMU...",
            bg="#eee", fg="#666", font=("Courier", 9), anchor="w", padx=10)
        self.status_label.pack(fill="both", expand=True)

        # Draw switches
        for ref, px, py, key in SWITCHES:
            cx, cy = mm_to_canvas(px, py)
            r = 6 * SCALE
            tag = f"sw_{ref}"

            btn_outer = self.canvas.create_oval(
                cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2,
                fill="", outline="#555", width=1, tags=(tag,))
            btn = self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill="#222", outline="#888", width=2,
                stipple="gray25", tags=(tag,))
            lbl_bg = self.canvas.create_rectangle(
                cx - 10, cy + r + 2, cx + 10, cy + r + 22,
                fill="#111", outline="", tags=(tag,))
            lbl = self.canvas.create_text(
                cx, cy + r + 12, text=key, fill="#eee",
                font=("Courier", int(11 * SCALE), "bold"),
                tags=(tag,))

            self.buttons[tag] = {
                "key": key,
                "items": (btn_outer, btn, lbl_bg, lbl),
                "cx": cx, "cy": cy, "r": r,
            }
            self.canvas.tag_bind(tag, "<Button-1>",
                                 lambda e, t=tag: self._press_key(t))

        # Draw 7-segment display
        dcx, dcy = mm_to_canvas(DISP_X, DISP_Y)
        disp_w = 14 * SCALE
        disp_h = 20 * SCALE
        gap = 3 * SCALE
        total_w = 8 * disp_w + 7 * gap
        start_x = dcx - total_w / 2
        start_y = dcy - disp_h / 2

        bg_rect = self.canvas.create_rectangle(
            start_x - 4, start_y - 4,
            start_x + total_w + 4, start_y + disp_h + 4,
            fill="#0a0a0a", outline="#444", width=2, tags="disp_bg")

        self.seg_digits = []
        for i in range(8):
            x = start_x + i * (disp_w + gap)
            seg = SevenSegment(self.canvas, x, start_y, disp_w, disp_h)
            self.seg_digits.append(seg)

        # OLED display below 7-seg (main user display)
        oled_y = start_y + disp_h + 14
        oled_w = int(total_w * 0.85)
        oled_h = int(14 * SCALE)
        oled_x = dcx - oled_w / 2
        self.canvas.create_rectangle(
            oled_x - 2, oled_y - 2,
            oled_x + oled_w + 2, oled_y + oled_h + 2,
            fill="#f0f4ff", outline="#888", width=1, tags="oled_bg")
        self.oled_text_id = self.canvas.create_text(
            dcx, oled_y + oled_h / 2, text="",
            fill="#036", font=("Courier", int(10 * SCALE), "bold"),
            anchor="center", tags="oled_text")

    def _launch_qemu(self):
        env = os.environ.copy()
        env["RUSTFLAGS"] = "-C link-arg=-Tlink.ld"
        build = subprocess.run(
            ["cargo", "build", "--target", "thumbv7m-none-eabi"],
            cwd=FIRMWARE_DIR, capture_output=True, text=True, env=env)
        if build.returncode != 0:
            self.status_label.config(text="FIRMWARE BUILD FAILED")
            self.running = False
            return
        # Convert ELF to flat binary
        subprocess.run(
            ["rust-objcopy", "-O", "binary", FIRMWARE_ELF, FIRMWARE_BIN],
            capture_output=True)

        cmd = [
            QEMU, "-M", "lm3s6965evb",
            "-nographic",
            "-kernel", FIRMWARE_BIN,
        ]
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0)
        fl = fcntl.fcntl(self.process.stdout, fcntl.F_GETFL)
        fcntl.fcntl(self.process.stdout, fcntl.F_SETFL, fl | os.O_NONBLOCK)
        self.status_label.config(text="Running")

    def _press_key(self, tag):
        info = self.buttons.get(tag)
        if not info:
            return
        key = info["key"]
        r = info["r"]
        cx, cy = info["cx"], info["cy"]

        press = self.canvas.create_oval(
            cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2,
            fill="#4a4", outline="#4a4", width=0, tags="press_feedback")
        self.root.after(150, lambda: self.canvas.delete(press))

        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(key.encode())
                self.process.stdin.flush()
            except Exception:
                self.status_label.config(text="Connection lost")
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
                            self._handle_line(line)
            except BlockingIOError:
                pass
            except (BrokenPipeError, OSError):
                self.status_label.config(text="Connection lost")
                self.process = None
        self.root.after(50, self._poll_serial)

    def _handle_line(self, line):
        if line.startswith("D:"):
            raw = line[3:]
            raw = raw.ljust(8)[:8]
            for i, ch in enumerate(raw):
                self.seg_digits[i].set_char(ch)
        elif line.startswith("O:"):
            parts = line[2:].split("|", 1)
            l1 = parts[0].strip() if parts else ""
            l2 = parts[1].strip() if len(parts) > 1 else ""
            self.oled_lines = [l1, l2]
            text = l1
            if l2:
                text += "  |  " + l2
            self.canvas.itemconfig(self.oled_text_id, text=text)
            self.status_label.config(text=f"OLED: {l1}  |  {l2}" if l2 else f"OLED: {l1}")
        elif line.startswith("E:"):
            for seg in self.seg_digits:
                seg.set_char("E")
            self.status_label.config(text=line[2:])
        elif line:
            self.status_label.config(text=line[:50])

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


def main():
    gui = PcbCalculatorGUI()
    gui.run()


if __name__ == "__main__":
    main()

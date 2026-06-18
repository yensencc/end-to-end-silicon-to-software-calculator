#!/usr/bin/env python3
import subprocess
import sys
import os

STEPS = [
    ("RTL Compile",   ["make", "simulate-rtl"]),
    ("Firmware Build", ["make", "simulate-fw"]),
    ("Schematic Check", ["make", "check-schematic"]),
]

def run_step(name, cmd):
    print(f"\n{'='*50}")
    print(f"STEP: {name}")
    print(f"{'='*50}")
    result = subprocess.run(cmd, capture_output=False, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return result.returncode == 0

def main():
    results = []
    for name, cmd in STEPS:
        ok = run_step(name, cmd)
        results.append((name, ok))
        if not ok:
            print(f"\nFAILED: {name}")
            break

    print(f"\n{'='*50}")
    print("FINAL REPORT")
    print(f"{'='*50}")
    all_pass = True
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {name}")

    print(f"\nResult: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    sys.exit(0 if all_pass else 1)

if __name__ == "__main__":
    main()

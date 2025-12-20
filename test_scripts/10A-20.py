#!/usr/bin/env python3
"""
10A-20.py — AD3 D Flip-Flop miniPCB functional test (hard-coded)

WIRING (fixed):
  DIO4 -> D
  DIO5 -> CLK
  DIO6 <- Q
  DIO7 <- /Q
  AD3 V+ -> board VCC  (script sets V+ = +5.0V)
  AD3 GND -> board GND

What you should see:
  - Terminal prints Python path, device found, power enabled, then PASS/FAIL.
  - Writes a JSON log file: dff_test_log.json
"""

from __future__ import annotations

import json
import random
import sys
import time
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, List, Dict, Any


# ---------------------------
# HARD-CODED TEST CONFIG
# ---------------------------
PIN_D   = 4
PIN_CLK = 5
PIN_Q   = 6
PIN_NQ  = 7

ENABLE_VPLUS = True
VPLUS_VOLTS = 5.0

ACTIVE_EDGE = "rising"   # "rising" or "falling"
SETUP_MS = 5.0
PULSE_MS = 2.0
PROP_MS  = 2.0
HOLDCHECK_MS = 5.0

RANDOM_CYCLES = 16
RNG_SEED = 1

LOG_JSON = "dff_test_log.json"
VERBOSE = True
# ---------------------------


@dataclass
class Sample:
    t_s: float
    d: int
    clk: int
    q: Optional[int]
    nq: Optional[int]


@dataclass
class Failure:
    step: str
    d: int
    clk: int
    q: Optional[int]
    nq: Optional[int]
    expected_q: Optional[int]
    expected_nq: Optional[int]
    note: str


def _b2i(x: bool) -> int:
    return 1 if x else 0


def main() -> int:
    print("=== AD3 DFF TEST (hard-coded) ===")
    print(f"Python: {sys.executable}")
    print(f"Version: {sys.version.split()[0]}")
    print("")

    try:
        import dwfpy as dwf
    except ModuleNotFoundError:
        print("ERROR: dwfpy is not installed in THIS interpreter environment.")
        print("Install it into the interpreter shown above with:\n")
        print(f'  "{sys.executable}" -m pip install --upgrade pip')
        print(f'  "{sys.executable}" -m pip install dwfpy\n')
        print("If you're in VS Code: Select Interpreter -> your .venv python, then reinstall.")
        return 2

    random.seed(RNG_SEED)

    setup_s = SETUP_MS / 1000.0
    pulse_s = PULSE_MS / 1000.0
    prop_s = PROP_MS / 1000.0
    holdcheck_s = HOLDCHECK_MS / 1000.0

    samples: List[Sample] = []
    failures: List[Failure] = []

    def log_sample(dv: int, clkv: int, qv: Optional[int], nqv: Optional[int]) -> None:
        samples.append(Sample(t_s=time.time(), d=dv, clk=clkv, q=qv, nq=nqv))

    def fail(step: str, dv: int, clkv: int, qv: Optional[int], nqv: Optional[int],
             exp_q: Optional[int], exp_nq: Optional[int], note: str) -> None:
        failures.append(Failure(step, dv, clkv, qv, nqv, exp_q, exp_nq, note))
        if VERBOSE:
            print(f"[FAIL] {step}: D={dv} CLK={clkv} Q={qv} /Q={nqv} expected Q={exp_q} /Q={exp_nq} :: {note}")

    # Try opening the first available WaveForms device
    try:
        with dwf.Device() as device:
            print(f"Found device: {getattr(device, 'name', 'Unknown')} ({getattr(device, 'serial_number', 'Unknown')})")

            # ---------- Power Supplies (V+) ----------
            # Uses dwfpy AnalogIO generic channel/node access:
            # channel 0 is typically V+, node 1 voltage, node 0 enable; then master_enable.
            def enable_vplus(volts: float) -> None:
                device.analog_io[0][1].value = float(volts)     # voltage node
                device.analog_io[0][0].value = True             # enable node
                device.analog_io.master_enable = True           # master enable

            def disable_vplus() -> None:
                try:
                    device.analog_io[0][0].value = False
                    device.analog_io.master_enable = False
                except Exception:
                    pass

            if ENABLE_VPLUS:
                try:
                    print(f"Enabling V+ = {VPLUS_VOLTS:.3f} V ...")
                    enable_vplus(VPLUS_VOLTS)
                    time.sleep(0.15)
                except Exception as e:
                    print("WARNING: Could not enable V+ from Python.")
                    print("         You can still run the digital test if the board is powered externally.")
                    print(f"         Details: {e}")
                    print("")

            # ---------- Digital IO ----------
            io = device.digital_io

            # Drive D and CLK
            io[PIN_D].setup(enabled=True, state=False)
            io[PIN_CLK].setup(enabled=True, state=False)

            # Read Q and /Q
            io[PIN_Q].setup(enabled=False)
            io[PIN_NQ].setup(enabled=False, configure=True)

            driven_d = 0
            driven_clk = 0

            def set_d(v: int) -> None:
                nonlocal driven_d
                driven_d = 1 if v else 0
                io[PIN_D].output_state = bool(driven_d)

            def set_clk(v: int) -> None:
                nonlocal driven_clk
                driven_clk = 1 if v else 0
                io[PIN_CLK].output_state = bool(driven_clk)

            def read_q_nq() -> Tuple[Optional[int], Optional[int]]:
                try:
                    io.read_status()
                    return _b2i(io[PIN_Q].input_state), _b2i(io[PIN_NQ].input_state)
                except Exception:
                    return None, None

            def expect(step: str, exp_q: Optional[int], exp_nq: Optional[int], note: str = "") -> None:
                qv, nqv = read_q_nq()
                log_sample(driven_d, driven_clk, qv, nqv)

                ok = True
                if exp_q is not None and qv != exp_q:
                    ok = False
                if exp_nq is not None and nqv != exp_nq:
                    ok = False
                if qv is not None and nqv is not None and qv == nqv:
                    ok = False
                    note = (note + " | " if note else "") + "Sanity: Q and /Q are identical (should be complements)."

                if not ok:
                    fail(step, driven_d, driven_clk, qv, nqv, exp_q, exp_nq, note)
                elif VERBOSE:
                    print(f"[ OK ] {step}: D={driven_d} CLK={driven_clk} Q={qv} /Q={nqv}")

            def pulse_active_edge() -> None:
                if ACTIVE_EDGE == "rising":
                    set_clk(0)
                    time.sleep(0.001)
                    set_clk(1)          # active edge
                    time.sleep(pulse_s)
                    set_clk(0)
                else:
                    set_clk(1)
                    time.sleep(0.001)
                    set_clk(0)          # active edge
                    time.sleep(pulse_s)
                    set_clk(1)

            # ---------- Quick smoke read ----------
            set_clk(0 if ACTIVE_EDGE == "rising" else 1)
            set_d(0)
            q0, nq0 = read_q_nq()
            print(f"Initial read: Q={q0} /Q={nq0}")
            print("Starting functional test...\n")

            # ---------- Prime ----------
            set_d(0)
            time.sleep(setup_s)
            pulse_active_edge()
            time.sleep(prop_s)
            expect("prime_to_0", 0, 1, "Priming with D=0")

            set_d(1)
            time.sleep(setup_s)
            pulse_active_edge()
            time.sleep(prop_s)
            expect("prime_to_1", 1, 0, "Priming with D=1")

            # ---------- Pattern ----------
            pattern = [0, 1, 0, 1, 1, 0, 0, 1]
            for i, dv in enumerate(pattern):
                q_before, nq_before = read_q_nq()
                log_sample(driven_d, driven_clk, q_before, nq_before)

                set_d(dv)
                time.sleep(setup_s)

                q_hold, nq_hold = read_q_nq()
                log_sample(driven_d, driven_clk, q_hold, nq_hold)

                if q_before is not None and q_hold is not None and q_before != q_hold:
                    fail(f"hold_no_clock_change_{i}", driven_d, driven_clk, q_hold, nq_hold,
                         q_before, (1 - q_before) if q_before in (0, 1) else None,
                         "Q changed after D changed without a clock edge.")

                pulse_active_edge()
                time.sleep(prop_s)
                expect(f"pattern_clock_{i}", dv, 1 - dv, "Latch check")

                set_d(1 - dv)
                time.sleep(holdcheck_s)
                expect(f"post_edge_hold_{i}", dv, 1 - dv, "Hold check")

            # ---------- Random ----------
            for i in range(RANDOM_CYCLES):
                dv = random.randint(0, 1)
                set_d(dv)
                time.sleep(setup_s)
                pulse_active_edge()
                time.sleep(prop_s)
                expect(f"random_clock_{i}", dv, 1 - dv, "Random latch check")

            passed = (len(failures) == 0)

            report: Dict[str, Any] = {
                "passed": passed,
                "device": {"name": getattr(device, "name", None), "serial_number": getattr(device, "serial_number", None)},
                "config": {
                    "pins": {"D": PIN_D, "CLK": PIN_CLK, "Q": PIN_Q, "nQ": PIN_NQ},
                    "vplus_volts": VPLUS_VOLTS if ENABLE_VPLUS else None,
                    "edge": ACTIVE_EDGE,
                    "setup_ms": SETUP_MS,
                    "pulse_ms": PULSE_MS,
                    "prop_ms": PROP_MS,
                    "holdcheck_ms": HOLDCHECK_MS,
                    "random_cycles": RANDOM_CYCLES,
                    "seed": RNG_SEED,
                },
                "failures": [asdict(f) for f in failures],
                "samples": [asdict(s) for s in samples],
            }

            with open(LOG_JSON, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)

            print("\n========== D FLIP-FLOP TEST RESULT ==========")
            print("PASS ✅" if passed else "FAIL ❌")
            print(f"Failures: {len(failures)}")
            print(f"Log written to: {LOG_JSON}")

            if ENABLE_VPLUS:
                print("Disabling V+ ...")
                disable_vplus()

            return 0 if passed else 1

    except Exception as e:
        print("ERROR: Could not open/use the WaveForms device from Python.")
        print("Common causes:")
        print("  - WaveForms is open (device busy) -> close WaveForms and retry")
        print("  - WaveForms runtime/SDK not installed correctly")
        print("  - USB permissions / cable / hub issues")
        print("")
        print(f"Details: {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

"""
Quality gate for forecast publish step.

Fails if row counts or positive-rate ranges are out of expected bounds.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd


def within(value: float, lo: float, hi: float) -> bool:
    return lo <= value <= hi


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model1-csv", required=True)
    parser.add_argument("--model2-csv", required=True)
    args = parser.parse_args()

    m1 = pd.read_csv(args.model1_csv)
    m2 = pd.read_csv(args.model2_csv)

    checks = []
    checks.append(("model1_nonempty", len(m1) > 0))
    checks.append(("model2_nonempty", len(m2) > 0))

    m1_pos_rate = float(m1["predicted_sla_breach_label"].mean())
    m2_pos_rate = float(m2["predicted_hotspot_label"].mean())
    checks.append(("model1_pos_rate_range", within(m1_pos_rate, 0.0001, 0.20)))
    checks.append(("model2_pos_rate_range", within(m2_pos_rate, 0.01, 0.30)))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{name}: {'PASS' if ok else 'FAIL'}")

    print(f"model1_pos_rate={m1_pos_rate:.6f}")
    print(f"model2_pos_rate={m2_pos_rate:.6f}")

    if failed:
        print(f"QUALITY_GATE_FAILED: {failed}")
        return 1

    print("QUALITY_GATE_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

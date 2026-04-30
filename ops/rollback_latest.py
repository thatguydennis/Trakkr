"""
Rollback latest pointer to a prior run.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEST_DIR = os.path.join(BASE, "data", "artifacts", "latest")
ARTIFACTS_DIR = os.path.join(BASE, "data", "artifacts")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", required=True, choices=["clean_data", "model1", "model2", "forecast", "backtest"])
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    run_dir = os.path.join(ARTIFACTS_DIR, args.run_id)
    if not os.path.isdir(run_dir):
        raise SystemExit(f"Run directory not found: {run_dir}")

    os.makedirs(LATEST_DIR, exist_ok=True)
    pointer_path = os.path.join(LATEST_DIR, f"{args.pipeline}.json")
    payload = {
        "pipeline_name": args.pipeline,
        "latest_run_id": args.run_id,
        "latest_run_dir": run_dir,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "rollback": True,
    }
    with open(pointer_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"Rolled back {args.pipeline} pointer to {args.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

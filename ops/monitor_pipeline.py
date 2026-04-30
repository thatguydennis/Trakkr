"""
Basic monitoring checks for pipeline freshness and run health.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List

PIPELINES = ["clean_data", "model1", "model2", "backtest", "forecast"]
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEST_DIR = os.path.join(BASE, "data", "artifacts", "latest")


def read_pointer(pipeline: str) -> Dict[str, str]:
    path = os.path.join(LATEST_DIR, f"{pipeline}.json")
    if not os.path.exists(path):
        return {"pipeline_name": pipeline, "status": "missing"}
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    payload["status"] = "ok"
    return payload


def main() -> int:
    now = datetime.now(timezone.utc)
    freshness_limit = now - timedelta(days=7)
    failures: List[str] = []

    for pipeline in PIPELINES:
        data = read_pointer(pipeline)
        if data.get("status") == "missing":
            failures.append(f"{pipeline}:missing_pointer")
            print(f"{pipeline}: MISSING")
            continue
        updated_at = datetime.fromisoformat(data["updated_at"])
        is_fresh = updated_at >= freshness_limit
        print(f"{pipeline}: updated_at={updated_at.isoformat()} fresh={is_fresh}")
        if not is_fresh:
            failures.append(f"{pipeline}:stale")

    if failures:
        print(f"MONITOR_ALERT failures={failures}")
        return 1
    print("MONITOR_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

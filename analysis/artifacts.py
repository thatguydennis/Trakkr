"""
Versioned artifact helpers for model and forecast runs.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict


BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS_ROOT = os.path.join(BASE, "data", "artifacts")
LATEST_ROOT = os.path.join(ARTIFACTS_ROOT, "latest")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class RunContext:
    pipeline_name: str
    run_id: str
    run_dir: str
    created_at: str


def create_run_context(pipeline_name: str) -> RunContext:
    os.makedirs(ARTIFACTS_ROOT, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{pipeline_name}_{ts}_{uuid.uuid4().hex[:8]}"
    run_dir = os.path.join(ARTIFACTS_ROOT, run_id)
    os.makedirs(run_dir, exist_ok=True)
    return RunContext(
        pipeline_name=pipeline_name,
        run_id=run_id,
        run_dir=run_dir,
        created_at=utc_now_iso(),
    )


def write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def write_run_metadata(ctx: RunContext, metadata: Dict[str, Any]) -> str:
    out = {
        "run_id": ctx.run_id,
        "pipeline_name": ctx.pipeline_name,
        "created_at": ctx.created_at,
        **metadata,
    }
    path = os.path.join(ctx.run_dir, "run_metadata.json")
    write_json(path, out)
    return path


def copy_to_run_dir(ctx: RunContext, source_path: str, target_name: str | None = None) -> str:
    if target_name is None:
        target_name = os.path.basename(source_path)
    dst = os.path.join(ctx.run_dir, target_name)
    shutil.copy2(source_path, dst)
    return dst


def update_latest_pointer(ctx: RunContext) -> None:
    os.makedirs(LATEST_ROOT, exist_ok=True)
    pointer = os.path.join(LATEST_ROOT, f"{ctx.pipeline_name}.json")
    write_json(
        pointer,
        {
            "pipeline_name": ctx.pipeline_name,
            "latest_run_id": ctx.run_id,
            "latest_run_dir": ctx.run_dir,
            "updated_at": utc_now_iso(),
        },
    )

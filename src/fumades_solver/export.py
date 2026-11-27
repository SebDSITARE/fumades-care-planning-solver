from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io import write_csv


PLANNING_FIELDS = [
    "status", "service_date", "stay_id", "client_ref", "primary_orientation",
    "secondary_orientation", "request_id", "care_code", "sector", "mode_plan",
    "start", "end", "resource_id", "locked", "engine",
]
DAILY_FIELDS = [
    "service_date", "stay_id", "client_ref", "first_start", "last_end",
    "journey_duration_minutes", "total_wait_minutes", "preferred_day_start",
    "desired_start_deviation_minutes",
]


def export_result(output_dir: str | Path, result: dict[str, Any], validation_report: dict[str, Any]) -> None:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    write_csv(root / "planning.csv", PLANNING_FIELDS, result.get("planning", []))
    write_csv(root / "daily_indicators.csv", DAILY_FIELDS, result.get("daily_indicators", []))
    diagnostics = {k: v for k, v in result.items() if k not in {"planning", "daily_indicators"}}
    diagnostics["daily_indicators_count"] = len(result.get("daily_indicators", []))
    (root / "diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "validation_report.json").write_text(
        json.dumps(validation_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

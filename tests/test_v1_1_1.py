from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fumades_solver.export import export_result
from fumades_solver.io import load_input, load_parameters, time_to_minutes
from fumades_solver.model import solve
from fumades_solver.validation import validate


def parameters(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "parameters"
    root.mkdir()
    (root / "care_types.csv").write_text(
        "care_code,duration_minutes,provisional,dry_care\n"
        "0206,15,false,false\n"
        "0307,5,false,false\n"
        "0308,6,true,false\n"
        "0408,15,false,true\n"
        "0513,15,false,false\n"
        "0601,10,false,false\n"
        "0306,10,false,false\n"
        "0701,10,true,false\n",
        encoding="utf-8",
    )
    (root / "resources.csv").write_text(
        "resource_id,sector\nB1RH,RH\nCA01,RH\nDP1R,RH\nTH1,RH\nPM,RH\nMOB_RH,RH\nPISC_RH,RH\n",
        encoding="utf-8",
    )
    (root / "care_resource_compatibility.csv").write_text(
        "care_code,resource_id\n0206,B1RH\n0408,CA01\n0308,DP1R\n0307,TH1\n0513,PM\n0601,MOB_RH\n0306,PISC_RH\n",
        encoding="utf-8",
    )
    config = tmp_path / "solver.json"
    config.write_text(json.dumps({
        "time_limit_seconds": 10,
        "num_search_workers": 4,
        "transition_minutes": 5,
        "preferred_day_start_weight": 1000,
        "journey_duration_weight": 10,
        "waiting_weight": 5,
        "turpentine_order_weight": 1,
    }), encoding="utf-8")
    return root, config


def test_demo_grid_anchor_locked_diagnostics_and_indicators(tmp_path: Path) -> None:
    parameter_dir, config = parameters(tmp_path)
    stays, requests = load_input(ROOT / "data" / "demo")
    params = load_parameters(parameter_dir, config)
    report = validate(stays, requests, params)
    assert report["status"] == "VALID"
    assert report["issues"][0]["context"]["care_codes"] == ["0308"]

    result = solve(stays, requests, params, report["issues"], time_limit_seconds=10)
    assert result["status"] in {"OPTIMAL", "FEASIBLE"}
    if result["engine"] == "cp-sat":
        assert result["best_bound"] is not None
        assert result["gap"] is not None
    assert isinstance(result["branches"], int)
    assert isinstance(result["conflicts"], int)

    rows = result["planning"]
    assert all(time_to_minutes(row["start"]) % 5 == 0 for row in rows)
    assert min(time_to_minutes(row["start"]) for row in rows) >= 7 * 60 + 45
    locked = next(row for row in rows if row["request_id"] == "REQ-001")
    assert locked["start"] == "07:45"
    assert locked["resource_id"] == "B1RH"
    assert locked["locked"] is True

    indicator = result["daily_indicators"][0]
    assert indicator["first_start"] == "07:45"
    assert indicator["desired_start_deviation_minutes"] == 0
    assert indicator["journey_duration_minutes"] >= 45
    assert indicator["total_wait_minutes"] >= 0

    ordered = sorted(rows, key=lambda row: row["start"])
    turpentine_index = next(i for i, row in enumerate(ordered) if row["care_code"] == "0307")
    if turpentine_index != len(ordered) - 1:
        assert ordered[turpentine_index + 1]["care_code"] == "0408"

    output = tmp_path / "out"
    export_result(output, result, report)
    diagnostics = json.loads((output / "diagnostics.json").read_text(encoding="utf-8"))
    for field in ("best_bound", "gap", "relative_gap", "branches", "conflicts"):
        assert field in diagnostics
    assert (output / "daily_indicators.csv").exists()


def test_validation_rejects_locked_start_before_earliest(tmp_path: Path) -> None:
    parameter_dir, config = parameters(tmp_path)
    stays, requests = load_input(ROOT / "data" / "demo_infeasible")
    report = validate(stays, requests, load_parameters(parameter_dir, config))
    assert report["status"] == "INVALID"
    assert "LOCKED_START_BEFORE_EARLIEST" in {issue["code"] for issue in report["issues"]}


def test_rh_generator_has_exact_composition_and_new_stay_fields(tmp_path: Path) -> None:
    import importlib.util

    script = ROOT / "tools" / "generate_rh_reference_001.py"
    spec = importlib.util.spec_from_file_location("rh_generator", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    days, rows = module.generate(tmp_path / "rh")
    assert len(days) == 18
    assert len(rows) == 72
    assert Counter(row[3] for row in rows) == {
        "0206": 6, "0306": 9, "0307": 9, "0308": 9,
        "0408": 18, "0513": 12, "0601": 9,
    }
    with (tmp_path / "rh" / "stays.csv").open(newline="", encoding="utf-8") as handle:
        stay = next(csv.DictReader(handle))
    assert stay["earliest_start"] == "07:45"
    assert stay["preferred_day_start"] == "07:45"
    assert stay["latest_start"] == "09:00"


def test_rh_reference_end_to_end(tmp_path: Path) -> None:
    import importlib.util

    parameter_dir, config = parameters(tmp_path)
    script = ROOT / "tools" / "generate_rh_reference_001.py"
    spec = importlib.util.spec_from_file_location("rh_generator_e2e", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    input_dir = tmp_path / "rh"
    module.generate(input_dir)
    stays, requests = load_input(input_dir)
    params = load_parameters(parameter_dir, config)
    report = validate(stays, requests, params)
    assert report["status"] == "VALID"
    warnings = [issue for issue in report["issues"] if issue["level"] == "WARNING"]
    assert warnings[0]["context"]["care_codes"] == ["0308"]
    result = solve(stays, requests, params, warnings, time_limit_seconds=10)
    assert result["status"] in {"OPTIMAL", "FEASIBLE"}
    assert len(result["planning"]) == 72
    assert len(result["daily_indicators"]) == 18
    assert all(row["first_start"] >= "07:45" for row in result["daily_indicators"])
    assert all(time_to_minutes(row["start"]) % 5 == 0 for row in result["planning"])

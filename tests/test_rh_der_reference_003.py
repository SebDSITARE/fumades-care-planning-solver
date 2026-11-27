from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from fumades_solver.acceptance_metrics import compute_acceptance_metrics, compute_resource_occupation
from fumades_solver.fallback import solve_fallback
from fumades_solver.io import load_problem
from fumades_solver.model import solve_cp_sat
from fumades_solver.validation import errors, validate_problem

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "acceptance" / "rh_der_reference_003"
PARAMS = ROOT / "config" / "parameters"
CONFIG = ROOT / "config" / "solver.json"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def problem():
    return load_problem(DATA, PARAMS, CONFIG)


def metrics(rows: list[dict]) -> dict:
    scenario = json.loads((DATA / "scenario.json").read_text(encoding="utf-8"))
    cfg = scenario["metrics"]
    return compute_acceptance_metrics(
        rows, read_csv(DATA / "care_requests.csv"), scenario["target"]["stay_id"],
        scenario["target"]["preferred_day_start"], cfg["preferred_start_tolerance_minutes"],
        cfg["target_sector_return_pattern"], cfg["expected_start_sector"],
    )


def test_generator_is_repeatable_and_case_is_fully_pseudonymized():
    subprocess.run([sys.executable, str(ROOT / "tools" / "generate_rh_der_reference_003.py")], check=True)
    p = problem()
    assert len(p["stays"]) == 21
    assert len(p["requests"]) == 192
    target = [row for row in p["requests"] if row["stay_id"] == "ACC-RHDER-003"]
    assert len(target) == 72
    assert {row["sector"] for row in target} == {"RH", "DER"}
    assert {row["care_code"] for row in target} == {"0301", "0324", "0408", "0513", "0519"}
    assert all(row["client_ref"].startswith("PSEUDO-") for row in p["stays"])
    serialized = " ".join(
        str(value) for table in (p["stays"], p["requests"])
        for row in table for value in row.values()
    ).lower()
    assert "marie" not in serialized
    assert "laure" not in serialized
    assert "@" not in serialized


def test_case_validates_on_unchanged_v1_2_0_and_write_is_disabled():
    p = problem()
    assert not errors(validate_problem(p))
    assert p["config"]["version"] == "1.2.0"
    assert p["config"]["write_to_nymphea"] is False
    assert p["config"]["planning_requires_human_validation"] is True
    assert p["config"]["time_step_minutes"] == 5


def test_inert_nymphea_baseline_reproduces_all_requested_defects():
    baseline = read_csv(DATA / "nymphea_baseline.csv")
    result = metrics(baseline)
    assert result["prescribed_care_count"] == 72
    assert result["positioned_care_count"] == 66
    assert result["unpositioned_care_count"] == 6
    assert result["unpositioned_general_showers"] == 6
    assert result["manual_additions_needed"] == 6
    assert result["vapor_end_of_cure_reports"] == 6
    assert result["avoidable_rh_der_rh_returns"] == 6
    assert result["avoidable_sector_returns"] == 6
    assert result["prescription_coverage_percent"] == 91.67
    assert result["prescription_exact_day_percent"] == 83.33
    assert result["start_time_compliance_percent"] == 100.0
    assert result["start_sector_compliance_percent"] == 100.0


def test_baseline_capacity_load_is_explicit_and_never_overbooks_a_post():
    occupation = compute_resource_occupation(
        read_csv(DATA / "nymphea_baseline.csv"), problem()["resources"]
    )
    assert occupation
    assert sum(row["overload_minutes"] for row in occupation) == 0
    assert all(row["max_concurrency"] <= row["capacity"] for row in occupation)
    relevant = {(row["service_date"], row["resource_id"]): row for row in occupation}
    assert any(resource_id == "DER_GENERAL" for _, resource_id in relevant)
    assert any(resource_id == "VAP" for _, resource_id in relevant)


def test_fallback_verifies_contract_without_adding_a_solver_rule():
    p = problem()
    rows, diagnostics = solve_fallback(p)
    assert diagnostics["status"] == "FEASIBLE"
    result = metrics(rows)
    assert result["positioned_care_count"] == 72
    assert result["unpositioned_care_count"] == 0
    assert result["manual_additions_needed"] == 0
    assert result["prescription_coverage_percent"] == 100.0
    assert result["prescription_exact_day_percent"] == 100.0
    occupation = compute_resource_occupation(rows, p["resources"])
    assert sum(row["overload_minutes"] for row in occupation) == 0


def test_cp_sat_v1_2_0_baseline_is_measured_without_preventive_rule():
    pytest.importorskip("ortools.sat.python.cp_model")
    p = problem()
    rows, diagnostics = solve_cp_sat(p)
    assert diagnostics["status"] in {"OPTIMAL", "FEASIBLE"}
    assert diagnostics["engine"] == "cp-sat"
    result = metrics(rows)
    assert result["positioned_care_count"] == 72
    assert result["unpositioned_care_count"] == 0
    assert result["manual_additions_needed"] == 0
    assert result["prescription_coverage_percent"] == 100.0
    assert result["prescription_exact_day_percent"] == 100.0
    occupation = compute_resource_occupation(rows, p["resources"])
    assert sum(row["overload_minutes"] for row in occupation) == 0
    # Sector returns, RH-wave sector compliance, waiting and path duration are
    # deliberately measured, not asserted: V1.2.0 has no preventive rule for them.
    assert isinstance(result["avoidable_sector_returns"], int)
    assert isinstance(result["start_sector_compliance_percent"], float)

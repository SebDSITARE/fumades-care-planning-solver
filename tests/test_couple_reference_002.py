from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import pytest

from fumades_solver.indicators import compute_couple_indicators, compute_daily_indicators
from fumades_solver.io import load_problem, minutes
from fumades_solver.model import solve_cp_sat
from fumades_solver.validation import errors, validate_problem

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "acceptance" / "couple_reference_002"
PARAMS = ROOT / "config" / "parameters"
CONFIG = ROOT / "config" / "solver.json"


def problem():
    return load_problem(DATA, PARAMS, CONFIG)


def test_couple_case_is_pseudonymized_and_has_distinct_prescriptions():
    p = problem()
    assert len(p["stays"]) == 2
    assert {row["client_ref"] for row in p["stays"]} == {"PSEUDO-CPL2-A", "PSEUDO-CPL2-B"}
    assert {row["couple_id"] for row in p["stays"]} == {"CPL-ACC-002"}
    assert {row["wave_id"] for row in p["stays"]} == {"WAVE-0800"}
    assert {row["preferred_day_start"] for row in p["stays"]} == {"08:00"}
    counts = defaultdict(Counter)
    for row in p["requests"]:
        counts[row["stay_id"]][row["care_code"]] += 1
    assert sum(counts["ACC-CPL2-A"].values()) == 72
    assert sum(counts["ACC-CPL2-B"].values()) == 72
    assert counts["ACC-CPL2-A"] != counts["ACC-CPL2-B"]
    serialized = " ".join(str(value) for table in (p["stays"], p["requests"]) for row in table for value in row.values()).lower()
    assert "marie" not in serialized
    assert "nymphea" not in serialized


def test_couple_case_validates_and_nymphea_write_is_disabled():
    p = problem()
    issues = validate_problem(p)
    assert not errors(issues)
    warning_codes = {item["code"] for item in issues if item["level"] == "WARNING"}
    assert warning_codes <= {"PROVISIONAL_PARAMETERS"}
    assert p["config"]["write_to_nymphea"] is False
    assert p["config"]["time_step_minutes"] == 5


def test_cp_sat_couple_acceptance_case():
    pytest.importorskip("ortools.sat.python.cp_model")
    p = problem()
    rows, diagnostics = solve_cp_sat(p)
    assert diagnostics["status"] in {"OPTIMAL", "FEASIBLE"}
    assert len(rows) == 144
    assert all((minutes(row["start"]) - minutes(p["config"]["planning_day_start"])) % 5 == 0 for row in rows if row["start"])
    daily = compute_daily_indicators(rows, p["stays"])
    couple = compute_couple_indicators(rows, p["stays"], 5)
    assert len(daily) == 36
    assert len(couple) == 18
    assert max(row["start_gap_minutes"] for row in couple) <= 5
    assert max(row["end_gap_minutes"] for row in couple) <= 5
    assert max(row["max_collective_gap_minutes"] for row in couple) <= 5
    assert all(row["collective_pair_count"] >= 1 for row in couple)


def test_simultaneous_individual_care_uses_distinct_resources():
    pytest.importorskip("ortools.sat.python.cp_model")
    p = problem()
    rows, diagnostics = solve_cp_sat(p)
    assert diagnostics["status"] in {"OPTIMAL", "FEASIBLE"}
    grouped = defaultdict(list)
    for row in rows:
        if row["couple_sync_group"] and row["couple_sync_priority"] == "PREFERRED":
            grouped[(row["service_date"], row["couple_sync_group"])].append(row)
    simultaneous_same_care = [pair for pair in grouped.values() if len(pair) == 2 and pair[0]["care_code"] == pair[1]["care_code"] and pair[0]["start"] == pair[1]["start"]]
    assert simultaneous_same_care
    assert all(pair[0]["resource_id"] != pair[1]["resource_id"] for pair in simultaneous_same_care)

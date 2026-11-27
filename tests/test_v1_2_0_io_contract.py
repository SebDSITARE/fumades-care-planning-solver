"""Behavioural contract for the autonomous V1.2.0 io API."""

from pathlib import Path

import pytest

from fumades_solver.export import export_result
from fumades_solver.io import hhmm, load_problem, minutes

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "acceptance" / "couple_reference_002"
PARAMETERS = ROOT / "config" / "parameters"
CONFIG = ROOT / "config" / "solver.json"


def test_minutes_and_hhmm_behaviour():
    assert minutes(0) == 0
    assert minutes(485) == 485
    assert minutes("00:00") == 0
    assert minutes("08:05") == 485
    assert minutes("23:59") == 1439
    assert hhmm(0) == "00:00"
    assert hhmm(485) == "08:05"
    assert hhmm(1439) == "23:59"
    assert hhmm(1440) == "00:00"
    assert minutes("485") == 485
    assert minutes("08:05:00") == 485
    for invalid in (None, True, "", "08:60", "24:00", 8.5):
        with pytest.raises(ValueError):
            minutes(invalid)
    for invalid in (None, True, "485", 8.5):
        with pytest.raises(ValueError):
            hhmm(invalid)


def test_load_problem_returns_raw_v120_contract():
    problem = load_problem(DATA, PARAMETERS, CONFIG)
    assert set(problem) == {
        "stays", "requests", "care_types", "resources",
        "compatibilities", "transitions", "workforce", "config",
    }
    assert len(problem["stays"]) == 2
    assert len(problem["requests"]) == 144
    assert all(isinstance(row, dict) for table in problem.values() if isinstance(table, list) for row in table)
    assert {row["couple_id"] for row in problem["stays"]} == {"CPL-ACC-002"}
    assert problem["config"]["time_step_minutes"] == 5
    assert problem["config"]["write_to_nymphea"] is False
    assert problem["care_types"]
    assert problem["resources"]
    assert problem["compatibilities"]
    assert problem["transitions"]
    assert problem["workforce"]


def test_v111_export_result_is_preserved():
    assert callable(export_result)

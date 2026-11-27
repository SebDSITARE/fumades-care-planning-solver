"""Behavioural tests for the opt-in daily couple end-gap policy."""

from pathlib import Path

import pytest

from fumades_solver.io import load_problem
from fumades_solver.model import _configured_couple_end_gap_limit

ROOT = Path(__file__).resolve().parents[1]


def test_end_gap_policy_is_opt_in_per_couple():
    assert _configured_couple_end_gap_limit({}, "ANY") is None
    config = {"couple_end_gap_limits_minutes": {"CPL-ACC-002": 5}}
    assert _configured_couple_end_gap_limit(config, "CPL-ACC-002") == 5
    assert _configured_couple_end_gap_limit(config, "ANOTHER-COUPLE") is None


def test_invalid_end_gap_policy_is_rejected():
    with pytest.raises(ValueError):
        _configured_couple_end_gap_limit(
            {"couple_end_gap_limits_minutes": {"CPL-ACC-002": -1}},
            "CPL-ACC-002",
        )
    with pytest.raises(ValueError):
        _configured_couple_end_gap_limit(
            {"couple_end_gap_limits_minutes": 5},
            "CPL-ACC-002",
        )


def test_acceptance_case_002_explicitly_requests_five_minute_end_limit():
    problem = load_problem(
        ROOT / "data" / "acceptance" / "couple_reference_002",
        ROOT / "config" / "parameters",
        ROOT / "config" / "solver.json",
    )
    assert problem["config"]["couple_end_gap_limits_minutes"] == {
        "CPL-ACC-002": 5,
    }

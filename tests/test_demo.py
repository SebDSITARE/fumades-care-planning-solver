from pathlib import Path
from fumades_solver.io import load_problem
from fumades_solver.validation import validate_problem, errors
from fumades_solver.fallback import solve_fallback

ROOT=Path(__file__).resolve().parents[1]
PARAMS=ROOT/"config"/"parameters"
CONFIG=ROOT/"config"/"solver.json"

def test_demo_is_valid_and_feasible():
    p=load_problem(ROOT/"data"/"demo",PARAMS,CONFIG)
    assert not errors(validate_problem(p))
    rows,diag=solve_fallback(p)
    assert diag["status"]=="FEASIBLE"
    assert len(rows)==24
    assert all(r["status"]=="PROPOSE" for r in rows)

def test_infeasible_locked_capacity_is_explained():
    p=load_problem(ROOT/"data"/"demo_infeasible",PARAMS,CONFIG)
    codes={i["code"] for i in errors(validate_problem(p))}
    assert "LOCKED_CAPACITY_OVERLOAD" in codes

def test_nymphea_write_is_disabled():
    p=load_problem(ROOT/"data"/"demo",PARAMS,CONFIG)
    assert p["config"]["write_to_nymphea"] is False

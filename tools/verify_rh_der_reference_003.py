#!/usr/bin/env python3
"""End-to-end validator for acceptance case no. 3 on a CP-SAT environment."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "acceptance" / "rh_der_reference_003"
PARAMS = ROOT / "config" / "parameters"
CONFIG = ROOT / "config" / "solver.json"


def run(command: list[str]) -> None:
    print(" ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--clean-output", action="store_true")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs" / "rh_der_reference_003_validation")
    args = parser.parse_args(argv)
    python = sys.executable
    solve_dir = args.output_root / "solve_v1_2_0_cp_sat"
    compare_dir = args.output_root / "comparison"
    if args.output_root.exists():
        if not args.clean_output:
            raise SystemExit(f"Output exists: {args.output_root}; use --clean-output to replace only this validation output")
        shutil.rmtree(args.output_root)

    if not args.skip_install:
        run([python, "-m", "pip", "install", "-e", "."])
    run([python, "tools/generate_rh_der_reference_003.py"])
    run([python, "-m", "pytest", "-v"])
    run([
        python, "-m", "fumades_solver.cli", "validate", "--input-dir", str(DATA),
        "--parameter-dir", str(PARAMS), "--config", str(CONFIG),
    ])
    run([
        python, "-m", "fumades_solver.cli", "solve", "--input-dir", str(DATA),
        "--parameter-dir", str(PARAMS), "--config", str(CONFIG),
        "--output-dir", str(solve_dir), "--engine", "cp-sat",
    ])
    run([
        python, "tools/compare_rh_der_reference_003.py", "--solver-output", str(solve_dir),
        "--output-dir", str(compare_dir),
    ])

    diagnostics = json.loads((solve_dir / "diagnostics.json").read_text(encoding="utf-8"))
    comparison = json.loads((compare_dir / "comparison.json").read_text(encoding="utf-8"))
    planning = read_csv(solve_dir / "planning.csv")
    target = [row for row in planning if row["stay_id"] == "ACC-RHDER-003"]
    assert diagnostics["status"] in {"OPTIMAL", "FEASIBLE"}
    assert diagnostics["engine"] == "cp-sat"
    assert len(planning) == 192
    assert len(target) == 72
    assert comparison["solver"]["positioned_care_count"] == 72
    assert comparison["solver"]["unpositioned_care_count"] == 0
    assert comparison["solver"]["manual_additions_needed"] == 0
    assert comparison["solver"]["prescription_coverage_percent"] == 100.0
    assert comparison["solver"]["prescription_exact_day_percent"] == 100.0
    assert comparison["capacity"]["solver_overload_minutes"] == 0
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert config["version"] == "1.2.0"
    assert config["write_to_nymphea"] is False
    assert config["planning_requires_human_validation"] is True

    if (ROOT / ".git").exists():
        run(["git", "diff", "--check"])
        subprocess.run(
            ["git", "diff", "--quiet", "v1.2.0", "--", "src/fumades_solver/model.py", "config/solver.json"],
            cwd=ROOT, check=True,
        )
    print("VALIDATION PASSED: V1.2.0 unchanged, CP-SAT 192/72 contract, metrics and safety checks succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

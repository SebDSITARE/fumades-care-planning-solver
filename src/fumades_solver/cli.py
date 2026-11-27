from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .export import (
    prepare_output,
    write_couple_indicators,
    write_daily_indicators,
    write_infeasibility,
    write_json,
    write_schedule,
)
from .fallback import solve_fallback
from .indicators import compute_couple_indicators, compute_daily_indicators
from .io import load_problem
from .model import solve_cp_sat
from .validation import errors, validate_problem


def build_parser():
    parser = argparse.ArgumentParser(prog="fumades-solver")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "solve"):
        command = sub.add_parser(name)
        command.add_argument("--input-dir", type=Path, required=True)
        command.add_argument("--parameter-dir", type=Path, required=True)
        command.add_argument("--config", type=Path, default=Path("config/solver.json"))
        if name == "solve":
            command.add_argument("--output-dir", type=Path, required=True)
            command.add_argument("--engine", choices=("cp-sat", "fallback"), default="cp-sat")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    problem = load_problem(args.input_dir, args.parameter_dir, args.config)
    issues = validate_problem(problem)
    blocking = errors(issues)
    if args.command == "validate":
        print(json.dumps({"status": "INVALID" if blocking else "VALID", "issues": issues}, ensure_ascii=False, indent=2))
        return 2 if blocking else 0

    prepare_output(args.output_dir)
    write_json(args.output_dir / "validation_report.json", {"status": "INVALID" if blocking else "VALID", "issues": issues})
    if blocking:
        diagnostics = {"status": "INVALID_INPUT", "engine": args.engine, "validation_errors": blocking}
        write_json(args.output_dir / "diagnostics.json", diagnostics)
        write_infeasibility(args.output_dir / "rapport_infeasibilite.txt", diagnostics)
        print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
        return 2

    rows, diagnostics = solve_cp_sat(problem) if args.engine == "cp-sat" else solve_fallback(problem)
    diagnostics["validation_warnings"] = [issue for issue in issues if issue["level"] == "WARNING"]
    if rows:
        daily = compute_daily_indicators(rows, problem["stays"])
        tolerance = int(problem["config"].get("couple_sync_tolerance_minutes", 5))
        couple = compute_couple_indicators(rows, problem["stays"], tolerance)
        diagnostics["daily_indicator_rows"] = len(daily)
        diagnostics["couple_indicator_rows"] = len(couple)
        diagnostics["couple_days_within_tolerance"] = sum(bool(row["within_tolerance"]) for row in couple)
        write_schedule(args.output_dir / "planning.csv", rows)
        write_daily_indicators(args.output_dir / "daily_indicators.csv", daily)
        if couple:
            write_couple_indicators(args.output_dir / "couple_indicators.csv", couple)
    else:
        write_infeasibility(args.output_dir / "rapport_infeasibilite.txt", diagnostics)
    write_json(args.output_dir / "diagnostics.json", diagnostics)
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    return 0 if rows else 3


if __name__ == "__main__":
    sys.exit(main())

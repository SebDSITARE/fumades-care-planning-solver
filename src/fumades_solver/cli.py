from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .export import export_result
from .fallback import solve_fallback
from .io import load_input, load_parameters
from .model import solve
from .validation import validate


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--parameter-dir", required=True)
    parser.add_argument("--config", default="config/solver.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fumades-solver")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    _common(validate_parser)
    solve_parser = subparsers.add_parser("solve")
    _common(solve_parser)
    solve_parser.add_argument("--output-dir", required=True)
    solve_parser.add_argument("--engine", choices=("cp-sat", "fallback"), default="cp-sat")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        stays, requests = load_input(args.input_dir)
        parameters = load_parameters(args.parameter_dir, args.config)
        report = validate(stays, requests, parameters)
        if args.command == "validate":
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["status"] == "VALID" else 2
        if report["status"] != "VALID":
            Path(args.output_dir).mkdir(parents=True, exist_ok=True)
            invalid = {
                "status": "INVALID",
                "engine": args.engine,
                "validation_warnings": [i for i in report["issues"] if i["level"] == "WARNING"],
                "planning": [],
                "daily_indicators": [],
            }
            export_result(args.output_dir, invalid, report)
            print(json.dumps(invalid, ensure_ascii=False, indent=2))
            return 2
        warnings = [issue for issue in report["issues"] if issue["level"] == "WARNING"]
        if args.engine == "fallback":
            result = solve_fallback(stays, requests, parameters, warnings)
        else:
            result = solve(stays, requests, parameters, warnings, engine="cp-sat")
        export_result(args.output_dir, result, report)
        console = {k: v for k, v in result.items() if k not in {"planning", "daily_indicators"}}
        print(json.dumps(console, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"FEASIBLE", "OPTIMAL"} else 3
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())

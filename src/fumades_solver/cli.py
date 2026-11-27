from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from .io import load_problem
from .validation import validate_problem, errors
from .model import solve_cp_sat
from .fallback import solve_fallback
from .export import prepare_output, write_json, write_schedule, write_infeasibility


def build_parser():
    p=argparse.ArgumentParser(prog="fumades-solver")
    sub=p.add_subparsers(dest="command",required=True)
    for name in ("validate","solve"):
        s=sub.add_parser(name)
        s.add_argument("--input-dir",type=Path,required=True)
        s.add_argument("--parameter-dir",type=Path,required=True)
        s.add_argument("--config",type=Path,default=Path("config/solver.json"))
        if name=="solve":
            s.add_argument("--output-dir",type=Path,required=True)
            s.add_argument("--engine",choices=("cp-sat","fallback"),default="cp-sat")
    return p


def main(argv=None):
    args=build_parser().parse_args(argv)
    problem=load_problem(args.input_dir,args.parameter_dir,args.config)
    issues=validate_problem(problem); blocking=errors(issues)
    if args.command=="validate":
        print(json.dumps({"status":"INVALID" if blocking else "VALID","issues":issues},ensure_ascii=False,indent=2))
        return 2 if blocking else 0
    prepare_output(args.output_dir)
    write_json(args.output_dir/"validation_report.json",{"status":"INVALID" if blocking else "VALID","issues":issues})
    if blocking:
        diag={"status":"INVALID_INPUT","engine":args.engine,"validation_errors":blocking}
        write_json(args.output_dir/"diagnostics.json",diag); write_infeasibility(args.output_dir/"rapport_infeasibilite.txt",diag)
        print(json.dumps(diag,ensure_ascii=False,indent=2)); return 2
    rows,diag=(solve_cp_sat(problem) if args.engine=="cp-sat" else solve_fallback(problem))
    diag["validation_warnings"]=[i for i in issues if i["level"]=="WARNING"]
    write_json(args.output_dir/"diagnostics.json",diag)
    if rows: write_schedule(args.output_dir/"planning.csv",rows)
    else: write_infeasibility(args.output_dir/"rapport_infeasibilite.txt",diag)
    print(json.dumps(diag,ensure_ascii=False,indent=2))
    return 0 if rows else 3


if __name__=="__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Compare the inert Nymphea reference with an unchanged V1.2.0 solve."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fumades_solver.acceptance_metrics import (
    compare_metrics,
    compute_acceptance_metrics,
    compute_resource_occupation,
)

DATA = ROOT / "data" / "acceptance" / "rh_der_reference_003"
PARAMETERS = ROOT / "config" / "parameters"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver-output", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    scenario = json.loads((DATA / "scenario.json").read_text(encoding="utf-8"))
    requests = read_csv(DATA / "care_requests.csv")
    baseline_rows = read_csv(DATA / "nymphea_baseline.csv")
    solver_rows = read_csv(args.solver_output / "planning.csv")
    resources = read_csv(PARAMETERS / "resources.csv")
    diagnostics = json.loads((args.solver_output / "diagnostics.json").read_text(encoding="utf-8"))
    target = scenario["target"]
    metrics_cfg = scenario["metrics"]
    metric_args = (
        requests, target["stay_id"], target["preferred_day_start"],
        int(metrics_cfg["preferred_start_tolerance_minutes"]),
        list(metrics_cfg["target_sector_return_pattern"]),
        metrics_cfg["expected_start_sector"],
    )
    baseline = compute_acceptance_metrics(baseline_rows, *metric_args)
    solver = compute_acceptance_metrics(solver_rows, *metric_args)
    baseline_occupation = compute_resource_occupation(baseline_rows, resources)
    solver_occupation = compute_resource_occupation(solver_rows, resources)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "case_id": scenario["case_id"],
        "solver_version": "1.2.0",
        "solver_status": diagnostics.get("status"),
        "engine": diagnostics.get("engine"),
        "baseline": baseline,
        "solver": solver,
        "delta": compare_metrics(baseline, solver),
        "capacity": {
            "baseline_overload_minutes": sum(row["overload_minutes"] for row in baseline_occupation),
            "solver_overload_minutes": sum(row["overload_minutes"] for row in solver_occupation),
        },
        "safety": scenario["safety"],
    }
    (args.output_dir / "comparison.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    flat_rows = []
    for metric, detail in payload["delta"].items():
        flat_rows.append({"metric": metric, **detail})
    write_csv(args.output_dir / "comparison.csv", flat_rows)
    write_csv(args.output_dir / "solver_resource_occupation.csv", solver_occupation)
    write_csv(args.output_dir / "baseline_resource_occupation.csv", baseline_occupation)

    summary = [
        "# Comparaison recette n°3 RH + DER",
        "",
        f"- Moteur: `{payload['engine']}`",
        f"- Statut: `{payload['solver_status']}`",
        f"- Version exécutée: `{payload['solver_version']}` (aucune nouvelle règle solveur)",
        "",
        "| Indicateur | Baseline Nymphéa | V1.2.0 | Écart |",
        "|---|---:|---:|---:|",
    ]
    keys = [
        "unpositioned_care_count", "manual_additions_needed", "avoidable_rh_der_rh_returns",
        "avoidable_sector_returns", "start_time_compliance_percent", "start_sector_compliance_percent",
        "total_wait_minutes", "mean_path_span_minutes",
        "intersector_moves", "prescription_coverage_percent", "prescription_exact_day_percent",
    ]
    for key in keys:
        detail = payload["delta"].get(key)
        if detail:
            summary.append(f"| `{key}` | {detail['baseline']} | {detail['solver']} | {detail['solver_minus_baseline']} |")
    summary += [
        "",
        f"- Surcharge physique baseline (minutes): {payload['capacity']['baseline_overload_minutes']}",
        f"- Surcharge physique solveur (minutes): {payload['capacity']['solver_overload_minutes']}",
        "- Écriture Nymphéa: désactivée.",
        "- Le planning reste une proposition soumise à validation humaine.",
    ]
    (args.output_dir / "comparison.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if diagnostics.get("status") not in {"OPTIMAL", "FEASIBLE"}:
        return 2
    if solver["positioned_care_count"] != solver["prescribed_care_count"]:
        return 3
    if payload["capacity"]["solver_overload_minutes"]:
        return 4
    if scenario["safety"]["write_to_nymphea"] is not False:
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

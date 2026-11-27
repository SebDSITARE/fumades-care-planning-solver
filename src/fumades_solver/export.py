from __future__ import annotations

import csv
import json
from pathlib import Path


def prepare_output(path: Path):
    if path.exists():
        raise FileExistsError(f"Refus d'ecraser le dossier existant: {path}")
    path.mkdir(parents=True)


def write_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict], fields: list[str]):
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_schedule(path: Path, rows: list[dict]):
    fields = [
        "status", "service_date", "stay_id", "client_ref", "couple_id", "wave_id",
        "primary_orientation", "secondary_orientation", "request_id", "care_code",
        "sector", "mode_plan", "start", "end", "resource_id", "couple_sync_group",
        "couple_sync_priority", "locked", "engine",
    ]
    _write_csv(path, rows, fields)


def write_daily_indicators(path: Path, rows: list[dict]):
    fields = [
        "service_date", "stay_id", "client_ref", "couple_id", "wave_id", "first_start",
        "last_end", "path_span_minutes", "care_minutes", "waiting_minutes",
        "preferred_day_start", "preferred_start_gap_minutes",
    ]
    _write_csv(path, rows, fields)


def write_couple_indicators(path: Path, rows: list[dict]):
    fields = [
        "service_date", "couple_id", "wave_id", "stay_a", "stay_b", "first_start_a",
        "first_start_b", "start_gap_minutes", "last_end_a", "last_end_b", "end_gap_minutes",
        "sync_pair_count", "synchronized_pair_count", "mean_sync_gap_minutes",
        "max_sync_gap_minutes", "collective_pair_count", "max_collective_gap_minutes",
        "tolerance_minutes", "within_tolerance",
    ]
    _write_csv(path, rows, fields)


def write_infeasibility(path: Path, diagnostics: dict):
    lines = [
        "RAPPORT D'INFAISABILITE - FUMADES SOLVER V1.2",
        "",
        f"Statut: {diagnostics.get('status')}",
        f"Moteur: {diagnostics.get('engine')}",
        "",
    ]
    if diagnostics.get("validation_errors"):
        lines.append("Erreurs de coherence:")
        for error in diagnostics["validation_errors"]:
            lines.append(f"- [{error['code']}] {error['message']} | {error.get('context', {})}")
    if diagnostics.get("unsat_core"):
        lines += ["", "Noyau d'hypotheses CP-SAT:"] + [f"- {item}" for item in diagnostics["unsat_core"]]
    if diagnostics.get("failed_requests"):
        lines += ["", "Demandes non positionnees:"] + [f"- {item}" for item in diagnostics["failed_requests"]]
    lines += [
        "", "Actions conseillees:",
        "- verifier les postes actifs et compatibilites;",
        "- verifier les horaires sectoriels et effectifs;",
        "- rechercher des rendez-vous verrouilles en conflit;",
        "- ne modifier la nature d'un soin qu'avec validation medicale;",
        "- conserver Nymphea en lecture seule.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# --- V1.1.1 export API compatibility (restored additively) ---

from typing import Any

from .io import write_csv

PLANNING_FIELDS = [
    "status", "service_date", "stay_id", "client_ref", "primary_orientation",
    "secondary_orientation", "request_id", "care_code", "sector", "mode_plan",
    "start", "end", "resource_id", "locked", "engine",
]

DAILY_FIELDS = [
    "service_date", "stay_id", "client_ref", "first_start", "last_end",
    "journey_duration_minutes", "total_wait_minutes", "preferred_day_start",
    "desired_start_deviation_minutes",
]

def export_result(output_dir: str | Path, result: dict[str, Any], validation_report: dict[str, Any]) -> None:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    write_csv(root / "planning.csv", PLANNING_FIELDS, result.get("planning", []))
    write_csv(root / "daily_indicators.csv", DAILY_FIELDS, result.get("daily_indicators", []))
    diagnostics = {k: v for k, v in result.items() if k not in {"planning", "daily_indicators"}}
    diagnostics["daily_indicators_count"] = len(result.get("daily_indicators", []))
    (root / "diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "validation_report.json").write_text(
        json.dumps(validation_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

# --- end V1.1.1 export API compatibility ---

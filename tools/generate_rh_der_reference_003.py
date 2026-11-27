#!/usr/bin/env python3
"""Generate acceptance case no. 3 from a configurable, pseudonymized pattern.

The generator does not reproduce any source identity or write to Nymphea. It
creates (1) the complete prescription/load problem for the unchanged V1.2.0
solver and (2) an inert reference CSV reproducing the observed planning defects.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fumades_solver.acceptance_metrics import compute_acceptance_metrics, compute_resource_occupation
from fumades_solver.io import hhmm, minutes

OUTPUT = ROOT / "data" / "acceptance" / "rh_der_reference_003"
SCENARIO_PATH = OUTPUT / "scenario.json"
PARAMETERS = ROOT / "config" / "parameters"

STAY_FIELDS = [
    "stay_id", "client_ref", "start_date", "end_date", "primary_orientation",
    "secondary_orientation", "package_primary", "package_secondary", "earliest_start",
    "preferred_day_start", "latest_start", "preferred_start", "pmr_level",
    "planning_communicated", "couple_id", "couple_role", "wave_id",
]
REQUEST_FIELDS = [
    "request_id", "stay_id", "service_date", "care_code", "sector", "mode_plan",
    "preferred_start", "locked_start", "locked_resource", "medical_override",
    "catchup_reason", "couple_sync_group", "couple_sync_priority",
]
BASELINE_FIELDS = [
    "status", "source", "manual_addition", "reason", "service_date",
    "prescribed_service_date", "planned_service_date", "stay_id", "client_ref",
    "primary_orientation", "secondary_orientation", "request_id", "care_code",
    "sector", "mode_plan", "start", "end", "resource_id", "locked", "engine",
]
OCCUPATION_FIELDS = [
    "service_date", "resource_id", "sector", "open_start", "open_end", "capacity",
    "occupied_capacity_minutes", "available_capacity_minutes", "utilization_percent",
    "max_concurrency", "overload_minutes",
]


def treatment_days(start: date, count: int, excluded_weekdays: set[int]) -> list[date]:
    result = []
    current = start
    while len(result) < count:
        if current.weekday() not in excluded_weekdays:
            result.append(current)
        current += timedelta(days=1)
    return result


def time_slots(start: str, end: str, step: int) -> list[str]:
    return [hhmm(value) for value in range(minutes(start), minutes(end), step)]


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def target_request(request_id: str, stay_id: str, service_date: date, care: dict) -> dict:
    return {
        "request_id": request_id, "stay_id": stay_id, "service_date": service_date.isoformat(),
        "care_code": care["care_code"], "sector": care["sector"], "mode_plan": care["mode_plan"],
        "preferred_start": "", "locked_start": "", "locked_resource": "",
        "medical_override": "false", "catchup_reason": "", "couple_sync_group": "",
        "couple_sync_priority": "",
    }


def load_request(request_id: str, stay_id: str, service_date: date, care_code: str, sector: str, start: str, resource: str) -> dict:
    return {
        "request_id": request_id, "stay_id": stay_id, "service_date": service_date.isoformat(),
        "care_code": care_code, "sector": sector, "mode_plan": "AVEC_RESSOURCE",
        "preferred_start": start, "locked_start": start, "locked_resource": resource,
        "medical_override": "false", "catchup_reason": "", "couple_sync_group": "",
        "couple_sync_priority": "",
    }


def baseline_row(request: dict, stay: dict, *, status: str, source: str, manual: bool,
                 reason: str, planned_date: str, start: str = "", end: str = "",
                 resource_id: str = "") -> dict:
    return {
        "status": status, "source": source, "manual_addition": str(manual).lower(), "reason": reason,
        "service_date": planned_date or request["service_date"],
        "prescribed_service_date": request["service_date"], "planned_service_date": planned_date,
        "stay_id": request["stay_id"], "client_ref": stay["client_ref"],
        "primary_orientation": stay["primary_orientation"],
        "secondary_orientation": stay.get("secondary_orientation", ""),
        "request_id": request["request_id"], "care_code": request["care_code"],
        "sector": request["sector"], "mode_plan": request["mode_plan"],
        "start": start, "end": end, "resource_id": resource_id,
        "locked": str(bool(request.get("locked_start") or request.get("locked_resource"))).lower(),
        "engine": "nymphea-reference-inert",
    }


def main() -> None:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    target_cfg = scenario["target"]
    constraints = scenario["constraints_to_reproduce"]
    days = treatment_days(
        date.fromisoformat(scenario["start_date"]),
        int(scenario["treatment_day_count"]),
        set(scenario["excluded_weekdays"]),
    )
    target_stay = {
        "stay_id": target_cfg["stay_id"], "client_ref": target_cfg["client_ref"],
        "start_date": days[0].isoformat(), "end_date": days[-1].isoformat(),
        "primary_orientation": target_cfg["primary_orientation"],
        "secondary_orientation": target_cfg["secondary_orientation"],
        "package_primary": target_cfg["package_primary"], "package_secondary": target_cfg["package_secondary"],
        "earliest_start": target_cfg["earliest_start"], "preferred_day_start": target_cfg["preferred_day_start"],
        "latest_start": target_cfg["latest_start"], "preferred_start": target_cfg["preferred_day_start"],
        "pmr_level": "0", "planning_communicated": "false", "couple_id": "", "couple_role": "",
        "wave_id": target_cfg["wave_id"],
    }
    stays = [target_stay]
    requests: list[dict] = []
    sequence = 0
    vapor_indices = set(target_cfg["alternate_cares"]["0519"]["day_indices"])
    for index, service_date in enumerate(days):
        care_rows = list(target_cfg["daily_cares"])
        care_rows.append({
            "care_code": "0519" if index in vapor_indices else "0513",
            "sector": target_cfg["alternate_cares"]["0519" if index in vapor_indices else "0513"]["sector"],
            "mode_plan": "AVEC_RESSOURCE",
        })
        for care in care_rows:
            sequence += 1
            requests.append(target_request(f"RHDER3-T-{sequence:03d}", target_cfg["stay_id"], service_date, care))

    # Pseudonymous locked demand fills the exact operational windows described in scenario.json.
    load_specs = [
        ("DG", constraints["general_shower"], "saturated_day_indices", "saturation_start", "saturation_end"),
        ("VAP", constraints["steam_bed"], "unavailable_day_indices", "unavailable_start", "unavailable_end"),
    ]
    for prefix, spec, day_key, start_key, end_key in load_specs:
        slots = time_slots(spec[start_key], spec[end_key], int(spec["slot_minutes"]))
        load_stays = []
        for slot_index, _ in enumerate(slots, start=1):
            stay_id = f"ACC-RHDER3-LOAD-{prefix}-{slot_index:02d}"
            stay = {
                "stay_id": stay_id, "client_ref": f"PSEUDO-LOAD-{prefix}-{slot_index:02d}",
                "start_date": days[0].isoformat(), "end_date": days[-1].isoformat(),
                "primary_orientation": spec["sector"], "secondary_orientation": "",
                "package_primary": "LOAD", "package_secondary": "", "earliest_start": spec[start_key],
                "preferred_day_start": spec[start_key], "latest_start": spec[end_key],
                "preferred_start": spec[start_key], "pmr_level": "0", "planning_communicated": "true",
                "couple_id": "", "couple_role": "", "wave_id": "LOAD-PSEUDO",
            }
            stays.append(stay)
            load_stays.append(stay)
        for day_index in spec[day_key]:
            service_date = days[day_index]
            for slot_index, slot in enumerate(slots, start=1):
                requests.append(load_request(
                    f"RHDER3-{prefix}-{day_index:02d}-{slot_index:02d}",
                    load_stays[slot_index - 1]["stay_id"], service_date,
                    spec["care_code"], spec["sector"], slot, spec["resource_id"],
                ))

    stay_map = {row["stay_id"]: row for row in stays}
    care_duration = {"0301": 5, "0324": 5, "0408": 15, "0513": 15, "0519": 15}
    baseline: list[dict] = []
    # Locked background demand is copied into the inert baseline.
    for request in requests:
        if request["stay_id"] == target_cfg["stay_id"]:
            continue
        start = request["locked_start"]
        end = hhmm(minutes(start) + care_duration[request["care_code"]])
        baseline.append(baseline_row(
            request, stay_map[request["stay_id"]], status="POSITIONED", source="NYMPHEA_REFERENCE",
            manual=False, reason="PSEUDONYMIZED_CAPACITY_LOAD", planned_date=request["service_date"],
            start=start, end=end, resource_id=request["locked_resource"],
        ))

    crowded_days = set(constraints["general_shower"]["saturated_day_indices"])
    report_days = constraints["steam_bed"]["manual_report_target_day_indices"]
    vapor_reports = dict(zip(sorted(vapor_indices), report_days))
    normal = scenario["baseline_schedule"]["normal_times"]
    crowded = scenario["baseline_schedule"]["crowded_day_times"]
    end_times = scenario["baseline_schedule"]["end_of_cure_times"]
    day_index_by_date = {day.isoformat(): index for index, day in enumerate(days)}
    for request in [row for row in requests if row["stay_id"] == target_cfg["stay_id"]]:
        index = day_index_by_date[request["service_date"]]
        code = request["care_code"]
        if code == "0301" and index in crowded_days:
            baseline.append(baseline_row(
                request, target_stay, status="UNPOSITIONED", source="NYMPHEA_REFERENCE",
                manual=False, reason="GENERAL_SHOWER_CAPACITY_EXHAUSTED_IN_RH_WINDOW",
                planned_date="",
            ))
            continue
        if code == "0519" and index in vapor_reports:
            report_index = vapor_reports[index]
            planned_date = days[report_index].isoformat()
            start, end, resource = end_times["0519"]
            baseline.append(baseline_row(
                request, target_stay, status="POSITIONED", source="NYMPHEA_MANUAL",
                manual=True, reason="STEAM_BED_UNAVAILABLE_IN_RH_WINDOW_REPORTED_END_OF_CURE",
                planned_date=planned_date, start=start, end=end, resource_id=resource,
            ))
            continue
        if index in report_days:
            timing = end_times[code]
        elif index in crowded_days:
            timing = crowded[code]
        else:
            timing = normal[code]
        baseline.append(baseline_row(
            request, target_stay, status="POSITIONED", source="NYMPHEA_REFERENCE",
            manual=False, reason="", planned_date=request["service_date"],
            start=timing[0], end=timing[1], resource_id=timing[2],
        ))

    write_csv(OUTPUT / "stays.csv", STAY_FIELDS, stays)
    write_csv(OUTPUT / "care_requests.csv", REQUEST_FIELDS, requests)
    write_csv(OUTPUT / "nymphea_baseline.csv", BASELINE_FIELDS, baseline)

    resources = read_csv(PARAMETERS / "resources.csv")
    metrics_cfg = scenario["metrics"]
    metrics = compute_acceptance_metrics(
        baseline, requests, target_cfg["stay_id"], target_cfg["preferred_day_start"],
        int(metrics_cfg["preferred_start_tolerance_minutes"]),
        list(metrics_cfg["target_sector_return_pattern"]),
        metrics_cfg["expected_start_sector"],
    )
    occupation = compute_resource_occupation(baseline, resources)
    write_csv(OUTPUT / "nymphea_resource_occupation.csv", OCCUPATION_FIELDS, occupation)
    (OUTPUT / "nymphea_baseline_metrics.json").write_text(
        json.dumps({"case_id": scenario["case_id"], "metrics": metrics}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{len(days)} jours de cure generes")
    print(f"{len(stays)} sejours pseudonymises generes (1 cible + {len(stays) - 1} charges)")
    print(f"{len(requests)} demandes generees, dont 72 pour le sejour cible")
    print(f"Baseline: {metrics['unpositioned_care_count']} soins non positionnes")
    print(f"Baseline: {metrics['manual_additions_needed']} ajouts manuels")
    print(f"Baseline: {metrics['avoidable_rh_der_rh_returns']} retours RH->DER->RH")


if __name__ == "__main__":
    main()

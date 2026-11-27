from __future__ import annotations

from collections import defaultdict

from .io import hhmm, minutes

TRUE_VALUES = {"1", "true", "TRUE", "oui", "OUI"}


def _truthy(value) -> bool:
    return str(value or "").strip() in TRUE_VALUES


def solve_fallback(problem: dict) -> tuple[list[dict], dict]:
    """Deterministic verification engine; CP-SAT remains the acceptance engine."""
    cfg = problem["config"]
    start_day = minutes(cfg["planning_day_start"])
    end_day = minutes(cfg["planning_day_end"])
    step = int(cfg.get("time_step_minutes", 5))
    cares = {x["care_code"]: x for x in problem["care_types"]}
    stays = {x["stay_id"]: x for x in problem["stays"]}
    resources = {x["resource_id"]: x for x in problem["resources"] if _truthy(x.get("active", "1"))}
    transitions = {(x["from_sector"], x["to_sector"]): int(x["minutes"]) for x in problem["transitions"]}
    compat = defaultdict(list)
    for row in problem["compatibilities"]:
        if _truthy(row.get("active", "1")) and row["resource_id"] in resources:
            compat[(row["care_code"], row["sector"])].append(row["resource_id"])

    tasks = []
    for req in problem["requests"]:
        care = cares[req["care_code"]]
        if care["mode_plan"] == "AVEC_RESSOURCE":
            tasks.append({"req": req, "dur": int(care["occupancy_minutes"]), "eligible": compat[(req["care_code"], req["sector"])]})
    tasks.sort(key=lambda task: (
        task["req"]["service_date"],
        task["req"].get("couple_sync_group", "~"),
        0 if task["req"].get("locked_start") else 1,
        len(task["eligible"]),
        -task["dur"],
        task["req"]["request_id"],
    ))

    assigned = {}
    by_resource = defaultdict(list)
    by_patient = defaultdict(list)
    sync_start = {}

    def overlap(a, b, c, d):
        return a < d and c < b

    def candidate_times(task):
        req = task["req"]
        if req.get("locked_start"):
            return [minutes(req["locked_start"])]
        stay = stays[req["stay_id"]]
        earliest = minutes(stay.get("earliest_start") or cfg["planning_day_start"])
        latest = end_day - task["dur"]
        preferred = req.get("preferred_start") or stay.get("preferred_day_start") or stay.get("preferred_start") or cfg["planning_day_start"]
        preferred_value = minutes(preferred)
        values = list(range(max(start_day, earliest), latest + 1, step))
        group = req.get("couple_sync_group")
        paired = sync_start.get((req["service_date"], group)) if group else None
        values.sort(key=lambda value: (abs(value - paired) if paired is not None else 0, abs(value - preferred_value), value))
        return values

    def resource_ok(resource_id, start, end, service_date):
        resource = resources[resource_id]
        if start < minutes(resource["open_start"]) or end > minutes(resource["open_end"]):
            return False
        overlaps = [(a, b) for a, b, _ in by_resource[(service_date, resource_id)] if overlap(start, end, a, b)]
        capacity = int(resource["capacity"])
        if capacity == 1:
            return not overlaps
        for instant in range(start, end):
            if 1 + sum(1 for a, b in overlaps if a <= instant < b) > capacity:
                return False
        return True

    def patient_ok(req, start, end):
        for other_start, other_end, other in by_patient[(req["service_date"], req["stay_id"])]:
            if start >= other_end:
                if start < other_end + transitions.get((other["sector"], req["sector"]), 0):
                    return False
            elif other_start >= end:
                if other_start < end + transitions.get((req["sector"], other["sector"]), 0):
                    return False
            else:
                return False
            if _truthy(cares[req["care_code"]].get("vr_entry_first")) and other["sector"] == "VR" and end > other_start:
                return False
            if _truthy(cares[other["care_code"]].get("vr_entry_first")) and req["sector"] == "VR" and other_end > start:
                return False
        return True

    def place(index):
        if index == len(tasks):
            return True
        task = tasks[index]
        req = task["req"]
        ids = [req["locked_resource"]] if req.get("locked_resource") else task["eligible"]
        group_key = (req["service_date"], req.get("couple_sync_group", ""))
        group_was_new = bool(req.get("couple_sync_group")) and group_key not in sync_start
        for start in candidate_times(task):
            end = start + task["dur"]
            if not patient_ok(req, start, end):
                continue
            for resource_id in ids:
                if not resource_ok(resource_id, start, end, req["service_date"]):
                    continue
                assigned[req["request_id"]] = (start, end, resource_id)
                by_resource[(req["service_date"], resource_id)].append((start, end, req))
                by_patient[(req["service_date"], req["stay_id"])].append((start, end, req))
                if group_was_new:
                    sync_start[group_key] = start
                if place(index + 1):
                    return True
                if group_was_new:
                    sync_start.pop(group_key, None)
                by_resource[(req["service_date"], resource_id)].pop()
                by_patient[(req["service_date"], req["stay_id"])].pop()
                assigned.pop(req["request_id"], None)
        return False

    ok = place(0)
    if not ok:
        return [], {"status": "INFEASIBLE", "engine": "fallback", "failed_requests": [task["req"]["request_id"] for task in tasks if task["req"]["request_id"] not in assigned]}

    rows = []
    for req in problem["requests"]:
        stay = stays[req["stay_id"]]
        row = {
            "status": "PROPOSE", "service_date": req["service_date"], "stay_id": req["stay_id"],
            "client_ref": stay["client_ref"], "couple_id": stay.get("couple_id", ""), "wave_id": stay.get("wave_id", ""),
            "primary_orientation": stay["primary_orientation"], "secondary_orientation": stay.get("secondary_orientation", ""),
            "request_id": req["request_id"], "care_code": req["care_code"], "sector": req["sector"],
            "mode_plan": req["mode_plan"], "couple_sync_group": req.get("couple_sync_group", ""),
            "couple_sync_priority": req.get("couple_sync_priority", ""),
            "locked": bool(req.get("locked_start") or req.get("locked_resource")), "engine": "fallback",
        }
        if req["request_id"] in assigned:
            start, end, resource_id = assigned[req["request_id"]]
            row.update({"start": hhmm(start), "end": hhmm(end), "resource_id": resource_id})
        else:
            row.update({"start": "", "end": "", "resource_id": "SANS_CRENEAU" if req["mode_plan"] == "SANS_CRENEAU" else ""})
        rows.append(row)
    rows.sort(key=lambda row: (row["service_date"], row["stay_id"], row["start"] or "99:99", row["request_id"]))
    return rows, {"status": "FEASIBLE", "engine": "fallback", "time_step_minutes": step, "note": "Moteur local de verification; CP-SAT reste le moteur de recette."}

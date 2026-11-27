from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from .io import minutes

TRUE_VALUES = {"1", "true", "TRUE", "oui", "OUI"}


def _truthy(value) -> bool:
    return str(value or "").strip() in TRUE_VALUES


def issue(level, code, message, **context):
    return {"level": level, "code": code, "message": message, "context": context}


def validate_problem(problem: dict) -> list[dict]:
    issues = []
    stays = {row["stay_id"]: row for row in problem["stays"]}
    cares = {row["care_code"]: row for row in problem["care_types"]}
    resources = {row["resource_id"]: row for row in problem["resources"] if _truthy(row.get("active", "1"))}
    compat = defaultdict(list)
    for row in problem["compatibilities"]:
        if _truthy(row.get("active", "1")) and row["resource_id"] in resources:
            compat[(row["care_code"], row["sector"])].append(row["resource_id"])

    req_ids = set()
    locked = Counter()
    same_care = defaultdict(list)
    sync_groups = defaultdict(list)
    used_cares = set()
    day_start = minutes(problem["config"]["planning_day_start"])
    step = int(problem["config"].get("time_step_minutes", 5))

    for req in problem["requests"]:
        same_care[(req.get("stay_id"), req.get("service_date"), req.get("care_code"))].append(req)
        request_id = req["request_id"]
        if request_id in req_ids:
            issues.append(issue("ERROR", "DUPLICATE_REQUEST", f"request_id duplique: {request_id}", request_id=request_id))
        req_ids.add(request_id)
        if req["stay_id"] not in stays:
            issues.append(issue("ERROR", "UNKNOWN_STAY", f"Sejour inconnu: {req['stay_id']}", request_id=request_id))
            continue
        try:
            service_date = date.fromisoformat(req["service_date"])
            stay = stays[req["stay_id"]]
            if not (date.fromisoformat(stay["start_date"]) <= service_date <= date.fromisoformat(stay["end_date"])):
                issues.append(issue("ERROR", "DATE_OUTSIDE_STAY", "Date hors sejour", request_id=request_id, date=req["service_date"]))
        except Exception:
            issues.append(issue("ERROR", "INVALID_DATE", "Date ISO attendue", request_id=request_id, date=req.get("service_date")))
        care = cares.get(req["care_code"])
        if not care:
            issues.append(issue("ERROR", "UNKNOWN_CARE", f"Soin inconnu: {req['care_code']}", request_id=request_id))
            continue
        used_cares.add(req["care_code"])
        expected = care["mode_plan"]
        if req["mode_plan"] != expected:
            issues.append(issue("ERROR", "MODE_PLAN_MISMATCH", f"MODE_PLAN doit etre {expected}", request_id=request_id, actual=req["mode_plan"]))
        allowed = set(care["allowed_sectors"].split("|"))
        if req["sector"] not in allowed and "GLOBAL" not in allowed:
            issues.append(issue("ERROR", "SECTOR_NOT_ALLOWED", "Secteur incompatible avec le soin", request_id=request_id, sector=req["sector"], allowed=sorted(allowed)))
        if expected == "AVEC_RESSOURCE":
            try:
                if int(care["occupancy_minutes"]) <= 0:
                    raise ValueError
            except Exception:
                issues.append(issue("ERROR", "INVALID_DURATION", "Duree d'occupation positive requise", request_id=request_id))
            eligible = compat[(req["care_code"], req["sector"])]
            if not eligible:
                issues.append(issue("ERROR", "NO_COMPATIBLE_RESOURCE", "Aucun poste actif compatible", request_id=request_id, care_code=req["care_code"], sector=req["sector"]))
            if req.get("locked_resource") and req["locked_resource"] not in eligible:
                issues.append(issue("ERROR", "LOCKED_RESOURCE_INCOMPATIBLE", "Poste verrouille incompatible ou inactif", request_id=request_id, resource=req["locked_resource"]))
            for field in ("preferred_start", "locked_start"):
                if req.get(field):
                    try:
                        value = minutes(req[field])
                        if field == "locked_start" and (value - day_start) % step:
                            issues.append(issue("ERROR", "TIME_NOT_ON_GRID", "Heure verrouillee hors grille", request_id=request_id, field=field, value=req[field], step=step))
                    except Exception:
                        issues.append(issue("ERROR", "INVALID_TIME", "Heure invalide", request_id=request_id, field=field, value=req.get(field)))
            if req.get("locked_start"):
                locked[(req["service_date"], req["care_code"], req["sector"], req["locked_start"])] += 1
        priority = req.get("couple_sync_priority", "")
        if priority and priority not in {"COLLECTIVE", "PREFERRED", "NONE"}:
            issues.append(issue("ERROR", "INVALID_COUPLE_SYNC_PRIORITY", "Priorite couple invalide", request_id=request_id, value=priority))
        if req.get("couple_sync_group"):
            sync_groups[(req["service_date"], req["couple_sync_group"])].append(req)

    for (stay_id, service_date, care_code), rows in same_care.items():
        if len(rows) > 1 and not all((_truthy(row.get("medical_override")) or row.get("catchup_reason")) for row in rows[1:]):
            issues.append(issue("ERROR", "DUPLICATE_CARE_WITHOUT_OVERRIDE", "Soin repete le meme jour sans rattrapage motive ni validation medicale", stay_id=stay_id, date=service_date, care_code=care_code, count=len(rows)))

    for (service_date, care_code, sector, time), demand in locked.items():
        capacity = sum(int(resources[resource_id]["capacity"]) for resource_id in compat[(care_code, sector)])
        if demand > capacity:
            issues.append(issue("ERROR", "LOCKED_CAPACITY_OVERLOAD", f"{demand} soins verrouilles a {time} pour une capacite {capacity}", date=service_date, care_code=care_code, sector=sector, time=time, demand=demand, capacity=capacity))

    couples = defaultdict(list)
    for stay in stays.values():
        for field in ("earliest_start", "preferred_day_start", "latest_start"):
            if stay.get(field):
                try:
                    minutes(stay[field])
                except Exception:
                    issues.append(issue("ERROR", "INVALID_STAY_TIME", "Heure de sejour invalide", stay_id=stay["stay_id"], field=field, value=stay[field]))
        if stay.get("couple_id"):
            couples[stay["couple_id"]].append(stay)
    for couple_id, members in couples.items():
        if len(members) != 2:
            issues.append(issue("ERROR", "COUPLE_MEMBER_COUNT", "Un couple doit contenir exactement deux sejours", couple_id=couple_id, count=len(members)))
        elif members[0].get("wave_id") != members[1].get("wave_id"):
            issues.append(issue("ERROR", "COUPLE_WAVE_MISMATCH", "Les deux membres doivent partager la meme vague", couple_id=couple_id))

    for (service_date, group), rows in sync_groups.items():
        if len(rows) != 2:
            issues.append(issue("ERROR", "COUPLE_SYNC_GROUP_SIZE", "Un groupe de synchronisation doit contenir deux demandes", date=service_date, group=group, count=len(rows)))
            continue
        stay_rows = [stays[row["stay_id"]] for row in rows]
        couple_ids = {stay.get("couple_id") for stay in stay_rows}
        if len(couple_ids) != 1 or "" in couple_ids:
            issues.append(issue("ERROR", "COUPLE_SYNC_GROUP_MISMATCH", "Les demandes synchronisees doivent appartenir au meme couple", date=service_date, group=group))
        if any(row.get("couple_sync_priority") == "COLLECTIVE" for row in rows) and rows[0]["care_code"] != rows[1]["care_code"]:
            issues.append(issue("ERROR", "COLLECTIVE_SYNC_CARE_MISMATCH", "Une synchronisation collective exige le meme soin", date=service_date, group=group))

    if problem["config"].get("write_to_nymphea") is not False:
        issues.append(issue("ERROR", "NYMPHEA_WRITE_FORBIDDEN", "write_to_nymphea doit rester false"))

    provisional = [
        care_code for care_code in sorted(used_cares)
        if "PROVISOIRE" in cares[care_code].get("status", "") or "A_CONFIRMER" in cares[care_code].get("status", "")
    ]
    if provisional:
        issues.append(issue("WARNING", "PROVISIONAL_PARAMETERS", "Parametres provisoires utilises", care_codes=provisional))
    return issues


def errors(issues):
    return [item for item in issues if item["level"] == "ERROR"]


# V1.1.1 public API preserved additively.
from .v111_validation import validate

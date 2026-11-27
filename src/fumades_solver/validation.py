from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date
from .io import minutes


def issue(level, code, message, **context):
    return {"level": level, "code": code, "message": message, "context": context}


def validate_problem(problem: dict) -> list[dict]:
    issues=[]
    stays={r["stay_id"]:r for r in problem["stays"]}
    cares={r["care_code"]:r for r in problem["care_types"]}
    resources={r["resource_id"]:r for r in problem["resources"] if r.get("active","1") in ("1","true","TRUE")}
    compat=defaultdict(list)
    for r in problem["compatibilities"]:
        if r.get("active","1") in ("1","true","TRUE") and r["resource_id"] in resources:
            compat[(r["care_code"],r["sector"])].append(r["resource_id"])
    req_ids=set()
    locked=Counter()
    same_care=defaultdict(list)
    for r in problem["requests"]:
        same_care[(r.get("stay_id"),r.get("service_date"),r.get("care_code"))].append(r)
        rid=r["request_id"]
        if rid in req_ids: issues.append(issue("ERROR","DUPLICATE_REQUEST",f"request_id duplique: {rid}",request_id=rid))
        req_ids.add(rid)
        if r["stay_id"] not in stays:
            issues.append(issue("ERROR","UNKNOWN_STAY",f"Sejour inconnu: {r['stay_id']}",request_id=rid))
            continue
        try:
            d=date.fromisoformat(r["service_date"]); s=stays[r["stay_id"]]
            if not (date.fromisoformat(s["start_date"]) <= d <= date.fromisoformat(s["end_date"])):
                issues.append(issue("ERROR","DATE_OUTSIDE_STAY","Date hors sejour",request_id=rid,date=r["service_date"]))
        except Exception:
            issues.append(issue("ERROR","INVALID_DATE","Date ISO attendue",request_id=rid,date=r.get("service_date")))
        c=cares.get(r["care_code"])
        if not c:
            issues.append(issue("ERROR","UNKNOWN_CARE",f"Soin inconnu: {r['care_code']}",request_id=rid)); continue
        expected=c["mode_plan"]
        if r["mode_plan"] != expected:
            issues.append(issue("ERROR","MODE_PLAN_MISMATCH",f"MODE_PLAN doit etre {expected}",request_id=rid,actual=r["mode_plan"]))
        allowed=set(c["allowed_sectors"].split("|"))
        if r["sector"] not in allowed and "GLOBAL" not in allowed:
            issues.append(issue("ERROR","SECTOR_NOT_ALLOWED","Secteur incompatible avec le soin",request_id=rid,sector=r["sector"],allowed=sorted(allowed)))
        if expected == "AVEC_RESSOURCE":
            try:
                if int(c["occupancy_minutes"]) <= 0: raise ValueError
            except Exception:
                issues.append(issue("ERROR","INVALID_DURATION","Duree d'occupation positive requise",request_id=rid))
            eligible=compat[(r["care_code"],r["sector"])]
            if not eligible: issues.append(issue("ERROR","NO_COMPATIBLE_RESOURCE","Aucun poste actif compatible",request_id=rid,care_code=r["care_code"],sector=r["sector"]))
            if r.get("locked_resource") and r["locked_resource"] not in eligible:
                issues.append(issue("ERROR","LOCKED_RESOURCE_INCOMPATIBLE","Poste verrouille incompatible ou inactif",request_id=rid,resource=r["locked_resource"]))
            if r.get("locked_start"):
                try: minutes(r["locked_start"])
                except Exception: issues.append(issue("ERROR","INVALID_LOCKED_TIME","Heure verrouillee invalide",request_id=rid))
                locked[(r["service_date"],r["care_code"],r["sector"],r["locked_start"])] += 1
    # Default: maximum one occurrence of the same care per morning.
    for (stay_id,d,care), rows in same_care.items():
        if len(rows)>1 and not all((x.get("medical_override","").lower() in ("1","true","oui") or x.get("catchup_reason")) for x in rows[1:]):
            issues.append(issue("ERROR","DUPLICATE_CARE_WITHOUT_OVERRIDE","Soin repete le meme jour sans rattrapage motive ni validation medicale",stay_id=stay_id,date=d,care_code=care,count=len(rows)))
    # Deterministic overload test for same-care fixed starts.
    for (d,care,sector,t), demand in locked.items():
        capacity=sum(int(resources[x]["capacity"]) for x in compat[(care,sector)])
        if demand > capacity:
            issues.append(issue("ERROR","LOCKED_CAPACITY_OVERLOAD",f"{demand} soins verrouilles a {t} pour une capacite {capacity}",date=d,care_code=care,sector=sector,time=t,demand=demand,capacity=capacity))
    if problem["config"].get("write_to_nymphea") is not False:
        issues.append(issue("ERROR","NYMPHEA_WRITE_FORBIDDEN","write_to_nymphea doit rester false"))
    provisional=[c["care_code"] for c in problem["care_types"] if "PROVISOIRE" in c.get("status","") or "A_CONFIRMER" in c.get("status","")]
    if provisional: issues.append(issue("WARNING","PROVISIONAL_PARAMETERS","Parametres provisoires presents",care_codes=provisional))
    return issues


def errors(issues):
    return [i for i in issues if i["level"]=="ERROR"]

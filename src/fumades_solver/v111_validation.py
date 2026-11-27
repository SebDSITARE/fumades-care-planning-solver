from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any

from .io import CareRequest, Parameters, Stay


def _issue(level: str, code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"level": level, "code": code, "message": message, "context": context}


def validate(stays: list[Stay], requests: list[CareRequest], parameters: Parameters) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    by_stay = {s.stay_id: s for s in stays}

    for stay in stays:
        if not stay.stay_id:
            issues.append(_issue("ERROR", "MISSING_STAY_ID", "stay_id est obligatoire"))
        if not (stay.earliest_start <= stay.preferred_day_start <= stay.latest_start):
            issues.append(_issue(
                "ERROR",
                "INVALID_DAY_START_WINDOW",
                "earliest_start <= preferred_day_start <= latest_start est requis",
                stay_id=stay.stay_id,
            ))
        for field_name in ("earliest_start", "preferred_day_start", "latest_start"):
            if getattr(stay, field_name) % 5:
                issues.append(_issue(
                    "ERROR",
                    "TIME_NOT_ON_5_MINUTE_GRID",
                    "Les horaires d'ancrage doivent appartenir a la grille de 5 minutes",
                    stay_id=stay.stay_id,
                    field=field_name,
                ))

    ids = Counter(r.request_id for r in requests)
    for request_id, count in ids.items():
        if not request_id or count > 1:
            issues.append(_issue(
                "ERROR",
                "DUPLICATE_REQUEST_ID" if request_id else "MISSING_REQUEST_ID",
                "request_id doit etre renseigne et unique",
                request_id=request_id,
                count=count,
            ))

    duplicates = Counter((r.stay_id, r.service_date.isoformat(), r.care_code) for r in requests)
    for (stay_id, day, care_code), count in duplicates.items():
        if count <= 1:
            continue
        relevant = [
            r for r in requests
            if (r.stay_id, r.service_date.isoformat(), r.care_code) == (stay_id, day, care_code)
        ]
        if not all(r.medical_override or r.catchup_reason for r in relevant):
            issues.append(_issue(
                "ERROR",
                "DUPLICATE_CARE_WITHOUT_OVERRIDE",
                "Soin repete le meme jour sans rattrapage motive ni validation medicale",
                stay_id=stay_id,
                date=day,
                care_code=care_code,
                count=count,
            ))

    for request in requests:
        stay = by_stay.get(request.stay_id)
        if stay is None:
            issues.append(_issue(
                "ERROR", "UNKNOWN_STAY", "Le sejour de la demande est inconnu",
                request_id=request.request_id, stay_id=request.stay_id,
            ))
            continue
        if not (stay.start_date <= request.service_date <= stay.end_date):
            issues.append(_issue(
                "ERROR", "CARE_OUTSIDE_STAY", "La date du soin est hors sejour",
                request_id=request.request_id,
            ))
        if request.has_slot and request.locked_start is not None:
            if request.locked_start % 5:
                issues.append(_issue(
                    "ERROR", "LOCKED_START_NOT_ON_5_MINUTE_GRID",
                    "locked_start doit appartenir a la grille de 5 minutes",
                    request_id=request.request_id,
                ))
            if request.locked_start < stay.earliest_start:
                issues.append(_issue(
                    "ERROR", "LOCKED_START_BEFORE_EARLIEST",
                    "locked_start ne peut pas preceder earliest_start",
                    request_id=request.request_id,
                ))
        if request.locked_resource and not request.locked_start:
            issues.append(_issue(
                "ERROR", "LOCKED_RESOURCE_WITHOUT_START",
                "locked_resource requiert locked_start",
                request_id=request.request_id,
            ))

    used_codes = {r.care_code for r in requests}
    provisional = sorted(code for code in used_codes if parameters.care(code).provisional)
    if provisional:
        issues.append(_issue(
            "WARNING",
            "PROVISIONAL_PARAMETERS",
            "Parametres provisoires presents pour des soins utilises",
            care_codes=provisional,
        ))

    return {
        "status": "INVALID" if any(i["level"] == "ERROR" for i in issues) else "VALID",
        "issues": issues,
    }

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Iterable

from .io import hhmm, minutes

TRUE_VALUES = {"1", "true", "yes", "oui", "vrai", "y"}


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in TRUE_VALUES


def _planned_date(row: dict) -> str:
    return row.get("planned_service_date") or row.get("service_date") or ""


def _prescribed_date(row: dict, request_map: dict[str, dict]) -> str:
    return row.get("prescribed_service_date") or request_map.get(row.get("request_id", ""), {}).get("service_date", "")


def _scheduled(row: dict) -> bool:
    return bool(row.get("start") and row.get("end"))


def _compressed(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and (not result or result[-1] != value):
            result.append(value)
    return result


def _pattern_count(sequence: list[str], pattern: list[str]) -> int:
    if not pattern:
        return 0
    return sum(sequence[index:index + len(pattern)] == pattern for index in range(len(sequence) - len(pattern) + 1))


def compute_acceptance_metrics(
    rows: list[dict],
    prescribed_requests: list[dict],
    target_stay_id: str,
    preferred_start: str,
    preferred_tolerance_minutes: int = 5,
    sector_return_pattern: list[str] | None = None,
    expected_start_sector: str = "RH",
) -> dict:
    """Measure one baseline or solver planning without changing solver rules."""
    pattern = sector_return_pattern or ["RH", "DER", "RH"]
    request_map = {row["request_id"]: row for row in prescribed_requests if row.get("stay_id") == target_stay_id}
    prescribed_ids = set(request_map)
    target_rows = [row for row in rows if row.get("stay_id") == target_stay_id]
    scheduled = [row for row in target_rows if _scheduled(row)]
    scheduled_ids = [row.get("request_id", "") for row in scheduled]
    scheduled_counter = Counter(scheduled_ids)

    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in scheduled:
        by_day[_planned_date(row)].append(row)

    first_deviations: list[int] = []
    waits: list[int] = []
    spans: list[int] = []
    sector_changes = 0
    return_count = 0
    return_days: list[str] = []
    any_sector_return_count = 0
    any_sector_return_days: list[str] = []
    expected_start_sector_days = 0
    for service_date, items in sorted(by_day.items()):
        ordered = sorted(items, key=lambda row: (minutes(row["start"]), minutes(row["end"]), row.get("request_id", "")))
        first = min(minutes(row["start"]) for row in ordered)
        last = max(minutes(row["end"]) for row in ordered)
        care_minutes = sum(minutes(row["end"]) - minutes(row["start"]) for row in ordered)
        sectors = _compressed(row.get("sector", "") for row in ordered)
        if sectors and sectors[0] == expected_start_sector:
            expected_start_sector_days += 1
        day_returns = _pattern_count(sectors, pattern)
        if day_returns:
            return_days.append(service_date)
        return_count += day_returns
        any_day_returns = sum(
            sectors[index] == sectors[index + 2] and sectors[index] != sectors[index + 1]
            for index in range(max(0, len(sectors) - 2))
        )
        if any_day_returns:
            any_sector_return_days.append(service_date)
        any_sector_return_count += any_day_returns
        sector_changes += max(0, len(sectors) - 1)
        spans.append(last - first)
        waits.append(last - first - care_minutes)
        first_deviations.append(abs(first - minutes(preferred_start)))

    prescribed_by_care = Counter(row["care_code"] for row in request_map.values())
    scheduled_by_care = Counter(row.get("care_code", "") for row in scheduled if row.get("request_id") in prescribed_ids)
    exact_day_count = sum(
        1 for row in scheduled
        if row.get("request_id") in prescribed_ids and _planned_date(row) == _prescribed_date(row, request_map)
    )
    unpositioned_ids = sorted(prescribed_ids - set(scheduled_ids))
    delayed = [
        row for row in scheduled
        if row.get("request_id") in prescribed_ids and _planned_date(row) != _prescribed_date(row, request_map)
    ]
    denominator = max(1, len(prescribed_ids))
    within_tolerance = sum(value <= preferred_tolerance_minutes for value in first_deviations)

    return {
        "prescribed_care_count": len(prescribed_ids),
        "positioned_care_count": len(prescribed_ids & set(scheduled_ids)),
        "unpositioned_care_count": len(unpositioned_ids),
        "unpositioned_request_ids": unpositioned_ids,
        "manual_additions_needed": sum(_truthy(row.get("manual_addition")) for row in target_rows),
        "delayed_or_rescheduled_care_count": len(delayed),
        "vapor_end_of_cure_reports": sum(row.get("care_code") == "0519" for row in delayed),
        "unpositioned_general_showers": sum(
            row.get("care_code") == "0301" and not _scheduled(row) for row in target_rows
        ),
        "avoidable_rh_der_rh_returns": return_count,
        "rh_der_rh_return_days": return_days,
        "avoidable_sector_returns": any_sector_return_count,
        "sector_return_days": any_sector_return_days,
        "intersector_moves": sector_changes,
        "prescription_coverage_percent": round(100 * len(prescribed_ids & set(scheduled_ids)) / denominator, 2),
        "prescription_exact_day_percent": round(100 * exact_day_count / denominator, 2),
        "duplicate_positioned_request_count": sum(max(0, count - 1) for count in scheduled_counter.values()),
        "extra_positioned_request_count": sum(request_id not in prescribed_ids for request_id in scheduled_ids),
        "prescribed_by_care": dict(sorted(prescribed_by_care.items())),
        "positioned_by_care": dict(sorted(scheduled_by_care.items())),
        "days_with_positioned_care": len(by_day),
        "preferred_start_tolerance_minutes": preferred_tolerance_minutes,
        "days_starting_within_tolerance": within_tolerance,
        "start_time_compliance_percent": round(100 * within_tolerance / max(1, len(first_deviations)), 2),
        "expected_start_sector": expected_start_sector,
        "days_starting_in_expected_sector": expected_start_sector_days,
        "start_sector_compliance_percent": round(100 * expected_start_sector_days / max(1, len(by_day)), 2),
        "mean_start_deviation_minutes": round(mean(first_deviations), 2) if first_deviations else None,
        "max_start_deviation_minutes": max(first_deviations) if first_deviations else None,
        "total_wait_minutes": sum(waits),
        "mean_wait_minutes": round(mean(waits), 2) if waits else None,
        "max_wait_minutes": max(waits) if waits else None,
        "total_path_span_minutes": sum(spans),
        "mean_path_span_minutes": round(mean(spans), 2) if spans else None,
        "max_path_span_minutes": max(spans) if spans else None,
    }


def compute_resource_occupation(rows: list[dict], resources: list[dict]) -> list[dict]:
    """Return auditable physical-resource occupation and overload indicators."""
    resource_map = {row["resource_id"]: row for row in resources}
    grouped: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    for row in rows:
        resource_id = row.get("resource_id", "")
        if not _scheduled(row) or not resource_id or resource_id == "SANS_CRENEAU":
            continue
        grouped[(_planned_date(row), resource_id)].append((minutes(row["start"]), minutes(row["end"])))

    result = []
    for (service_date, resource_id), intervals in sorted(grouped.items()):
        resource = resource_map.get(resource_id, {})
        capacity = int(resource.get("capacity", 1) or 1)
        open_start = minutes(resource.get("open_start") or min(start for start, _ in intervals))
        open_end = minutes(resource.get("open_end") or max(end for _, end in intervals))
        occupied = sum(end - start for start, end in intervals)
        max_concurrency = 0
        overload_minutes = 0
        for instant in range(open_start, open_end):
            concurrency = sum(start <= instant < end for start, end in intervals)
            max_concurrency = max(max_concurrency, concurrency)
            if concurrency > capacity:
                overload_minutes += 1
        available = max(1, (open_end - open_start) * capacity)
        result.append({
            "service_date": service_date,
            "resource_id": resource_id,
            "sector": resource.get("sector", ""),
            "open_start": hhmm(open_start),
            "open_end": hhmm(open_end),
            "capacity": capacity,
            "occupied_capacity_minutes": occupied,
            "available_capacity_minutes": available,
            "utilization_percent": round(100 * occupied / available, 2),
            "max_concurrency": max_concurrency,
            "overload_minutes": overload_minutes,
        })
    return result


def compare_metrics(baseline: dict, solver: dict) -> dict:
    lower_is_better = {
        "unpositioned_care_count", "manual_additions_needed", "delayed_or_rescheduled_care_count",
        "vapor_end_of_cure_reports", "unpositioned_general_showers", "avoidable_rh_der_rh_returns",
        "avoidable_sector_returns", "intersector_moves", "mean_start_deviation_minutes", "max_start_deviation_minutes",
        "total_wait_minutes", "mean_wait_minutes", "max_wait_minutes", "total_path_span_minutes",
        "mean_path_span_minutes", "max_path_span_minutes", "duplicate_positioned_request_count",
        "extra_positioned_request_count",
    }
    higher_is_better = {
        "positioned_care_count", "prescription_coverage_percent", "prescription_exact_day_percent",
        "start_time_compliance_percent", "start_sector_compliance_percent",
    }
    delta = {}
    for key in sorted(lower_is_better | higher_is_better):
        left, right = baseline.get(key), solver.get(key)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            raw = round(right - left, 2)
            improvement = round(left - right, 2) if key in lower_is_better else raw
            delta[key] = {"baseline": left, "solver": right, "solver_minus_baseline": raw, "improvement": improvement}
    return delta

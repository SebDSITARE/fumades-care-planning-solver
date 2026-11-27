from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import permutations
from math import ceil
from time import perf_counter
from typing import Any

try:
    from ortools.sat.python import cp_model
except ModuleNotFoundError:  # Enables validation/tests where OR-Tools is not installed.
    cp_model = None  # type: ignore[assignment]

from .io import (
    CareRequest,
    Parameters,
    Stay,
    minutes_to_time,
)

GRID_MINUTES = 5
DAY_SLOTS = 24 * 60 // GRID_MINUTES


def _find_config(value: Any, names: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in names:
                return item
        for item in value.values():
            found = _find_config(item, names)
            if found is not None:
                return found
    return None


def _config(parameters: Parameters, names: tuple[str, ...], default: Any) -> Any:
    found = _find_config(parameters.config, set(names))
    return default if found is None else found


@dataclass
class _Scheduled:
    request: CareRequest
    stay: Stay
    day_index: int
    offset: int
    duration_slots: int
    duration_minutes: int
    start: cp_model.IntVar
    end: cp_model.IntVar
    assignments: dict[str, cp_model.BoolVar]


@dataclass
class _DailyVars:
    stay: Stay
    service_date: date
    offset: int
    items: list[_Scheduled]
    first: cp_model.IntVar
    last: cp_model.IntVar
    span: cp_model.IntVar
    waiting: cp_model.IntVar
    deviation: cp_model.IntVar


def solve(
    stays: list[Stay],
    requests: list[CareRequest],
    parameters: Parameters,
    validation_warnings: list[dict[str, Any]] | None = None,
    *,
    engine: str = "cp-sat",
    time_limit_seconds: float | None = None,
    num_workers: int | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    if cp_model is None:
        return _solve_python_fallback(
            stays,
            requests,
            parameters,
            validation_warnings or [],
            engine="fallback" if engine == "fallback" else "python-fallback",
        )
    model = cp_model.CpModel()
    stays_by_id = {stay.stay_id: stay for stay in stays}
    dates = sorted({request.service_date for request in requests})
    day_index = {day: index for index, day in enumerate(dates)}
    transition_minutes = int(_config(parameters, ("transition_minutes", "minimum_transition_minutes"), 5))
    transition_slots = ceil(max(0, transition_minutes) / GRID_MINUTES)
    day_close_minutes = int(_config(parameters, ("day_end_minutes", "planning_day_end_minutes"), 18 * 60))
    day_close_slot = day_close_minutes // GRID_MINUTES

    scheduled: list[_Scheduled] = []
    no_slot: list[CareRequest] = []
    resource_intervals: dict[str, list[cp_model.IntervalVar]] = {}
    patient_intervals: dict[tuple[str, date], list[cp_model.IntervalVar]] = {}

    for request in requests:
        stay = stays_by_id[request.stay_id]
        if not request.has_slot:
            no_slot.append(request)
            continue
        index = day_index[request.service_date]
        offset = index * DAY_SLOTS
        care_type = parameters.care(request.care_code)
        duration_slots = max(1, ceil(care_type.duration_minutes / GRID_MINUTES))
        rounded_duration = duration_slots * GRID_MINUTES
        lower = offset + stay.earliest_start // GRID_MINUTES
        upper = offset + day_close_slot - duration_slots
        start = model.NewIntVar(lower, upper, f"start_{request.request_id}")
        end = model.NewIntVar(lower + duration_slots, offset + day_close_slot, f"end_{request.request_id}")
        model.Add(end == start + duration_slots)

        if request.locked_start is not None:
            model.Add(start == offset + request.locked_start // GRID_MINUTES)

        resources = parameters.resources_for(request)
        assignments: dict[str, cp_model.BoolVar] = {}
        for resource in resources:
            selected = model.NewBoolVar(f"assign_{request.request_id}_{resource}")
            assignments[resource] = selected
            interval = model.NewOptionalIntervalVar(
                start,
                duration_slots,
                end,
                selected,
                f"resource_{request.request_id}_{resource}",
            )
            resource_intervals.setdefault(resource, []).append(interval)
        model.AddExactlyOne(assignments.values())

        patient_interval = model.NewIntervalVar(
            start,
            duration_slots + transition_slots,
            start + duration_slots + transition_slots,
            f"patient_{request.request_id}",
        )
        patient_intervals.setdefault((request.stay_id, request.service_date), []).append(patient_interval)
        scheduled.append(_Scheduled(
            request=request,
            stay=stay,
            day_index=index,
            offset=offset,
            duration_slots=duration_slots,
            duration_minutes=rounded_duration,
            start=start,
            end=end,
            assignments=assignments,
        ))

    for intervals in resource_intervals.values():
        if len(intervals) > 1:
            model.AddNoOverlap(intervals)
    for intervals in patient_intervals.values():
        if len(intervals) > 1:
            model.AddNoOverlap(intervals)

    daily_vars: list[_DailyVars] = []
    objective_terms: list[cp_model.LinearExpr] = []
    groups: dict[tuple[str, date], list[_Scheduled]] = {}
    for item in scheduled:
        groups.setdefault((item.request.stay_id, item.request.service_date), []).append(item)

    preferred_weight = int(_config(parameters, ("preferred_day_start_weight",), 1000))
    journey_weight = int(_config(parameters, ("journey_duration_weight",), 10))
    waiting_weight = int(_config(parameters, ("waiting_weight",), 5))
    occurrence_weight = int(_config(parameters, ("occurrence_preferred_start_weight",), 1))
    turpentine_weight = int(_config(parameters, ("turpentine_order_weight",), 1))

    for (stay_id, service_date), items in groups.items():
        stay = stays_by_id[stay_id]
        offset = items[0].offset
        first = model.NewIntVar(offset, offset + DAY_SLOTS - 1, f"first_{stay_id}_{service_date}")
        last = model.NewIntVar(offset, offset + DAY_SLOTS, f"last_{stay_id}_{service_date}")
        model.AddMinEquality(first, [item.start for item in items])
        model.AddMaxEquality(last, [item.end for item in items])
        model.Add(first >= offset + stay.earliest_start // GRID_MINUTES)
        model.Add(first <= offset + stay.latest_start // GRID_MINUTES)

        span = model.NewIntVar(0, DAY_SLOTS, f"span_{stay_id}_{service_date}")
        model.Add(span == last - first)
        total_care_slots = sum(item.duration_slots for item in items)
        waiting = model.NewIntVar(0, DAY_SLOTS, f"waiting_{stay_id}_{service_date}")
        model.Add(waiting == span - total_care_slots)

        preferred = offset + stay.preferred_day_start // GRID_MINUTES
        deviation = model.NewIntVar(0, DAY_SLOTS, f"deviation_{stay_id}_{service_date}")
        model.AddAbsEquality(deviation, first - preferred)
        objective_terms.extend([
            preferred_weight * deviation,
            journey_weight * span,
            waiting_weight * waiting,
        ])
        daily_vars.append(_DailyVars(
            stay=stay,
            service_date=service_date,
            offset=offset,
            items=items,
            first=first,
            last=last,
            span=span,
            waiting=waiting,
            deviation=deviation,
        ))

        dry_items = [item for item in items if parameters.care(item.request.care_code).dry_care]
        for item in items:
            if item.request.preferred_start is not None:
                target = offset + item.request.preferred_start // GRID_MINUTES
                occurrence_deviation = model.NewIntVar(0, DAY_SLOTS, f"occ_dev_{item.request.request_id}")
                model.AddAbsEquality(occurrence_deviation, item.start - target)
                objective_terms.append(occurrence_weight * occurrence_deviation)

            if item.request.care_code != "0307":
                continue
            is_last = model.NewBoolVar(f"turpentine_last_{item.request.request_id}")
            model.Add(item.end == last).OnlyEnforceIf(is_last)
            model.Add(item.end != last).OnlyEnforceIf(is_last.Not())
            good_options: list[cp_model.BoolVar] = [is_last]
            for dry in dry_items:
                adjacent = model.NewBoolVar(
                    f"turpentine_before_dry_{item.request.request_id}_{dry.request.request_id}"
                )
                model.Add(dry.start == item.end + transition_slots).OnlyEnforceIf(adjacent)
                model.Add(dry.start != item.end + transition_slots).OnlyEnforceIf(adjacent.Not())
                good_options.append(adjacent)
            good = model.NewBoolVar(f"turpentine_good_{item.request.request_id}")
            model.AddMaxEquality(good, good_options)
            bad = model.NewBoolVar(f"turpentine_penalty_{item.request.request_id}")
            model.Add(good + bad == 1)
            objective_terms.append(turpentine_weight * bad)

    model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    configured_limit = float(_config(parameters, ("time_limit_seconds", "max_time_seconds"), 60.0))
    solver.parameters.max_time_in_seconds = time_limit_seconds or configured_limit
    solver.parameters.num_search_workers = num_workers or int(
        _config(parameters, ("num_search_workers", "workers"), 8)
    )
    status_code = solver.Solve(model)
    status = solver.StatusName(status_code)
    feasible = status_code in (cp_model.FEASIBLE, cp_model.OPTIMAL)

    result: dict[str, Any] = {
        "status": status,
        "engine": engine,
        "grid_minutes": GRID_MINUTES,
        "wall_time_seconds": round(solver.WallTime(), 6),
        "objective": solver.ObjectiveValue() if feasible else None,
        "best_bound": solver.BestObjectiveBound() if feasible else None,
        "gap": None,
        "relative_gap": None,
        "branches": solver.NumBranches(),
        "conflicts": solver.NumConflicts(),
        "validation_warnings": validation_warnings or [],
        "planning": [],
        "daily_indicators": [],
    }
    if not feasible:
        return result

    objective = float(result["objective"])
    bound = float(result["best_bound"])
    gap = max(0.0, objective - bound)
    result["gap"] = gap
    result["relative_gap"] = 0.0 if abs(objective) < 1e-9 else gap / abs(objective)

    for item in scheduled:
        selected_resource = next(
            resource for resource, selected in item.assignments.items() if solver.Value(selected)
        )
        start_minutes = (solver.Value(item.start) - item.offset) * GRID_MINUTES
        end_minutes = (solver.Value(item.end) - item.offset) * GRID_MINUTES
        result["planning"].append({
            "status": "COMMUNIQUE" if item.stay.planning_communicated else "PROPOSE",
            "service_date": item.request.service_date.isoformat(),
            "stay_id": item.stay.stay_id,
            "client_ref": item.stay.client_ref,
            "primary_orientation": item.stay.primary_orientation,
            "secondary_orientation": item.stay.secondary_orientation,
            "request_id": item.request.request_id,
            "care_code": item.request.care_code,
            "sector": item.request.sector,
            "mode_plan": item.request.mode_plan,
            "start": minutes_to_time(start_minutes),
            "end": minutes_to_time(end_minutes),
            "resource_id": selected_resource,
            "locked": item.request.locked_start is not None,
            "engine": engine,
        })

    for request in no_slot:
        stay = stays_by_id[request.stay_id]
        result["planning"].append({
            "status": "COMMUNIQUE" if stay.planning_communicated else "PROPOSE",
            "service_date": request.service_date.isoformat(),
            "stay_id": stay.stay_id,
            "client_ref": stay.client_ref,
            "primary_orientation": stay.primary_orientation,
            "secondary_orientation": stay.secondary_orientation,
            "request_id": request.request_id,
            "care_code": request.care_code,
            "sector": request.sector,
            "mode_plan": request.mode_plan,
            "start": "",
            "end": "",
            "resource_id": "SANS_CRENEAU",
            "locked": False,
            "engine": engine,
        })

    result["planning"].sort(key=lambda row: (
        row["service_date"], row["stay_id"], row["start"] or "99:99", row["request_id"]
    ))

    for daily in daily_vars:
        first_minutes = (solver.Value(daily.first) - daily.offset) * GRID_MINUTES
        last_minutes = (solver.Value(daily.last) - daily.offset) * GRID_MINUTES
        result["daily_indicators"].append({
            "service_date": daily.service_date.isoformat(),
            "stay_id": daily.stay.stay_id,
            "client_ref": daily.stay.client_ref,
            "first_start": minutes_to_time(first_minutes),
            "last_end": minutes_to_time(last_minutes),
            "journey_duration_minutes": solver.Value(daily.span) * GRID_MINUTES,
            "total_wait_minutes": solver.Value(daily.waiting) * GRID_MINUTES,
            "preferred_day_start": minutes_to_time(daily.stay.preferred_day_start),
            "desired_start_deviation_minutes": solver.Value(daily.deviation) * GRID_MINUTES,
        })
    result["daily_indicators"].sort(key=lambda row: (row["service_date"], row["stay_id"]))
    return result


def _solve_python_fallback(
    stays: list[Stay],
    requests: list[CareRequest],
    parameters: Parameters,
    validation_warnings: list[dict[str, Any]],
    *,
    engine: str,
) -> dict[str, Any]:
    """Small deterministic fallback used only when OR-Tools is unavailable.

    It exhausts the daily order when there are at most eight care occurrences.
    CP-SAT remains the production engine and is selected automatically whenever
    OR-Tools is installed.
    """
    started = perf_counter()
    stays_by_id = {stay.stay_id: stay for stay in stays}
    transition = ceil(int(_config(parameters, ("transition_minutes", "minimum_transition_minutes"), 5)) / GRID_MINUTES) * GRID_MINUTES
    day_close = int(_config(parameters, ("day_end_minutes", "planning_day_end_minutes"), 18 * 60))
    calendars: dict[tuple[date, str], list[tuple[int, int]]] = {}
    planning: list[dict[str, Any]] = []
    indicators: list[dict[str, Any]] = []
    total_objective = 0.0
    groups: dict[tuple[date, str], list[CareRequest]] = {}
    for request in requests:
        if request.has_slot:
            groups.setdefault((request.service_date, request.stay_id), []).append(request)

    def available(day: date, resource: str, start: int, end: int) -> bool:
        return all(end <= old_start or start >= old_end for old_start, old_end in calendars.get((day, resource), []))

    for (service_date, stay_id), items in sorted(
        groups.items(), key=lambda pair: (pair[0][0], stays_by_id[pair[0][1]].preferred_day_start, pair[0][1])
    ):
        stay = stays_by_id[stay_id]
        candidate_orders = permutations(items) if len(items) <= 8 else [tuple(items)]
        best: tuple[float, list[tuple[CareRequest, int, int, str]]] | None = None
        for order in candidate_orders:
            current = stay.earliest_start
            candidate: list[tuple[CareRequest, int, int, str]] = []
            feasible = True
            for request in order:
                duration = max(GRID_MINUTES, ceil(parameters.care(request.care_code).duration_minutes / GRID_MINUTES) * GRID_MINUTES)
                resources = parameters.resources_for(request)
                if request.locked_start is not None:
                    starts = [request.locked_start]
                else:
                    initial = max(current, stay.earliest_start, request.preferred_start or stay.earliest_start)
                    initial = ceil(initial / GRID_MINUTES) * GRID_MINUTES
                    starts = range(initial, day_close - duration + 1, GRID_MINUTES)
                chosen: tuple[int, str] | None = None
                for start in starts:
                    if start < current:
                        continue
                    end = start + duration
                    for resource in resources:
                        if available(service_date, resource, start, end) and all(
                            end <= old_start or start >= old_end
                            for _, old_start, old_end, _ in candidate
                        ):
                            chosen = (start, resource)
                            break
                    if chosen:
                        break
                if not chosen:
                    feasible = False
                    break
                start, resource = chosen
                end = start + duration
                candidate.append((request, start, end, resource))
                current = end + transition
            if not feasible or not candidate:
                continue
            first = min(row[1] for row in candidate)
            if first > stay.latest_start:
                continue
            last = max(row[2] for row in candidate)
            span = last - first
            care_total = sum(row[2] - row[1] for row in candidate)
            waiting = span - care_total
            score = abs(first - stay.preferred_day_start) * 1000 + span * 10 + waiting * 5
            ordered = sorted(candidate, key=lambda row: row[1])
            for index, (request, start, end, _) in enumerate(ordered):
                if request.preferred_start is not None:
                    score += abs(start - request.preferred_start)
                if request.care_code == "0307":
                    good = index == len(ordered) - 1 or parameters.care(ordered[index + 1][0].care_code).dry_care
                    if not good:
                        score += 1
            if best is None or score < best[0]:
                best = (float(score), candidate)
        if best is None:
            return {
                "status": "INFEASIBLE", "engine": engine, "grid_minutes": GRID_MINUTES,
                "wall_time_seconds": round(perf_counter() - started, 6), "objective": None,
                "best_bound": None, "gap": None, "relative_gap": None, "branches": 0,
                "conflicts": 0, "validation_warnings": validation_warnings,
                "planning": [], "daily_indicators": [],
            }
        score, candidate = best
        total_objective += score
        first = min(row[1] for row in candidate)
        last = max(row[2] for row in candidate)
        care_total = sum(row[2] - row[1] for row in candidate)
        for request, start, end, resource in candidate:
            calendars.setdefault((service_date, resource), []).append((start, end))
            planning.append({
                "status": "COMMUNIQUE" if stay.planning_communicated else "PROPOSE",
                "service_date": service_date.isoformat(), "stay_id": stay.stay_id,
                "client_ref": stay.client_ref, "primary_orientation": stay.primary_orientation,
                "secondary_orientation": stay.secondary_orientation, "request_id": request.request_id,
                "care_code": request.care_code, "sector": request.sector,
                "mode_plan": request.mode_plan, "start": minutes_to_time(start),
                "end": minutes_to_time(end), "resource_id": resource,
                "locked": request.locked_start is not None, "engine": engine,
            })
        indicators.append({
            "service_date": service_date.isoformat(), "stay_id": stay.stay_id,
            "client_ref": stay.client_ref, "first_start": minutes_to_time(first),
            "last_end": minutes_to_time(last), "journey_duration_minutes": last - first,
            "total_wait_minutes": last - first - care_total,
            "preferred_day_start": minutes_to_time(stay.preferred_day_start),
            "desired_start_deviation_minutes": abs(first - stay.preferred_day_start),
        })

    for request in requests:
        if request.has_slot:
            continue
        stay = stays_by_id[request.stay_id]
        planning.append({
            "status": "COMMUNIQUE" if stay.planning_communicated else "PROPOSE",
            "service_date": request.service_date.isoformat(), "stay_id": stay.stay_id,
            "client_ref": stay.client_ref, "primary_orientation": stay.primary_orientation,
            "secondary_orientation": stay.secondary_orientation, "request_id": request.request_id,
            "care_code": request.care_code, "sector": request.sector,
            "mode_plan": request.mode_plan, "start": "", "end": "",
            "resource_id": "SANS_CRENEAU", "locked": False, "engine": engine,
        })
    planning.sort(key=lambda row: (row["service_date"], row["stay_id"], row["start"] or "99:99", row["request_id"]))
    indicators.sort(key=lambda row: (row["service_date"], row["stay_id"]))
    return {
        "status": "FEASIBLE", "engine": engine, "grid_minutes": GRID_MINUTES,
        "wall_time_seconds": round(perf_counter() - started, 6), "objective": total_objective,
        "best_bound": None, "gap": None, "relative_gap": None, "branches": 0,
        "conflicts": 0, "validation_warnings": validation_warnings,
        "planning": planning, "daily_indicators": indicators,
    }

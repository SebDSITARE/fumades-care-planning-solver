from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from .io import hhmm, minutes

TRUE_VALUES = {"1", "true", "TRUE", "oui", "OUI"}


def _truthy(value) -> bool:
    return str(value or "").strip() in TRUE_VALUES


def _weight(cfg: dict, name: str, default: int) -> int:
    return int(cfg.get("objective_weights", {}).get(name, default))


# --- opt-in per-couple start-gap policy ---
def _configured_couple_start_gap_limit(cfg: dict, couple_id: str) -> int | None:
    """Return an explicitly configured hard start-gap limit for one couple.

    No entry means no hard start-gap constraint. This keeps the default couple
    behaviour soft while allowing an acceptance case to opt in by couple ID.
    """
    limits = cfg.get("couple_start_gap_limits_minutes", {})
    if limits is None:
        return None
    if not isinstance(limits, dict):
        raise ValueError("couple_start_gap_limits_minutes must be an object")
    raw_limit = limits.get(couple_id)
    if raw_limit in (None, ""):
        return None
    limit = int(raw_limit)
    if limit < 0:
        raise ValueError(f"negative couple start-gap limit for {couple_id}: {limit}")
    return limit
# --- end opt-in per-couple start-gap policy ---

# --- opt-in per-couple end-gap policy ---
def _configured_couple_end_gap_limit(cfg: dict, couple_id: str) -> int | None:
    """Return an explicitly configured hard end-gap limit for one couple.

    Missing entries preserve the general soft-objective behaviour. Only a
    couple explicitly named in config receives a hard daily end-gap limit.
    """
    limits = cfg.get("couple_end_gap_limits_minutes", {})
    if limits is None:
        return None
    if not isinstance(limits, dict):
        raise ValueError("couple_end_gap_limits_minutes must be an object")
    raw_limit = limits.get(couple_id)
    if raw_limit in (None, ""):
        return None
    limit = int(raw_limit)
    if limit < 0:
        raise ValueError(f"negative couple end-gap limit for {couple_id}: {limit}")
    return limit
# --- end opt-in per-couple end-gap policy ---


def solve_cp_sat(problem: dict) -> tuple[list[dict], dict]:
    """Solve the complete planning problem with CP-SAT.

    V1.2 adds explicit couple objectives while keeping every business rule soft
    unless it is a safety, prescription, resource, time-window or lock rule.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:
        raise RuntimeError("OR-Tools n'est pas installe. Executer: python -m pip install -e .") from exc

    cfg = problem["config"]
    day_start = minutes(cfg["planning_day_start"])
    day_end = minutes(cfg["planning_day_end"])
    step = int(cfg.get("time_step_minutes", 5))
    cares = {x["care_code"]: x for x in problem["care_types"]}
    resources = {
        x["resource_id"]: x
        for x in problem["resources"]
        if _truthy(x.get("active", "1"))
    }
    stays = {x["stay_id"]: x for x in problem["stays"]}
    transitions = {
        (x["from_sector"], x["to_sector"]): int(x["minutes"])
        for x in problem["transitions"]
    }
    compat = defaultdict(list)
    for row in problem["compatibilities"]:
        if _truthy(row.get("active", "1")) and row["resource_id"] in resources:
            compat[(row["care_code"], row["sector"])].append(row["resource_id"])
    workforce = {x["pool_id"]: x for x in problem["workforce"]}

    model = cp_model.CpModel()
    tasks: dict[str, dict] = {}
    assumptions: dict[int, str] = {}
    resource_intervals = defaultdict(list)
    patient_intervals = defaultdict(list)
    workforce_intervals = defaultdict(list)
    objective = []
    objective_terms: dict[str, list] = defaultdict(list)

    def add_objective(name: str, coefficient: int, expression) -> None:
        if coefficient:
            term = coefficient * expression
            objective.append(term)
            objective_terms[name].append(term)

    def pool_for(care: dict, sector: str):
        pools = [p for p in care.get("workforce_pool", "").split("|") if p]
        if len(pools) <= 1:
            return pools[0] if pools else None
        exact = [p for p in pools if p.endswith("_" + sector)]
        return exact[0] if exact else pools[0]

    for req in problem["requests"]:
        care = cares[req["care_code"]]
        if care["mode_plan"] != "AVEC_RESSOURCE":
            continue
        dur = int(care["occupancy_minutes"])
        key = req["request_id"]
        max_slot = (day_end - day_start - dur) // step
        slot = model.NewIntVar(0, max_slot, f"slot_{key}")
        start = model.NewIntVar(day_start, day_end - dur, f"start_{key}")
        end = model.NewIntVar(day_start + dur, day_end, f"end_{key}")
        model.Add(start == day_start + step * slot)
        model.Add(end == start + dur)

        assumption = model.NewBoolVar(f"required_{key}")
        model.AddAssumption(assumption)
        assumptions[assumption.Index()] = key

        choices = []
        eligible = compat[(req["care_code"], req["sector"])]
        for resource_id in eligible:
            resource = resources[resource_id]
            present = model.NewBoolVar(f"use_{key}_{resource_id}")
            interval = model.NewOptionalIntervalVar(start, dur, end, present, f"int_{key}_{resource_id}")
            model.Add(start >= minutes(resource["open_start"])).OnlyEnforceIf(present)
            model.Add(end <= minutes(resource["open_end"])).OnlyEnforceIf(present)
            resource_intervals[(req["service_date"], resource_id)].append(interval)
            choices.append((resource_id, present, interval))
        model.Add(sum(present for _, present, _ in choices) == 1).OnlyEnforceIf(assumption)

        if req.get("locked_start"):
            model.Add(start == minutes(req["locked_start"]))
        if req.get("locked_resource"):
            for resource_id, present, _ in choices:
                model.Add(present == int(resource_id == req["locked_resource"]))

        stay = stays[req["stay_id"]]
        if stay.get("earliest_start"):
            model.Add(start >= minutes(stay["earliest_start"]))

        patient_interval = model.NewIntervalVar(start, dur, end, f"patient_{key}")
        patient_intervals[(req["service_date"], req["stay_id"])].append(
            (req, start, end, patient_interval)
        )
        workforce_pool = pool_for(care, req["sector"])
        if workforce_pool and workforce_pool in workforce:
            workforce_intervals[(req["service_date"], workforce_pool)].append(patient_interval)

        if req.get("preferred_start"):
            deviation = model.NewIntVar(0, day_end - day_start, f"request_pref_dev_{key}")
            model.AddAbsEquality(deviation, start - minutes(req["preferred_start"]))
            add_objective(
                "request_preferred_start",
                _weight(cfg, "preferred_start_deviation", 20),
                deviation,
            )
        tasks[key] = {
            "request": req,
            "care": care,
            "start": start,
            "end": end,
            "choices": choices,
        }

    if cfg.get("rule_switches", {}).get("enforce_resource_capacity", True):
        for (_, resource_id), intervals in resource_intervals.items():
            capacity = int(resources[resource_id]["capacity"])
            if capacity == 1:
                model.AddNoOverlap(intervals)
            else:
                model.AddCumulative(intervals, [1] * len(intervals), capacity)

    daily_bounds: dict[tuple[str, str], tuple] = {}
    for (service_date, stay_id), items in patient_intervals.items():
        model.AddNoOverlap([x[3] for x in items])
        if cfg.get("rule_switches", {}).get("enforce_intersector_transitions", True):
            for left, right in combinations(items, 2):
                req_a, start_a, end_a, _ = left
                req_b, start_b, end_b, _ = right
                gap_ab = transitions.get((req_a["sector"], req_b["sector"]), 0)
                gap_ba = transitions.get((req_b["sector"], req_a["sector"]), 0)
                order = model.NewBoolVar(f"order_{req_a['request_id']}_{req_b['request_id']}")
                model.Add(start_b >= end_a + gap_ab).OnlyEnforceIf(order)
                model.Add(start_a >= end_b + gap_ba).OnlyEnforceIf(order.Not())

        if cfg.get("rule_switches", {}).get("enforce_vr_irrigation_first", True):
            irrigation = [x for x in items if _truthy(cares[x[0]["care_code"]].get("vr_entry_first"))]
            for first in irrigation:
                for other in items:
                    if other is not first and other[0]["sector"] == "VR":
                        model.Add(first[2] <= other[1])

        min_start = model.NewIntVar(day_start, day_end, f"min_{service_date}_{stay_id}")
        max_end = model.NewIntVar(day_start, day_end, f"max_{service_date}_{stay_id}")
        model.AddMinEquality(min_start, [x[1] for x in items])
        model.AddMaxEquality(max_end, [x[2] for x in items])
        span = model.NewIntVar(0, day_end - day_start, f"span_{service_date}_{stay_id}")
        model.Add(span == max_end - min_start)
        daily_bounds[(service_date, stay_id)] = (min_start, max_end, span, items)
        add_objective("patient_path_span", _weight(cfg, "patient_path_span", 10), span)

        stay = stays[stay_id]
        preferred = stay.get("preferred_day_start") or stay.get("preferred_start")
        if preferred:
            deviation = model.NewIntVar(0, day_end - day_start, f"day_pref_dev_{service_date}_{stay_id}")
            model.AddAbsEquality(deviation, min_start - minutes(preferred))
            add_objective(
                "preferred_day_start",
                _weight(cfg, "preferred_day_start_deviation", 100),
                deviation,
            )
        if stay.get("latest_start"):
            model.Add(min_start <= minutes(stay["latest_start"]))

    # Weak preference: terebenthine is last or immediately before a dry care.
    dry_codes = set(cfg.get("dry_care_codes", ["0408", "0513", "0519"]))
    for (service_date, stay_id), (_, max_end, _, items) in daily_bounds.items():
        dry_items = [x for x in items if x[0]["care_code"] in dry_codes]
        for req, _, end, _ in items:
            if req["care_code"] != "0307":
                continue
            is_last = model.NewBoolVar(f"tere_last_{req['request_id']}")
            model.Add(end == max_end).OnlyEnforceIf(is_last)
            model.Add(end != max_end).OnlyEnforceIf(is_last.Not())
            supported = [is_last]
            for dry_req, dry_start, _, _ in dry_items:
                adjacent = model.NewBoolVar(f"tere_before_{req['request_id']}_{dry_req['request_id']}")
                model.Add(dry_start == end).OnlyEnforceIf(adjacent)
                model.Add(dry_start != end).OnlyEnforceIf(adjacent.Not())
                supported.append(adjacent)
            violation = model.NewBoolVar(f"tere_violation_{req['request_id']}")
            model.AddBoolOr(supported + [violation])
            for ok in supported:
                model.Add(violation == 0).OnlyEnforceIf(ok)
            add_objective(
                "terebenthine_position",
                _weight(cfg, "terebenthine_not_last", 4),
                violation,
            )

    # Couple day start/end proximity.
    couple_members = defaultdict(list)
    for stay in stays.values():
        if stay.get("couple_id"):
            couple_members[stay["couple_id"]].append(stay["stay_id"])
    dates = sorted({date for date, _ in daily_bounds})
    for couple_id, member_ids in couple_members.items():
        if len(member_ids) != 2:
            continue
        member_a, member_b = sorted(member_ids)
        for service_date in dates:
            left = daily_bounds.get((service_date, member_a))
            right = daily_bounds.get((service_date, member_b))
            if not left or not right:
                continue
            start_gap = model.NewIntVar(0, day_end - day_start, f"couple_start_gap_{couple_id}_{service_date}")
            end_gap = model.NewIntVar(0, day_end - day_start, f"couple_end_gap_{couple_id}_{service_date}")
            model.AddAbsEquality(start_gap, left[0] - right[0])
            model.AddAbsEquality(end_gap, left[1] - right[1])
            # Apply a hard limit only when this exact couple opts in through config.
            configured_start_gap_limit = _configured_couple_start_gap_limit(cfg, couple_id)
            if configured_start_gap_limit is not None:
                model.Add(start_gap <= configured_start_gap_limit)
            # Apply an end-gap limit only when this exact couple opts in through config.
            configured_end_gap_limit = _configured_couple_end_gap_limit(cfg, couple_id)
            if configured_end_gap_limit is not None:
                model.Add(end_gap <= configured_end_gap_limit)
            add_objective("couple_start_gap", _weight(cfg, "couple_start_gap", 60), start_gap)
            add_objective("couple_end_gap", _weight(cfg, "couple_end_gap", 60), end_gap)

    # Explicit pair synchronization. The generator assigns one common group to
    # the two requests; collective groups receive the stronger coefficient.
    sync_groups = defaultdict(list)
    for task in tasks.values():
        req = task["request"]
        group = req.get("couple_sync_group")
        if group:
            sync_groups[(req["service_date"], group)].append(task)
    for (service_date, group), group_tasks in sync_groups.items():
        if len(group_tasks) != 2:
            continue
        left, right = group_tasks
        gap = model.NewIntVar(0, day_end - day_start, f"sync_gap_{service_date}_{group}")
        model.AddAbsEquality(gap, left["start"] - right["start"])
        priorities = {left["request"].get("couple_sync_priority", "PREFERRED"), right["request"].get("couple_sync_priority", "PREFERRED")}
        if "COLLECTIVE" in priorities:
            coefficient = _weight(cfg, "couple_collective_sync", 120)
            name = "couple_collective_sync"
        else:
            coefficient = _weight(cfg, "couple_preferred_sync", 25)
            name = "couple_preferred_sync"
        add_objective(name, coefficient, gap)

    if cfg.get("rule_switches", {}).get("enforce_workforce_pools", True):
        for (_, pool), intervals in workforce_intervals.items():
            model.AddCumulative(intervals, [1] * len(intervals), int(workforce[pool]["capacity"]))

    if objective:
        model.Minimize(sum(objective))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(cfg.get("max_solve_seconds", 60))
    solver.parameters.num_search_workers = int(cfg.get("num_search_workers", 8))
    status = solver.Solve(model)
    status_name = solver.StatusName(status)
    feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    objective_value = solver.ObjectiveValue() if feasible else None
    best_bound = solver.BestObjectiveBound() if feasible else None
    gap = abs(objective_value - best_bound) if feasible else None
    relative_gap = gap / max(1.0, abs(objective_value)) if feasible else None
    diagnostics = {
        "status": status_name,
        "engine": "cp-sat",
        "wall_time_seconds": solver.WallTime(),
        "objective": objective_value,
        "best_bound": best_bound,
        "gap": gap,
        "relative_gap": relative_gap,
        "branches": solver.NumBranches(),
        "conflicts": solver.NumConflicts(),
        "time_step_minutes": step,
        "objective_term_counts": {name: len(values) for name, values in sorted(objective_terms.items())},
    }
    if not feasible:
        core = solver.SufficientAssumptionsForInfeasibility() if status == cp_model.INFEASIBLE else []
        diagnostics["unsat_core"] = [assumptions.get(abs(x), str(x)) for x in core]
        return [], diagnostics

    rows = []
    for req in problem["requests"]:
        stay = stays[req["stay_id"]]
        base = {
            "status": "PROPOSE",
            "service_date": req["service_date"],
            "stay_id": req["stay_id"],
            "client_ref": stay["client_ref"],
            "couple_id": stay.get("couple_id", ""),
            "wave_id": stay.get("wave_id", ""),
            "primary_orientation": stay["primary_orientation"],
            "secondary_orientation": stay.get("secondary_orientation", ""),
            "request_id": req["request_id"],
            "care_code": req["care_code"],
            "sector": req["sector"],
            "mode_plan": req["mode_plan"],
            "couple_sync_group": req.get("couple_sync_group", ""),
            "couple_sync_priority": req.get("couple_sync_priority", ""),
            "locked": bool(req.get("locked_start") or req.get("locked_resource")),
            "engine": "cp-sat",
        }
        if req["request_id"] in tasks:
            task = tasks[req["request_id"]]
            base["start"] = hhmm(solver.Value(task["start"]))
            base["end"] = hhmm(solver.Value(task["end"]))
            base["resource_id"] = next(
                resource_id
                for resource_id, present, _ in task["choices"]
                if solver.Value(present)
            )
        else:
            base.update({"start": "", "end": "", "resource_id": "SANS_CRENEAU" if req["mode_plan"] == "SANS_CRENEAU" else ""})
        rows.append(base)
    rows.sort(key=lambda x: (x["service_date"], x["stay_id"], x["start"] or "99:99", x["request_id"]))
    return rows, diagnostics


# V1.1.1 public API preserved additively.
from .v111_model import solve

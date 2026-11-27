from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .io import minutes


def compute_daily_indicators(rows: list[dict], stays: list[dict]) -> list[dict]:
    stay_map = {row["stay_id"]: row for row in stays}
    grouped = defaultdict(list)
    for row in rows:
        if row.get("start") and row.get("end"):
            grouped[(row["service_date"], row["stay_id"])].append(row)
    result = []
    for (service_date, stay_id), items in sorted(grouped.items()):
        first = min(minutes(row["start"]) for row in items)
        last = max(minutes(row["end"]) for row in items)
        care_minutes = sum(minutes(row["end"]) - minutes(row["start"]) for row in items)
        preferred = stay_map[stay_id].get("preferred_day_start") or stay_map[stay_id].get("preferred_start")
        result.append({
            "service_date": service_date,
            "stay_id": stay_id,
            "client_ref": stay_map[stay_id]["client_ref"],
            "couple_id": stay_map[stay_id].get("couple_id", ""),
            "wave_id": stay_map[stay_id].get("wave_id", ""),
            "first_start": min(row["start"] for row in items),
            "last_end": max(row["end"] for row in items),
            "path_span_minutes": last - first,
            "care_minutes": care_minutes,
            "waiting_minutes": last - first - care_minutes,
            "preferred_day_start": preferred or "",
            "preferred_start_gap_minutes": abs(first - minutes(preferred)) if preferred else "",
        })
    return result


def compute_couple_indicators(rows: list[dict], stays: list[dict], tolerance_minutes: int = 5) -> list[dict]:
    stay_map = {row["stay_id"]: row for row in stays}
    by_day_stay = defaultdict(list)
    by_sync = defaultdict(list)
    for row in rows:
        if not row.get("start") or not row.get("end"):
            continue
        couple_id = row.get("couple_id") or stay_map[row["stay_id"]].get("couple_id", "")
        if not couple_id:
            continue
        by_day_stay[(row["service_date"], couple_id, row["stay_id"])].append(row)
        if row.get("couple_sync_group"):
            by_sync[(row["service_date"], couple_id, row["couple_sync_group"])].append(row)

    members = defaultdict(set)
    for service_date, couple_id, stay_id in by_day_stay:
        members[(service_date, couple_id)].add(stay_id)

    result = []
    for (service_date, couple_id), member_ids in sorted(members.items()):
        if len(member_ids) != 2:
            continue
        stay_a, stay_b = sorted(member_ids)
        items_a = by_day_stay[(service_date, couple_id, stay_a)]
        items_b = by_day_stay[(service_date, couple_id, stay_b)]
        first_a = min(minutes(row["start"]) for row in items_a)
        first_b = min(minutes(row["start"]) for row in items_b)
        last_a = max(minutes(row["end"]) for row in items_a)
        last_b = max(minutes(row["end"]) for row in items_b)
        sync_gaps = []
        collective_gaps = []
        sync_pairs = 0
        collective_pairs = 0
        synchronized_pairs = 0
        for (date_key, couple_key, _), paired in by_sync.items():
            if date_key != service_date or couple_key != couple_id or len(paired) != 2:
                continue
            gap = abs(minutes(paired[0]["start"]) - minutes(paired[1]["start"]))
            sync_pairs += 1
            sync_gaps.append(gap)
            if gap <= tolerance_minutes:
                synchronized_pairs += 1
            if "COLLECTIVE" in {paired[0].get("couple_sync_priority"), paired[1].get("couple_sync_priority")}:
                collective_pairs += 1
                collective_gaps.append(gap)
        result.append({
            "service_date": service_date,
            "couple_id": couple_id,
            "wave_id": stay_map[stay_a].get("wave_id", ""),
            "stay_a": stay_a,
            "stay_b": stay_b,
            "first_start_a": min(row["start"] for row in items_a),
            "first_start_b": min(row["start"] for row in items_b),
            "start_gap_minutes": abs(first_a - first_b),
            "last_end_a": max(row["end"] for row in items_a),
            "last_end_b": max(row["end"] for row in items_b),
            "end_gap_minutes": abs(last_a - last_b),
            "sync_pair_count": sync_pairs,
            "synchronized_pair_count": synchronized_pairs,
            "mean_sync_gap_minutes": round(mean(sync_gaps), 2) if sync_gaps else "",
            "max_sync_gap_minutes": max(sync_gaps) if sync_gaps else "",
            "collective_pair_count": collective_pairs,
            "max_collective_gap_minutes": max(collective_gaps) if collective_gaps else "",
            "tolerance_minutes": tolerance_minutes,
            "within_tolerance": (
                abs(first_a - first_b) <= tolerance_minutes
                and abs(last_a - last_b) <= tolerance_minutes
                and (not collective_gaps or max(collective_gaps) <= tolerance_minutes)
            ),
        })
    return result

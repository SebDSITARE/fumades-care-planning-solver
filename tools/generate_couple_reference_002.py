#!/usr/bin/env python3
"""Generate the fully pseudonymized couple acceptance case no. 2.

The source planning is not reproduced. Only its validated business pattern is
encoded: same wave and preferred time, close daily path boundaries, strong
synchronization of collective pool care, and preferred synchronization of
other care on distinct individual resources when required.
"""
from __future__ import annotations

import csv
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "acceptance" / "couple_reference_002"
FIELD_STAYS = [
    "stay_id", "client_ref", "start_date", "end_date", "primary_orientation",
    "secondary_orientation", "package_primary", "package_secondary", "earliest_start",
    "preferred_day_start", "latest_start", "preferred_start", "pmr_level",
    "planning_communicated", "couple_id", "couple_role", "wave_id",
]
FIELD_REQUESTS = [
    "request_id", "stay_id", "service_date", "care_code", "sector", "mode_plan",
    "preferred_start", "locked_start", "locked_resource", "medical_override",
    "catchup_reason", "couple_sync_group", "couple_sync_priority",
]


def treatment_days(start: date, count: int = 18) -> list[date]:
    days = []
    current = start
    while len(days) < count:
        if current.weekday() != 6:  # Monday to Saturday
            days.append(current)
        current += timedelta(days=1)
    return days


def distribute(days: list[date], fixed: dict[int, list[str]], remaining: Counter) -> dict[int, list[str]]:
    result = {index: list(fixed.get(index, [])) for index in range(len(days))}
    while sum(remaining.values()):
        candidates = sorted(range(len(days)), key=lambda index: (len(result[index]), index))
        placed = False
        for index in candidates:
            if len(result[index]) >= 4:
                continue
            choices = sorted((code for code, count in remaining.items() if count and code not in result[index]), key=lambda code: (-remaining[code], code))
            if choices:
                code = choices[0]
                result[index].append(code)
                remaining[code] -= 1
                placed = True
                break
        if not placed:
            raise RuntimeError(f"Distribution impossible: {remaining}")
    if any(len(codes) != 4 or len(set(codes)) != 4 for codes in result.values()):
        raise RuntimeError("Chaque jour doit contenir quatre soins distincts")
    return result


def pair_day(cares_a: list[str], cares_b: list[str]) -> list[tuple[str, str, str]]:
    pairs = []
    remaining_a = list(cares_a)
    remaining_b = list(cares_b)
    for code in sorted(set(remaining_a) & set(remaining_b)):
        pairs.append((code, code, "COLLECTIVE" if code in {"0306", "0601"} else "PREFERRED"))
        remaining_a.remove(code)
        remaining_b.remove(code)
    for code_a, code_b in zip(sorted(remaining_a), sorted(remaining_b)):
        pairs.append((code_a, code_b, "PREFERRED"))
    if len(pairs) != 4:
        raise RuntimeError("Quatre paires quotidiennes attendues")
    return pairs


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    days = treatment_days(date(2027, 5, 3))
    stays = [
        {
            "stay_id": "ACC-CPL2-A", "client_ref": "PSEUDO-CPL2-A",
            "start_date": days[0].isoformat(), "end_date": days[-1].isoformat(),
            "primary_orientation": "RH", "secondary_orientation": "", "package_primary": "RH1",
            "package_secondary": "", "earliest_start": "07:45", "preferred_day_start": "08:00",
            "latest_start": "08:30", "preferred_start": "08:00", "pmr_level": "0",
            "planning_communicated": "false", "couple_id": "CPL-ACC-002",
            "couple_role": "A", "wave_id": "WAVE-0800",
        },
        {
            "stay_id": "ACC-CPL2-B", "client_ref": "PSEUDO-CPL2-B",
            "start_date": days[0].isoformat(), "end_date": days[-1].isoformat(),
            "primary_orientation": "RH", "secondary_orientation": "", "package_primary": "RH1",
            "package_secondary": "", "earliest_start": "07:45", "preferred_day_start": "08:00",
            "latest_start": "08:30", "preferred_start": "08:00", "pmr_level": "0",
            "planning_communicated": "false", "couple_id": "CPL-ACC-002",
            "couple_role": "B", "wave_id": "WAVE-0800",
        },
    ]

    fixed_a = {index: ["0408", "0601" if index < 9 else "0306"] for index in range(18)}
    fixed_b = {index: ["0408"] + (["0601"] if index < 9 else []) + (["0306"] if index >= 6 else []) for index in range(18)}
    plan_a = distribute(days, fixed_a, Counter({"0513": 12, "0307": 9, "0308": 9, "0206": 6}))
    plan_b = distribute(days, fixed_b, Counter({"0513": 12, "0308": 9, "0307": 6, "0206": 6}))

    requests = []
    sequence = {"A": 0, "B": 0}
    for index, service_date in enumerate(days):
        for pair_index, (care_a, care_b, priority) in enumerate(pair_day(plan_a[index], plan_b[index]), start=1):
            group = f"CPL2-{service_date:%Y%m%d}-{pair_index:02d}"
            for role, care in (("A", care_a), ("B", care_b)):
                sequence[role] += 1
                requests.append({
                    "request_id": f"CPL2-{role}-{sequence[role]:03d}",
                    "stay_id": f"ACC-CPL2-{role}",
                    "service_date": service_date.isoformat(),
                    "care_code": care,
                    "sector": "RH",
                    "mode_plan": "AVEC_RESSOURCE",
                    "preferred_start": "",
                    "locked_start": "",
                    "locked_resource": "",
                    "medical_override": "false",
                    "catchup_reason": "",
                    "couple_sync_group": group,
                    "couple_sync_priority": priority,
                })

    write_csv(OUTPUT / "stays.csv", FIELD_STAYS, stays)
    write_csv(OUTPUT / "care_requests.csv", FIELD_REQUESTS, requests)

    print(f"{len(days)} jours generes")
    print(f"{len(stays)} sejours pseudonymises generes")
    print(f"{len(requests)} soins generes")
    for role in ("A", "B"):
        counts = Counter(row["care_code"] for row in requests if row["stay_id"].endswith(role))
        print(f"Partenaire {role}: {sum(counts.values())} soins")
        for code, count in sorted(counts.items()):
            print(f"  {code}: {count}")


if __name__ == "__main__":
    main()

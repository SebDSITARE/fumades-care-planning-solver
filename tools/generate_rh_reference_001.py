from __future__ import annotations

import csv
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

OUT = Path("data/acceptance/rh_reference_001")
STAY_ID = "ACC-RH-001"
CLIENT_REF = "PSEUDO-ACC-001"


def care_days(start: date, count: int) -> list[date]:
    result: list[date] = []
    current = start
    while len(result) < count:
        if current.weekday() != 6:  # lundi a samedi
            result.append(current)
        current += timedelta(days=1)
    return result


def generate(output_dir: Path = OUT) -> tuple[list[date], list[list[str]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    days = care_days(date(2027, 4, 5), 18)
    with (output_dir / "stays.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "stay_id", "client_ref", "start_date", "end_date",
            "primary_orientation", "secondary_orientation", "package_primary",
            "package_secondary", "earliest_start", "preferred_day_start",
            "latest_start", "pmr_level", "planning_communicated",
        ])
        writer.writerow([
            STAY_ID, CLIENT_REF, days[0].isoformat(), days[-1].isoformat(),
            "RH", "", "RH1", "", "07:45", "07:45", "09:00", 0, "false",
        ])

    # A1 x3: CATA + BAIN + ETUVE + PEN
    # A2 x3: CATA + BAIN + ETUVE + TERE
    # B  x6: CATA + ETUVE + MOB + PISC
    # C  x3: CATA + PEN + TERE + MOB
    # D  x3: CATA + PEN + TERE + PISC
    day_types = (
        [["0408", "0206", "0513", "0308"]] * 3
        + [["0408", "0206", "0513", "0307"]] * 3
        + [["0408", "0513", "0601", "0306"]] * 6
        + [["0408", "0308", "0307", "0601"]] * 3
        + [["0408", "0308", "0307", "0306"]] * 3
    )
    rows: list[list[str]] = []
    counter = 1
    for day, codes in zip(days, day_types, strict=True):
        for code in codes:
            rows.append([
                f"ACC-REQ-{counter:03d}", STAY_ID, day.isoformat(), code, "RH",
                "AVEC_RESSOURCE", "", "", "", "false", "",
            ])
            counter += 1
    with (output_dir / "care_requests.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "request_id", "stay_id", "service_date", "care_code", "sector",
            "mode_plan", "preferred_start", "locked_start", "locked_resource",
            "medical_override", "catchup_reason",
        ])
        writer.writerows(rows)
    return days, rows


if __name__ == "__main__":
    generated_days, generated_rows = generate()
    counts = Counter(row[3] for row in generated_rows)
    target = {"0206": 6, "0306": 9, "0307": 9, "0308": 9, "0408": 18, "0513": 12, "0601": 9}
    if counts != target or len(generated_rows) != 72:
        raise SystemExit(f"Composition invalide: {dict(counts)}")
    print(f"{len(generated_days)} jours generes")
    print(f"{len(generated_rows)} soins generes")
    for code, count in sorted(counts.items()):
        print(f"{code}: {count}")
    print(f"Fichiers crees dans {OUT}")

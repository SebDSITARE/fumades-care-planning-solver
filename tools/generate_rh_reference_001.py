from pathlib import Path
import csv
from datetime import date, timedelta
from collections import Counter

OUT = Path("data/acceptance/rh_reference_001")
OUT.mkdir(parents=True, exist_ok=True)

STAY_ID = "ACC-RH-001"
CLIENT_REF = "PSEUDO-ACC-001"

start = date(2027, 4, 5)

# 18 jours de soins, du lundi au samedi.
days = []
d = start

while len(days) < 18:
    if d.weekday() != 6:
        days.append(d)
    d += timedelta(days=1)


# -----------------------------------------------------
# Séjour
# -----------------------------------------------------

with (OUT / "stays.csv").open(
    "w",
    newline="",
    encoding="utf-8",
) as f:

    writer = csv.writer(f)

    writer.writerow([
        "stay_id",
        "client_ref",
        "start_date",
        "end_date",
        "primary_orientation",
        "secondary_orientation",
        "package_primary",
        "package_secondary",
        "preferred_start",
        "pmr_level",
        "planning_communicated",
    ])

    writer.writerow([
        STAY_ID,
        CLIENT_REF,
        days[0].isoformat(),
        days[-1].isoformat(),
        "RH",
        "",
        "RH1",
        "",
        "07:45",
        0,
        "false",
    ])


# -----------------------------------------------------
# Composition de référence
# -----------------------------------------------------
#
# Tous les jours :
#   CATA
#
# 6 jours type A :
#   CATA + BAIN + ETUVE + PEN
#
# 6 jours type B :
#   CATA + ETUVE + MOB + PISC
#
# 3 jours type C :
#   CATA + PEN + TERE + MOB
#
# 3 jours type D :
#   CATA + PEN + TERE + PISC
#
# Totaux :
#
# CATA  18
# BAIN   6
# ETUVE 12
# PEN    9
# TERE   6
# MOB    9
# PISC   9
#
# Il manque alors TERE x3.
#
# Pour obtenir TERE x9, trois journées type A
# deviennent :
#
# CATA + BAIN + TERE + PEN
#
# ce qui ramène ETUVE à 9.
#
# Nous devons donc construire les quantités
# mathématiquement plutôt que par remplacement.
#
# Répartition finale :
#
# 3 x [CATA, BAIN, ETUVE, PEN]
# 3 x [CATA, BAIN, ETUVE, TERE]
# 6 x [CATA, ETUVE, MOB, PISC]
# 3 x [CATA, PEN, TERE, MOB]
# 3 x [CATA, PEN, TERE, PISC]
#
# Totaux :
# CATA = 18
# BAIN = 6
# ETUVE = 12
# PEN = 9
# TERE = 9
# MOB = 9
# PISC = 9
#
# TOTAL = 72


patterns = (
    [["0408", "0206", "0513", "0308"]] * 3
    + [["0408", "0206", "0513", "0307"]] * 3
    + [["0408", "0513", "0601", "0306"]] * 6
    + [["0408", "0308", "0307", "0601"]] * 3
    + [["0408", "0308", "0307", "0306"]] * 3
)


requests = []
request_number = 1


for day_index, (day, care_codes) in enumerate(
    zip(days, patterns)
):
    for care_index, care_code in enumerate(care_codes):

        preferred_start = ""

        # Une seule indication de préférence initiale
        # suffit pour ce jeu de recette.
        if day_index == 0 and care_index == 0:
            preferred_start = "07:45"

        requests.append([
            f"ACC-REQ-{request_number:03d}",
            STAY_ID,
            day.isoformat(),
            care_code,
            "RH",
            "AVEC_RESSOURCE",
            preferred_start,
            "",
            "",
            "false",
            "",
        ])

        request_number += 1


# -----------------------------------------------------
# Contrôles avant écriture
# -----------------------------------------------------

counts = Counter(row[3] for row in requests)

expected = {
    "0206": 6,
    "0306": 9,
    "0307": 9,
    "0308": 9,
    "0408": 18,
    "0513": 12,
    "0601": 9,
}

assert len(days) == 18
assert len(requests) == 72
assert counts == expected, (counts, expected)

# Interdiction de doubler un soin le même jour.
for day in days:
    care_codes = [
        row[3]
        for row in requests
        if row[2] == day.isoformat()
    ]

    assert len(care_codes) == len(set(care_codes)), (
        day,
        care_codes,
    )


# -----------------------------------------------------
# Export
# -----------------------------------------------------

with (OUT / "care_requests.csv").open(
    "w",
    newline="",
    encoding="utf-8",
) as f:

    writer = csv.writer(f)

    writer.writerow([
        "request_id",
        "stay_id",
        "service_date",
        "care_code",
        "sector",
        "mode_plan",
        "preferred_start",
        "locked_start",
        "locked_resource",
        "medical_override",
        "catchup_reason",
    ])

    writer.writerows(requests)


print(f"{len(days)} jours générés")
print(f"{len(requests)} soins générés")

for care_code in sorted(counts):
    print(f"{care_code}: {counts[care_code]}")

print(f"Fichiers créés dans {OUT}")
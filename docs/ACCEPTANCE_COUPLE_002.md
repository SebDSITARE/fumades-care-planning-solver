# Cas de recette couple n°2 — V1.2.0

## Finalité et source métier

Ce cas traduit uniquement l'enseignement non nominatif d'un planning jugé satisfaisant : les deux curistes se suivent sur la quasi-totalité des soins, dans une plage horaire convenable. Le PDF source n'est ni copié ni embarqué.

Le cas contrôle :

- deux séjours et deux prescriptions individuelles pseudonymisés ;
- une même vague `WAVE-0800` et un début quotidien souhaité à `08:00` ;
- une grille de départ de cinq minutes ;
- le rapprochement du premier soin et de la fin de parcours ;
- une synchronisation renforcée des soins collectifs `0306` et `0601` ;
- une synchronisation préférentielle des autres paires ;
- l'affectation simultanée possible sur des postes individuels distincts ;
- 18 jours, 72 soins par curiste et 144 demandes au total ;
- l'absence d'écriture dans Nymphéa.

Les prescriptions restent distinctes : le partenaire A a 9 soins `0306` et 9 soins `0307`; le partenaire B en a respectivement 12 et 6. Les deux totalisent 72 soins.

## Données et champs

- `data/acceptance/couple_reference_002/stays.csv`
- `data/acceptance/couple_reference_002/care_requests.csv`
- générateur reproductible : `tools/generate_couple_reference_002.py`

Champs de séjour : `couple_id`, `couple_role`, `wave_id`, `earliest_start`, `preferred_day_start`, `latest_start`.

Champs de demande : `couple_sync_group`, `couple_sync_priority` (`COLLECTIVE` ou `PREFERRED`). Une priorité reste un objectif souple : elle ne rend jamais un problème physiquement infaisable pour préserver le couple.

## Fonction objectif

Par ordre métier, les contraintes dures restent la prescription, les capacités, la compatibilité, les fenêtres horaires, les transitions et les rendez-vous verrouillés. Les nouveaux termes sont souples :

1. synchronisation des soins collectifs ;
2. écart de début quotidien du couple ;
3. écart de fin quotidien du couple ;
4. rapprochement préférentiel des autres paires ;
5. durée des parcours et horaire souhaité.

Les coefficients sont externalisés dans `config/solver.json`.

## Indicateurs produits

`couple_indicators.csv` contient une ligne par jour et par couple :

- `start_gap_minutes` ;
- `end_gap_minutes` ;
- nombre de paires explicites et nombre dans la tolérance ;
- moyenne et maximum des écarts de synchronisation ;
- nombre de paires collectives et maximum de leur écart ;
- booléen `within_tolerance`.

`daily_indicators.csv` conserve les indicateurs individuels : début, fin, amplitude, soins, attente et écart à l'horaire souhaité.

## Régénération, validation et recette CP-SAT

```bash
python tools/generate_couple_reference_002.py

python -m fumades_solver.cli validate \
  --input-dir data/acceptance/couple_reference_002 \
  --parameter-dir config/parameters \
  --config config/solver.json

rm -rf outputs/couple_reference_002_v1_2_0
python -m fumades_solver.cli solve \
  --input-dir data/acceptance/couple_reference_002 \
  --parameter-dir config/parameters \
  --config config/solver.json \
  --output-dir outputs/couple_reference_002_v1_2_0 \
  --engine cp-sat
```

Contrôles attendus : statut `OPTIMAL` ou `FEASIBLE`, 144 lignes de planning, 36 indicateurs individuels, 18 indicateurs couple, départs sur la grille de cinq minutes, aucune erreur de validation, uniquement le warning provisoire du soin `0308` si les paramètres V1.1.1 sont inchangés.

## Tests automatisés

```bash
python -m pip install -e .
python -m pytest -v
```

## Commit et push sur branche dédiée

Le bundle crée la branche `feature/v1.2.0-couple-acceptance-002`. Après vérification :

```bash
git status
git diff --check
git add VERSION.txt pyproject.toml src config/solver.json schemas docs tests tools data/acceptance/couple_reference_002 README.md
git commit -m "Add couple acceptance case 002 and couple objectives"
git push -u origin feature/v1.2.0-couple-acceptance-002
```

La branche stable et le tag `v1.1.1` ne sont ni réécrits ni déplacés.

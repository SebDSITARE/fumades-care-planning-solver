# Architecture V1.1.1

La V1.1.1 conserve le CLI V1.1 (`validate` et `solve`) et remplace l'unité minute par un créneau CP-SAT de cinq minutes.

1. `io.py` charge les CSV V1.1/V1.1.1 et les paramètres existants. Les alias de colonnes permettent de conserver les tables V1.1.
2. `validation.py` contrôle la fenêtre journalière, la grille, les verrouillages, les doublons et les paramètres provisoires utilisés.
3. `model.py` applique les contraintes dures : borne `earliest_start`, `latest_start` sur le premier soin, `locked_start`, non-chevauchement patient/ressource et compatibilité ressource.
4. L'objectif minimise d'abord l'écart du premier soin à `preferred_day_start`, puis la durée du parcours et l'attente. Une pénalité faible place le soin `0307` en fin de séance ou immédiatement avant un soin sec.
5. `export.py` produit le planning, les indicateurs quotidiens et les diagnostics prouvables par OR-Tools.

Les fichiers `config/parameters/*` de la V1.1 ne sont pas remplacés par le patch. Si une colonne `dry_care`/`soin_sec` existe dans `care_types.csv`, elle pilote la préférence térébenthine ; à défaut, `0408` est traité comme soin sec pour compatibilité.

# V1.1.1 — Ancrage horaire et grille de planification

## Corrigé

- suppression des débuts avant l'heure admissible du séjour ;
- suppression des horaires hors grille (07:37, 08:02, etc.) ;
- avertissement `0701` absent lorsque le soin n'est pas utilisé.

## Ajouté

- fenêtre `earliest_start` / `preferred_day_start` / `latest_start` ;
- indicateurs quotidiens et diagnostics d'optimalité ;
- préférence faible de séquencement de la térébenthine ;
- tests de non-régression et recette RH complète.

## Compatibilité

Le CLI et les deux CSV d'entrée sont conservés. Les séjours V1.1 utilisant seulement `preferred_start` restent lisibles, mais doivent migrer vers les trois nouveaux champs.
